"""
GBDT Quality Prediction and SHAP Factor Attribution Module.
Trains a gradient boosted decision tree (LightGBM) to predict latent quality Z
and calculates TreeSHAP values to attribute credit/penalty to each staff feature.
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False

from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from scipy.stats import pearsonr, spearmanr

try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False


class QualityPredictor:
    """
    Predicts anime latent relative quality score Z from staff features.
    Provides TreeSHAP-based factor attribution for interpretability.
    """

    def __init__(
        self,
        n_estimators: int = 100,
        learning_rate: float = 0.05,
        max_depth: int = 4,
        num_leaves: int = 15,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        min_child_samples: int = 5,
        random_state: int = 42,
    ):
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.num_leaves = num_leaves
        self.subsample = subsample
        self.colsample_bytree = colsample_bytree
        self.min_child_samples = min_child_samples
        self.random_state = random_state

        self.model: Any = None
        self.explainer: Any = None
        self.feature_names: List[str] = []
        self.expected_value: float = 0.0
        self.is_fitted: bool = False

    def fit(
        self,
        X: Union[pd.DataFrame, np.ndarray],
        y: Union[pd.Series, np.ndarray],
        feature_names: Optional[List[str]] = None,
    ) -> "QualityPredictor":
        """
        Trains GBDT regressor on feature matrix X and target y (latent Z).
        """
        if isinstance(X, pd.DataFrame):
            self.feature_names = list(X.columns)
            X_mat = X.values
        else:
            X_mat = np.array(X)
            self.feature_names = feature_names or [f"f_{i}" for i in range(X_mat.shape[1])]

        y_vec = np.array(y).flatten()

        if HAS_LIGHTGBM:
            min_child = min(self.min_child_samples, max(2, len(y_vec) // 5))
            self.model = lgb.LGBMRegressor(
                n_estimators=self.n_estimators,
                learning_rate=self.learning_rate,
                max_depth=self.max_depth,
                num_leaves=self.num_leaves,
                subsample=self.subsample,
                colsample_bytree=self.colsample_bytree,
                min_child_samples=min_child,
                random_state=self.random_state,
                verbose=-1,
            )
            self.model.fit(X_mat, y_vec)
        else:
            self.model = HistGradientBoostingRegressor(
                max_iter=self.n_estimators,
                learning_rate=self.learning_rate,
                max_depth=self.max_depth,
                min_samples_leaf=min(5, max(2, len(y_vec) // 5)),
                random_state=self.random_state,
            )
            self.model.fit(X_mat, y_vec)

        # Initialize SHAP explainer
        if HAS_SHAP and HAS_LIGHTGBM:
            try:
                self.explainer = shap.TreeExplainer(self.model)
                ev = self.explainer.expected_value
                if isinstance(ev, np.ndarray):
                    self.expected_value = float(ev[0])
                else:
                    self.expected_value = float(ev)
            except Exception:
                self.explainer = None
                self.expected_value = float(np.mean(y_vec))
        else:
            self.explainer = None
            self.expected_value = float(np.mean(y_vec))

        self.is_fitted = True
        return self

    def predict(self, X: Union[pd.DataFrame, np.ndarray]) -> np.ndarray:
        """Predicts latent Z score for input features."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted before predict.")
        if isinstance(X, pd.DataFrame):
            X_mat = X[self.feature_names].values
        else:
            X_mat = np.array(X)
        return self.model.predict(X_mat)

    def predict_single(self, feature_dict: Dict[str, float]) -> float:
        """Predicts latent Z for a single work feature dictionary."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted first.")
        feat_vector = np.array([[feature_dict.get(col, 0.0) for col in self.feature_names]])
        return float(self.model.predict(feat_vector)[0])

    def evaluate(self, X: Union[pd.DataFrame, np.ndarray], y: Union[pd.Series, np.ndarray]) -> Dict[str, float]:
        """Calculates regression performance metrics (RMSE, MAE, Pearson R, Spearman rho, R^2)."""
        preds = self.predict(X)
        y_true = np.array(y).flatten()
        rmse = math.sqrt(mean_squared_error(y_true, preds))
        mae = float(mean_absolute_error(y_true, preds))
        r2 = float(r2_score(y_true, preds))

        if len(y_true) > 2 and float(np.std(y_true)) > 1e-6 and float(np.std(preds)) > 1e-6:
            pr, _ = pearsonr(y_true, preds)
            sr, _ = spearmanr(y_true, preds)
        else:
            pr, sr = 0.0, 0.0

        return {
            "rmse": float(rmse),
            "mae": float(mae),
            "r2": float(r2),
            "pearson_r": float(pr),
            "spearman_rho": float(sr),
        }

    def explain_prediction(self, feature_dict: Dict[str, float]) -> Dict[str, Any]:
        """
        Explains single prediction using SHAP values.
        Returns:
            - predicted_z: float
            - base_value: float
            - contributions: list of {feature: str, label_ja: str, value: float, shap_value: float}
        """
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted first.")

        feat_vector = np.array([[feature_dict.get(col, 0.0) for col in self.feature_names]])
        pred_val = float(self.model.predict(feat_vector)[0])

        shap_values: np.ndarray
        if self.explainer is not None:
            raw_shap = self.explainer.shap_values(feat_vector)
            if isinstance(raw_shap, list):
                shap_values = np.array(raw_shap[0]).flatten()
            else:
                shap_values = np.array(raw_shap).flatten()
        else:
            # Fallback pseudo-attribution if SHAP tree explainer is unavailable
            # Use linear proxy proportional to feature importance
            importances = getattr(self.model, "feature_importances_", np.ones(len(self.feature_names)))
            diff = pred_val - self.expected_value
            imp_sum = np.sum(importances) + 1e-6
            shap_values = (importances / imp_sum) * diff

        contributions: List[Dict[str, Any]] = []
        for name, val, sv in zip(self.feature_names, feat_vector[0], shap_values):
            label_ja = self._get_feature_label_ja(name)
            contributions.append({
                "feature": name,
                "label_ja": label_ja,
                "feature_value": float(val),
                "shap_value": float(sv),
            })

        # Sort by absolute SHAP impact
        contributions.sort(key=lambda x: abs(x["shap_value"]), reverse=True)

        return {
            "predicted_z": pred_val,
            "base_value": self.expected_value,
            "contributions": contributions,
            "top_positive": [c for c in contributions if c["shap_value"] > 0][:5],
            "top_negative": [c for c in contributions if c["shap_value"] < 0][:5],
        }

    def get_feature_importances(self) -> List[Dict[str, Any]]:
        """Returns sorted feature importances with Japanese descriptions."""
        if not self.is_fitted:
            raise RuntimeError("Model must be fitted first.")
        imp = getattr(self.model, "feature_importances_", np.zeros(len(self.feature_names)))
        total = float(np.sum(imp)) + 1e-6
        results = []
        for name, val in zip(self.feature_names, imp):
            results.append({
                "feature": name,
                "label_ja": self._get_feature_label_ja(name),
                "importance": float(val),
                "normalized_importance": float(val / total),
            })
        results.sort(key=lambda x: x["importance"], reverse=True)
        return results

    def _get_feature_label_ja(self, feat_name: str) -> str:
        mapping = {
            "genga_weighted_s": "原画陣 加重過去実績実力値 S(a)",
            "genga_top_density": "原画陣 トップタレント比率 (D_top)",
            "genga_max_s": "原画陣 最高実力アニメーター S",
            "genga_total_count": "原画総参加人数",
            "genga_experienced_ratio": "原画過去実績保有率",
            "genga_sum_weights": "原画陣 参加話数比率総和",
            "director_bayesian_s": "監督 総合実力スコア S(a)",
            "director_mean_z": "監督 過去実績平均スコア",
            "director_max_z": "監督 過去最高実績スコア (Peak)",
            "director_past_count": "監督 過去監督作品数",
            "series_comp_bayesian_s": "シリーズ構成 総合実力スコア S(a)",
            "series_comp_mean_z": "シリーズ構成 過去実績平均スコア",
            "series_comp_max_z": "シリーズ構成 過去最高実績スコア",
            "series_comp_past_count": "シリーズ構成 過去作品数",
            "char_design_bayesian_s": "キャラクターデザイン 総合実力スコア S(a)",
            "char_design_mean_z": "キャラクターデザイン 過去実績平均",
            "char_design_max_z": "キャラクターデザイン 過去最高実績",
            "char_design_past_count": "キャラクターデザイン 過去作品数",
            "unit_director_bayesian_s": "演出陣 総合実力スコア S(a)",
            "unit_director_mean_z": "演出陣 過去実績平均",
            "unit_director_max_z": "演出陣 過去最高実績",
            "unit_director_past_count": "演出陣 過去作品数",
            "sakkan_bayesian_s": "作画監督 総合実力スコア S(a)",
            "sakkan_mean_z": "作画監督 過去実績平均スコア",
            "sakkan_max_z": "作画監督 過去最高実績スコア",
            "sakkan_past_count": "作画監督 過去作品数",
            "music_bayesian_s": "音楽 総合実力スコア S(a)",
            "music_mean_z": "音楽 過去実績平均スコア",
            "music_max_z": "音楽 過去最高実績スコア",
            "music_past_count": "音楽 過去作品数",
            "art_dir_bayesian_s": "美術監督 総合実力スコア S(a)",
            "art_dir_mean_z": "美術監督 過去実績平均スコア",
            "art_dir_max_z": "美術監督 過去最高実績スコア",
            "art_dir_past_count": "美術監督 過去作品数",
        }
        return mapping.get(feat_name, feat_name)
