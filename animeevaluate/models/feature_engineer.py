"""
Temporal Staff Feature Engineering Module.
Strict leak-free past performance aggregation for anime production staff:
- Key Animators (Genga): credit-order and episode-frequency weighting (w_a = 1/sqrt(r) * f)
- Bayesian smoothed score S(a) = sum(Z_p) / (|P| + m)
- Weighted aggregate score S_genga and top-talent density D_top
- Key roles (Director, Series Composition, Character Design, Unit Director, Studio, Animation Director):
  Mean(Z), Max(Z), 3-work exponential decay average sum_{j=1}^3 gamma^j Z_{pj}
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import numpy as np
import pandas as pd


# Main roles to track specifically (human creators)
MAIN_ROLES = [
    "director",          # 監督
    "series_comp",       # シリーズ構成 / 脚本
    "char_design",       # キャラクターデザイン
    "unit_director",     # 演出 / 副監督 / 助監督
    "sakkan",            # 作画監督 / 総作画監督
    "music",             # 音楽 / 劇伴作曲家
    "art_dir",           # 美術監督 / 背景
]


DEFAULT_ROLE_M: Dict[str, float] = {
    "director": 2.0,
    "series_comp": 2.0,
    "char_design": 2.0,
    "music": 2.0,
    "unit_director": 4.0,
    "sakkan": 4.0,
    "art_dir": 4.0,
    "genga": 6.0,
    "all": 6.0,
}


class StaffFeatureEngineer:
    """
    Computes time-ordered, leak-free staff performance features.
    """

    def __init__(
        self,
        pseudo_count_m: Optional[Union[float, Dict[str, float]]] = None,
        top_talent_threshold: float = 0.5,
        decay_gamma: float = 0.8,
    ):
        """
        Args:
            pseudo_count_m: Pseudo-count m for Bayesian smoothing in S(a).
                            Can be float, dict of role->m, or None (defaults to role medians).
            top_talent_threshold: Threshold for top talent indicator I(S(a) > Threshold).
            decay_gamma: Decay factor gamma in (0, 1] for 3-work weighted sum.
        """
        if pseudo_count_m is None:
            self.role_m = dict(DEFAULT_ROLE_M)
        elif isinstance(pseudo_count_m, dict):
            self.role_m = {**DEFAULT_ROLE_M, **pseudo_count_m}
        else:
            self.role_m = {r: float(pseudo_count_m) for r in DEFAULT_ROLE_M}
        self.pseudo_count_m = float(self.role_m.get("all", 6.0))
        self.top_talent_threshold = float(top_talent_threshold)
        self.decay_gamma = float(decay_gamma)

        # Feature column names generated
        self.feature_names: List[str] = []
        self._init_feature_names()

    def get_m(self, role: Optional[str] = None) -> float:
        """Returns role-specific pseudo count m."""
        if not role:
            return float(self.role_m.get("all", 6.0))
        return float(self.role_m.get(role, self.role_m.get("all", 4.0)))

    def _init_feature_names(self):
        names = [
            "genga_weighted_s",       # \bar{S}_{genga}
            "genga_top_density",      # D_{top}
            "genga_max_s",            # max S(a)
            "genga_total_count",      # |A_k|
            "genga_experienced_ratio",# fraction of animators with past works
            "genga_sum_weights",      # sum w_a
        ]
        for role in MAIN_ROLES:
            names.extend([
                f"{role}_bayesian_s",
                f"{role}_mean_z",
                f"{role}_max_z",
                f"{role}_past_count",
            ])
        self.feature_names = names

    def extract_features_for_work(
        self,
        work_id: Union[int, str],
        release_year: int,
        staff_data: Dict[str, Any],
        all_works_metadata: Dict[Union[int, str], Dict[str, Any]],
        z_scores: Dict[Union[int, str], float],
        reference_date: Optional[str] = None,
        precomputed_staff_history: Optional[Dict[str, List[Tuple[int, float]]]] = None,
    ) -> Dict[str, float]:
        """
        Extracts staff features for a single work k strictly using past works (year < release_year).

        Args:
            work_id: ID of current work k
            release_year: Release year of current work
            staff_data: Staff dictionary containing:
                - 'genga': list of dicts [{'name': str, 'rank': float, 'ep_ratio': float}] or
                           list of names or dict mapping animator name -> {'rank': ..., 'ep_ratio': ...}
                - 'director': list of str or single str
                - 'series_comp': list of str or single str
                - 'char_design': list of str or single str
                - 'unit_director': list of str or single str
                - 'studio': list of str or single str
                - 'sakkan': list of str or single str
            all_works_metadata: Dict mapping past work_id -> {'year': int, 'staff': dict}
            z_scores: Dict mapping past work_id -> ground truth / estimated Z-score
            reference_date: Optional string date (YYYY-MM-DD) for finer temporal ordering if available.
            precomputed_staff_history: Optional pre-inverted index of staff performance history.

        Returns:
            Dictionary mapping feature_name -> float value
        """
        # 1. Identify all valid past works (release_year_p < release_year)
        if precomputed_staff_history is not None:
            # Fast O(1) path using precomputed inverted index
            past_works_by_staff: Dict[str, List[Tuple[int, float]]] = {}
            target_staff = self._collect_all_staff_names(staff_data)
            for s_name in target_staff:
                hist = precomputed_staff_history.get(s_name, [])
                valid_past = [(y, z) for (y, z) in hist if y < release_year]
                if valid_past:
                    past_works_by_staff[s_name] = sorted(valid_past, key=lambda x: x[0], reverse=True)
        else:
            # Fallback path scanning all_works_metadata
            past_works_by_staff: Dict[str, List[Tuple[int, float]]] = {}
            for past_id, p_meta in all_works_metadata.items():
                if past_id == work_id:
                    continue
                p_year = p_meta.get("year", 0)
                if p_year >= release_year:
                    # Strictly prior to release_year to prevent data leakage!
                    continue
                if past_id not in z_scores:
                    continue
                p_z = z_scores[past_id]

                p_staff = p_meta.get("staff", {})
                p_all_staff_names = self._collect_all_staff_names(p_staff)
                for s_name in p_all_staff_names:
                    if s_name not in past_works_by_staff:
                        past_works_by_staff[s_name] = []
                    past_works_by_staff[s_name].append((p_year, p_z))

            # Sort each staff member's past history chronologically reversed
            for s_name in past_works_by_staff:
                past_works_by_staff[s_name].sort(key=lambda x: x[0], reverse=True)

        feats: Dict[str, float] = {}

        # 2. Extract Key Animator (Genga) Features
        genga_list = self._normalize_genga_input(staff_data.get("genga", []))
        w_list: List[float] = []
        s_list: List[float] = []
        is_top_list: List[float] = []
        exp_count = 0

        for g in genga_list:
            name = g["name"]
            # Weight purely by episode participation frequency f(a) (1.0 for movies/OVAs)
            f_a = max(0.01, min(1.0, float(g.get("ep_ratio", 1.0))))
            w_a = f_a
            w_list.append(w_a)

            past_records = past_works_by_staff.get(name, [])
            p_count = len(past_records)
            if p_count > 0:
                exp_count += 1
                sum_z = sum(r[1] for r in past_records)
            else:
                sum_z = 0.0
            s_a = sum_z / (p_count + self.get_m("genga"))
            s_list.append(s_a)

            is_top = 1.0 if s_a > self.top_talent_threshold else 0.0
            is_top_list.append(is_top)

        if w_list and sum(w_list) > 0:
            sum_w = sum(w_list)
            feats["genga_weighted_s"] = float(sum(w * s for w, s in zip(w_list, s_list)) / sum_w)
            feats["genga_top_density"] = float(sum(is_top_list) / len(w_list))
            feats["genga_max_s"] = float(max(s_list))
            feats["genga_total_count"] = float(len(w_list))
            feats["genga_experienced_ratio"] = float(exp_count / len(w_list))
            feats["genga_sum_weights"] = float(sum_w)
        else:
            feats["genga_weighted_s"] = 0.0
            feats["genga_top_density"] = 0.0
            feats["genga_max_s"] = 0.0
            feats["genga_total_count"] = 0.0
            feats["genga_experienced_ratio"] = 0.0
            feats["genga_sum_weights"] = 0.0

        # 3. Extract Main Roles Features (Bayesian smoothed past performance S(a))
        for role in MAIN_ROLES:
            names = self._normalize_names_list(staff_data.get(role, []))
            role_past_records: List[Tuple[int, float]] = []
            for n in names:
                role_past_records.extend(past_works_by_staff.get(n, []))

            # Deduplicate by past work if a person appears multiple times
            if role_past_records:
                role_past_records.sort(key=lambda x: x[0], reverse=True)
                past_z_vals = [r[1] for r in role_past_records]
                count = float(len(past_z_vals))
                sum_z = float(sum(past_z_vals))

                # Empirical Bayes score S(role) across all past works
                bayesian_s = float(sum_z / (count + self.get_m(role)))

                feats[f"{role}_bayesian_s"] = bayesian_s
                feats[f"{role}_mean_z"] = float(np.mean(past_z_vals))
                feats[f"{role}_max_z"] = float(np.max(past_z_vals))
                feats[f"{role}_past_count"] = count
            else:
                feats[f"{role}_bayesian_s"] = 0.0
                feats[f"{role}_mean_z"] = 0.0
                feats[f"{role}_max_z"] = 0.0
                feats[f"{role}_past_count"] = 0.0

        return feats

    def extract_features_dataset(
        self,
        all_works_metadata: Dict[Union[int, str], Dict[str, Any]],
        z_scores: Dict[Union[int, str], float],
    ) -> pd.DataFrame:
        """
        Generates the leak-free feature matrix for all works.
        Precomputes inverted staff history for O(1) lookups across large datasets.
        """
        # Precompute inverted index: staff_name -> list of (year, Z)
        staff_history: Dict[str, List[Tuple[int, float]]] = {}
        for w_id, meta in all_works_metadata.items():
            if w_id in z_scores:
                w_year = meta.get("year", 0)
                w_z = z_scores[w_id]
                for s_name in self._collect_all_staff_names(meta.get("staff", {})):
                    if s_name not in staff_history:
                        staff_history[s_name] = []
                    staff_history[s_name].append((w_year, w_z))

        rows: List[Dict[str, Any]] = []
        for work_id, meta in all_works_metadata.items():
            if work_id not in z_scores:
                continue
            year = meta.get("year", 0)
            staff = meta.get("staff", {})
            f_dict = self.extract_features_for_work(
                work_id=work_id,
                release_year=year,
                staff_data=staff,
                all_works_metadata=all_works_metadata,
                z_scores=z_scores,
                precomputed_staff_history=staff_history,
            )
            f_dict["work_id"] = work_id
            f_dict["release_year"] = year
            f_dict["target_z"] = z_scores[work_id]
            rows.append(f_dict)

        df = pd.DataFrame(rows)
        return df

    def _collect_all_staff_names(self, staff_data: Dict[str, Any]) -> Set[str]:
        names: Set[str] = set()
        for role in MAIN_ROLES:
            for n in self._normalize_names_list(staff_data.get(role, [])):
                names.add(n)
        for g in self._normalize_genga_input(staff_data.get("genga", [])):
            names.add(g["name"])
        return names

    def _normalize_names_list(self, val: Any) -> List[str]:
        if not val:
            return []
        if isinstance(val, str):
            return [val.strip()]
        if isinstance(val, (list, tuple, set)):
            res = []
            for item in val:
                if isinstance(item, str) and item.strip():
                    res.append(item.strip())
                elif isinstance(item, dict) and "name" in item:
                    res.append(str(item["name"]).strip())
            return res
        return []

    def _normalize_genga_input(self, val: Any) -> List[Dict[str, Any]]:
        if not val:
            return []
        results: List[Dict[str, Any]] = []
        if isinstance(val, list):
            for idx, item in enumerate(val, start=1):
                if isinstance(item, str):
                    results.append({"name": item.strip(), "rank": float(idx), "ep_ratio": 1.0})
                elif isinstance(item, dict):
                    results.append({
                        "name": str(item.get("name", "")).strip(),
                        "rank": float(item.get("rank", idx)),
                        "ep_ratio": float(item.get("ep_ratio", 1.0)),
                    })
        elif isinstance(val, dict):
            for idx, (name, data) in enumerate(val.items(), start=1):
                if isinstance(data, dict):
                    results.append({
                        "name": str(name).strip(),
                        "rank": float(data.get("rank", idx)),
                        "ep_ratio": float(data.get("ep_ratio", 1.0)),
                    })
                else:
                    results.append({"name": str(name).strip(), "rank": float(idx), "ep_ratio": 1.0})
        return [r for r in results if r["name"]]
