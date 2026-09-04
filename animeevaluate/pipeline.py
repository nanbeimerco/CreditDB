"""
Integrated Anime Evaluation & Prediction Pipeline.
Orchestrates:
1. Ratings Data Loading
2. Item-User Bias ALS Decomposition (R_{ui} = \mu + b_u + b_i)
3. Local Z-Score Era Normalization (Z_i)
4. Leak-Free Temporal Feature Extraction (Genga w_a, S(a), Main roles decay)
5. GBDT Training & SHAP Attribution
6. Staff Capability Evaluation & Side-by-side AniList Comparison
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from .data.dataset import DatasetManager
from .models.bias_model import ItemUserBiasModel
from .models.local_zscore import LocalZScoreModel
from .models.feature_engineer import StaffFeatureEngineer
from .models.predictor import QualityPredictor
from .models.staff_evaluator import StaffEvaluator

def normalize_search_text(text: str) -> str:
    """Normalizes Japanese text for fuzzy substring matching (archaic kana, punctuation, katakana/hiragana)."""
    if not text:
        return ""
    import unicodedata
    t = unicodedata.normalize("NFKC", str(text)).lower()
    replacements = {
        "ヱ": "エ", "ゑ": "え", "ヲ": "オ", "を": "お",
        "ヰ": "イ", "ゐ": "い", "ヴ": "ブ", "ゔ": "ぶ",
        "・": "", "･": "", " ": "", "　": "", ":": "", "：": "",
        "~": "", "～": "", "-": "", "—": "", "─": "",
        "!": "", "！": "", "?": "", "？": "", "☆": "", "★": "",
        "|": "", "｜": "", "│": "", "▌": ""
    }
    for k, v in replacements.items():
        t = t.replace(k, v)
    res = []
    for ch in t:
        code = ord(ch)
        if 0x3041 <= code <= 0x3096:
            res.append(chr(code + 0x60))
        else:
            res.append(ch)
    return "".join(res)


class AnimePipeline:
    """Master pipeline tying together dataset, models, predictions, and explanations."""

    def __init__(self, data_dir: Optional[Union[str, Path]] = None):
        self.dataset_manager = DatasetManager(data_dir)
        self.bias_model = ItemUserBiasModel(lambda_user=10.0, lambda_item=10.0, max_iter=40)
        self.local_z_model = LocalZScoreModel(window_size=3, min_items_in_window=3)
        self.feature_engineer = StaffFeatureEngineer(top_talent_threshold=0.4, decay_gamma=0.8)
        self.predictor = QualityPredictor(n_estimators=100, learning_rate=0.05, max_depth=4)
        self.staff_evaluator = StaffEvaluator()

        self.works_metadata: Dict[str, Dict[str, Any]] = {}
        self.ratings_df: Optional[pd.DataFrame] = None
        self.item_biases: Dict[str, float] = {}
        self.z_scores: Dict[str, float] = {}
        self.feature_df: Optional[pd.DataFrame] = None
        self.evaluation_metrics: Dict[str, float] = {}
        self.work_pred_ranks: Dict[str, int] = {}
        self.work_raw_ranks: Dict[str, int] = {}
        self.work_z_ranks: Dict[str, int] = {}
        self.is_trained: bool = False

    def train(self) -> Dict[str, Any]:
        """Runs end-to-end model training."""
        # 1. Load or initialize dataset
        self.works_metadata, self.ratings_df = self.dataset_manager.load_or_init_dataset()

        # 2. Fit Item-User bias decomposition model
        self.bias_model.fit(self.ratings_df, user_col="user_id", item_col="item_id", score_col="score")
        raw_b = self.bias_model.get_item_biases()
        self.item_biases = {str(k): float(v) for k, v in raw_b.items()}

        # 3. Fit Local Z-score era standardization model
        years_map = {
            work_id: int(meta.get("year", 2020))
            for work_id, meta in self.works_metadata.items()
        }
        self.z_scores = self.local_z_model.fit_transform(self.item_biases, years_map)

        # 4. Generate leak-free temporal feature dataset
        self.feature_df = self.feature_engineer.extract_features_dataset(
            all_works_metadata=self.works_metadata,
            z_scores=self.z_scores,
        )

        # 5. Fit GBDT Predictor on (X, target_z)
        feature_cols = self.feature_engineer.feature_names
        X = self.feature_df[feature_cols]
        y = self.feature_df["target_z"]
        self.predictor.fit(X, y)
        self.evaluation_metrics = self.predictor.evaluate(X, y)

        # 6. Build Staff Capability Evaluator
        self.staff_evaluator.build_from_dataset(self.works_metadata, self.z_scores)

        # 7. Precompute predicted scores, z-scores, and ranks for all works
        pred_scores_list = []
        raw_scores_list = []
        z_scores_list = []

        feat_map = (
            self.feature_df.set_index("work_id")[feature_cols].to_dict("index")
            if self.feature_df is not None
            else {}
        )

        for wid, meta in self.works_metadata.items():
            year = int(meta.get("year", 2020))
            raw_score = float(meta.get("anilist_mean_score", 0.0))
            raw_scores_list.append((wid, raw_score))

            true_z = float(self.z_scores.get(wid, 0.0))
            z_scores_list.append((wid, true_z))

            feats = feat_map.get(wid)
            if feats is None:
                feats = self.feature_engineer.extract_features_for_work(
                    work_id=wid,
                    release_year=year,
                    staff_data=meta.get("staff", {}),
                    all_works_metadata=self.works_metadata,
                    z_scores=self.z_scores,
                )
            pred_z = float(self.predictor.predict_single(feats))
            est_b = self.local_z_model.inverse_transform_single(pred_z, year)
            est_score = float(np.clip(self.bias_model.global_mean + est_b, 10.0, 100.0))
            pred_scores_list.append((wid, est_score))

        pred_scores_list.sort(key=lambda x: x[1], reverse=True)
        self.work_pred_ranks = {wid: idx + 1 for idx, (wid, _) in enumerate(pred_scores_list)}

        raw_scores_list.sort(key=lambda x: x[1], reverse=True)
        self.work_raw_ranks = {wid: idx + 1 for idx, (wid, _) in enumerate(raw_scores_list)}

        z_scores_list.sort(key=lambda x: x[1], reverse=True)
        self.work_z_ranks = {wid: idx + 1 for idx, (wid, _) in enumerate(z_scores_list)}

        self.is_trained = True
        return {
            "status": "success",
            "total_works": len(self.works_metadata),
            "total_ratings": len(self.ratings_df) if self.ratings_df is not None else 0,
            "metrics": self.evaluation_metrics,
            "global_rating_mean": round(self.bias_model.global_mean, 2),
        }

    def predict_custom(
        self,
        title: str,
        release_year: int,
        staff: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Predicts quality and SHAP attribution for custom staff configuration.
        """
        if not self.is_trained:
            self.train()

        feats = self.feature_engineer.extract_features_for_work(
            work_id="CUSTOM_INFERENCE",
            release_year=release_year,
            staff_data=staff,
            all_works_metadata=self.works_metadata,
            z_scores=self.z_scores,
        )

        explanation = self.predictor.explain_prediction(feats)
        pred_z = explanation["predicted_z"]

        # Invert Z-score back to estimated raw rating
        est_b = self.local_z_model.inverse_transform_single(pred_z, release_year)
        est_anilist_score = float(np.clip(self.bias_model.global_mean + est_b, 10.0, 100.0))

        return {
            "title": title,
            "release_year": release_year,
            "predicted_z": round(pred_z, 3),
            "predicted_anilist_score": round(est_anilist_score, 1),
            "base_z": round(explanation["base_value"], 3),
            "top_positive_factors": explanation["top_positive"],
            "top_negative_factors": explanation["top_negative"],
            "all_contributions": explanation["contributions"],
        }

    def get_comparison_table(self) -> List[Dict[str, Any]]:
        """
        Generates comprehensive side-by-side comparison table:
        AniList raw mean, de-biased b_i, ground truth Z_i, predicted Z_i, predicted raw, residual.
        """
        if not self.is_trained:
            self.train()

        table = []
        feature_cols = self.feature_engineer.feature_names
        X = self.feature_df[feature_cols]
        predicted_z_all = self.predictor.predict(X)

        for idx, row in self.feature_df.iterrows():
            work_id = str(row["work_id"])
            meta = self.works_metadata.get(work_id, {})
            title = meta.get("title", work_id)
            year = int(row["release_year"])
            raw_anilist = meta.get("anilist_mean_score", 0.0)

            b_val = self.item_biases.get(work_id, 0.0)
            true_z = float(row["target_z"])
            pred_z = float(predicted_z_all[idx])

            # Invert predicted Z to estimated score
            est_b = self.local_z_model.inverse_transform_single(pred_z, year)
            est_score = float(np.clip(self.bias_model.global_mean + est_b, 10.0, 100.0))

            residual = true_z - pred_z  # positive means performed better than staff expectations!

            # Quick top factor
            feats = {col: float(row[col]) for col in feature_cols}
            expl = self.predictor.explain_prediction(feats)
            top_pos = expl["top_positive"][0]["label_ja"] if expl["top_positive"] else "-"

            table.append({
                "work_id": work_id,
                "title": title,
                "year": year,
                "anilist_raw_score": round(raw_anilist, 1),
                "debiased_b_i": round(b_val, 2),
                "true_z_score": round(true_z, 3),
                "deviation_score": round(50.0 + 10.0 * true_z, 1),
                "z_score_rank": self.work_z_ranks.get(work_id, 0),
                "predicted_z_score": round(pred_z, 3),
                "predicted_score": round(est_score, 1),
                "pred_score_rank": self.work_pred_ranks.get(work_id, 0),
                "raw_score_rank": self.work_raw_ranks.get(work_id, 0),
                "residual": round(residual, 3),
                "total_works": len(self.work_pred_ranks),
                "performance_verdict": "サプライズ名作 (期待値以上)" if residual > 0.4 else (
                    "期待外れ (ポテンシャル未達)" if residual < -0.4 else "概ねスタッフ前評判通り"
                ),
                "top_factor": top_pos,
            })

        # Sort descending by true Z-score
        table.sort(key=lambda x: x["true_z_score"], reverse=True)
        return table

    def get_staff_leaderboard(
        self,
        role: Optional[str] = None,
        sort_by: str = "rating",
        min_works: int = 1,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Returns capability leaderboard for staff."""
        if not self.is_trained:
            self.train()
        return self.staff_evaluator.get_leaderboard(
            role=role, sort_by=sort_by, min_works=min_works, limit=limit
        )

    def get_staff_profile(self, staff_name: str) -> Optional[Dict[str, Any]]:
        """Returns individual staff capability profile and history."""
        if not self.is_trained:
            self.train()
        return self.staff_evaluator.get_staff_profile(staff_name)

    def search_staff(self, query: str) -> List[Dict[str, Any]]:
        """Searches staff by name query."""
        if not self.is_trained:
            self.train()
        return self.staff_evaluator.search_staff(query)

    def search_works(self, query: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Searches anime works by title substring or romaji/english with Kana normalization."""
        if not self.is_trained:
            self.train()

        raw_q = query.strip().lower()
        norm_q = normalize_search_text(query)
        results = []
        for work_id, meta in self.works_metadata.items():
            t_ja = str(meta.get("title", ""))
            t_en = str(meta.get("title_en", ""))
            norm_ja = normalize_search_text(t_ja)
            norm_en = normalize_search_text(t_en)

            is_match = (
                (raw_q and (raw_q in t_ja.lower() or raw_q in t_en.lower()))
                or (norm_q and (norm_q in norm_ja or norm_q in norm_en))
            )
            if is_match:
                true_z = self.z_scores.get(work_id, 0.0)
                b_val = self.item_biases.get(work_id, 0.0)
                results.append({
                    "work_id": work_id,
                    "title": meta.get("title", work_id),
                    "title_en": meta.get("title_en", ""),
                    "year": meta.get("year", 0),
                    "anilist_raw_score": meta.get("anilist_mean_score", 0.0),
                    "true_z_score": round(true_z, 2),
                    "deviation_score": round(50.0 + 10.0 * true_z, 1),
                    "z_score_rank": self.work_z_ranks.get(work_id, 0),
                    "debiased_b_i": round(b_val, 2),
                    "director": meta.get("staff", {}).get("director", []),
                    "studio": meta.get("staff", {}).get("studio", []),
                })
        results.sort(key=lambda x: x["true_z_score"], reverse=True)
        return results[:limit]

    def get_work_detail(self, work_id: str) -> Optional[Dict[str, Any]]:
        """Returns comprehensive anime details including staff credits and SHAP attribution."""
        if not self.is_trained:
            self.train()

        meta = self.works_metadata.get(work_id)
        if not meta:
            return None

        year = int(meta.get("year", 2020))
        title = meta.get("title", work_id)
        staff = meta.get("staff", {})
        raw_anilist = float(meta.get("anilist_mean_score", 0.0))
        b_val = float(self.item_biases.get(work_id, 0.0))
        true_z = float(self.z_scores.get(work_id, 0.0))

        # Features & prediction
        feats = self.feature_engineer.extract_features_for_work(
            work_id=work_id,
            release_year=year,
            staff_data=staff,
            all_works_metadata=self.works_metadata,
            z_scores=self.z_scores,
        )

        expl = self.predictor.explain_prediction(feats)
        pred_z = expl["predicted_z"]
        est_b = self.local_z_model.inverse_transform_single(pred_z, year)
        est_score = float(np.clip(self.bias_model.global_mean + est_b, 10.0, 100.0))
        residual = true_z - pred_z

        return {
            "work_id": work_id,
            "title": title,
            "title_en": meta.get("title_en", ""),
            "year": year,
            "anilist_raw_score": round(raw_anilist, 1),
            "debiased_b_i": round(b_val, 2),
            "true_z_score": round(true_z, 3),
            "deviation_score": round(50.0 + 10.0 * true_z, 1),
            "z_score_rank": self.work_z_ranks.get(work_id, 0),
            "predicted_z_score": round(pred_z, 3),
            "predicted_score": round(est_score, 1),
            "pred_score_rank": self.work_pred_ranks.get(work_id, 0),
            "raw_score_rank": self.work_raw_ranks.get(work_id, 0),
            "total_works": len(self.works_metadata),
            "residual": round(residual, 3),
            "performance_verdict": "サプライズ名作 (期待値以上)" if residual > 0.4 else (
                "期待外れ (ポテンシャル未達)" if residual < -0.4 else "概ねスタッフ前評判通り"
            ),
            "staff": staff,
            "base_z": round(expl["base_value"], 3),
            "top_positive_factors": expl["top_positive"],
            "top_negative_factors": expl["top_negative"],
            "all_contributions": expl["contributions"],
        }
