"""
Staff Capability Evaluation and Leaderboard Module.
Analyzes individual staff (directors, key animators, character designers, studios)
to compute their latent capability rating S(a), career trajectory, peak performance,
stability, and role-specific leaderboards.
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


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


class StaffEvaluator:
    """
    Evaluates anime staff capabilities across their filmography using de-biased Z scores.
    """

    def __init__(self, pseudo_count_m: Optional[Union[float, Dict[str, float]]] = None):
        if pseudo_count_m is None:
            self.role_m = dict(DEFAULT_ROLE_M)
        elif isinstance(pseudo_count_m, dict):
            self.role_m = {**DEFAULT_ROLE_M, **pseudo_count_m}
        else:
            self.role_m = {r: float(pseudo_count_m) for r in DEFAULT_ROLE_M}
        self.pseudo_count_m = float(self.role_m.get("all", 6.0))
        self.staff_records: Dict[str, List[Dict[str, Any]]] = {}
        # staff_name -> list of records:
        # [{'work_id': ..., 'work_title': ..., 'year': ..., 'role': ..., 'z_score': ..., 'rank': ..., 'ep_ratio': ...}]
        self.is_built: bool = False

    def get_m(self, role: Optional[str] = None) -> float:
        """Returns role-specific pseudo count m."""
        if not role:
            return float(self.role_m.get("all", 6.0))
        return float(self.role_m.get(role, self.role_m.get("all", 4.0)))

    def build_from_dataset(
        self,
        all_works_metadata: Dict[Union[int, str], Dict[str, Any]],
        z_scores: Dict[Union[int, str], float],
    ) -> "StaffEvaluator":
        """
        Builds staff profiles from works metadata and calculated Z-scores.
        """
        self.staff_records = {}

        for work_id, meta in all_works_metadata.items():
            if work_id not in z_scores:
                continue
            z_val = float(z_scores[work_id])
            year = int(meta.get("year", 0))
            title = meta.get("title", str(work_id))
            staff = meta.get("staff", {})

            # 1. Main roles (excluding studio as requested)
            for role in ["director", "series_comp", "char_design", "unit_director", "sakkan", "music", "art_dir"]:
                names = staff.get(role, [])
                if isinstance(names, str):
                    names = [names]
                elif isinstance(names, (list, tuple)):
                    pass
                else:
                    names = []

                for n in names:
                    if isinstance(n, dict):
                        n = n.get("name", "")
                    n = str(n).strip()
                    if not n:
                        continue
                    if n not in self.staff_records:
                        self.staff_records[n] = []
                    self.staff_records[n].append({
                        "work_id": work_id,
                        "work_title": title,
                        "year": year,
                        "role": role,
                        "z_score": z_val,
                        "rank": 1.0,
                        "ep_ratio": 1.0,
                    })

            # 2. Genga (key animators)
            genga_list = staff.get("genga", [])
            if isinstance(genga_list, list):
                for idx, item in enumerate(genga_list, start=1):
                    if isinstance(item, str):
                        name = item.strip()
                        rank = float(idx)
                        ep_ratio = 1.0
                    elif isinstance(item, dict):
                        name = str(item.get("name", "")).strip()
                        rank = float(item.get("rank", idx))
                        ep_ratio = float(item.get("ep_ratio", 1.0))
                    else:
                        continue
                    if not name:
                        continue
                    if name not in self.staff_records:
                        self.staff_records[name] = []
                    self.staff_records[name].append({
                        "work_id": work_id,
                        "work_title": title,
                        "year": year,
                        "role": "genga",
                        "z_score": z_val,
                        "rank": rank,
                        "ep_ratio": ep_ratio,
                    })

        # Precompute overall ranks, cumulative Z ranks, and role-specific ranks
        all_staff_ratings = []
        all_m = self.get_m("all")
        for name, recs in self.staff_records.items():
            z_vals = [r["z_score"] for r in recs]
            z_sum = sum(z_vals)
            rating = z_sum / (len(z_vals) + all_m)
            role_c: Dict[str, int] = {}
            for r in recs:
                role_c[r["role"]] = role_c.get(r["role"], 0) + 1
            pri_role = max(role_c.items(), key=lambda x: x[1])[0]
            all_staff_ratings.append({
                "name": name,
                "rating": rating,
                "z_sum": z_sum,
                "primary_role": pri_role,
                "roles": set(role_c.keys()),
            })

        all_staff_ratings.sort(key=lambda x: x["rating"], reverse=True)
        self.total_staff_count = len(all_staff_ratings)
        self.overall_ranks = {item["name"]: idx + 1 for idx, item in enumerate(all_staff_ratings)}

        # Precompute career cumulative Z ranks (通算貢献度順)
        all_staff_cumulative = sorted(all_staff_ratings, key=lambda x: x["z_sum"], reverse=True)
        self.cumulative_ranks = {item["name"]: idx + 1 for idx, item in enumerate(all_staff_cumulative)}
        self.staff_cumulative_z = {item["name"]: item["z_sum"] for item in all_staff_ratings}

        # Precompute role-specific ratings, cumulative Z, and ranks
        self.role_ranks: Dict[str, Dict[str, int]] = {}
        self.role_cumulative_ranks: Dict[str, Dict[str, int]] = {}
        self.role_staff_counts: Dict[str, int] = {}
        
        for role in ["director", "series_comp", "char_design", "unit_director", "sakkan", "genga", "music", "art_dir"]:
            role_members = []
            role_m = self.get_m(role)
            for name, recs in self.staff_records.items():
                r_recs = [r for r in recs if r["role"] == role]
                if r_recs:
                    z_vals = [r["z_score"] for r in r_recs]
                    k = len(r_recs)
                    z_sum = float(sum(z_vals))
                    rating = float(z_sum / (k + role_m))
                    role_members.append({
                        "name": name,
                        "works_count": k,
                        "cumulative_z": z_sum,
                        "bayesian_rating": rating,
                    })

            self.role_staff_counts[role] = len(role_members)

            # Sort by role rating
            by_rating = sorted(role_members, key=lambda x: x["bayesian_rating"], reverse=True)
            self.role_ranks[role] = {item["name"]: idx + 1 for idx, item in enumerate(by_rating)}

            # Sort by role cumulative Z
            by_cum = sorted(role_members, key=lambda x: x["cumulative_z"], reverse=True)
            self.role_cumulative_ranks[role] = {item["name"]: idx + 1 for idx, item in enumerate(by_cum)}

        self.is_built = True
        return self

    def get_staff_profile(self, staff_name: str) -> Optional[Dict[str, Any]]:
        """Returns comprehensive capability profile, ranks, and history for a given staff member."""
        if not self.is_built:
            raise RuntimeError("Evaluator must be built first.")

        records = self.staff_records.get(staff_name)
        if not records:
            return None

        # Sort chronologically
        sorted_records = sorted(records, key=lambda r: r["year"])
        z_vals = [r["z_score"] for r in sorted_records]
        work_count = len(z_vals)
        z_sum = float(sum(z_vals))
        bayesian_rating = float(z_sum / (work_count + self.get_m("all")))
        raw_mean = float(np.mean(z_vals))
        peak_z = float(np.max(z_vals))
        std_z = float(np.std(z_vals)) if work_count > 1 else 0.0

        # Count roles
        role_counts: Dict[str, int] = {}
        for r in sorted_records:
            role = r["role"]
            role_counts[role] = role_counts.get(role, 0) + 1

        primary_role = max(role_counts.items(), key=lambda x: x[1])[0]

        overall_rank = self.overall_ranks.get(staff_name, 0)
        cumulative_rank = self.cumulative_ranks.get(staff_name, 0)

        # Department (role) specific metrics
        all_role_stats = []
        for role, count in sorted(role_counts.items(), key=lambda x: x[1], reverse=True):
            r_recs = [r for r in sorted_records if r["role"] == role]
            z_vals = [r["z_score"] for r in r_recs]
            k = len(z_vals)
            z_sum_role = float(sum(z_vals))
            r_rating = float(z_sum_role / (k + self.get_m(role)))
            r_tot = self.role_staff_counts.get(role, 0)
            r_rank = self.role_ranks.get(role, {}).get(staff_name, 0)
            r_cum_rank = self.role_cumulative_ranks.get(role, {}).get(staff_name, 0)

            all_role_stats.append({
                "role": role,
                "works_count": k,
                "cumulative_z": round(z_sum_role, 2),
                "bayesian_rating": round(r_rating, 3),
                "rating_rank": r_rank,
                "cumulative_rank": r_cum_rank,
                "role_total": r_tot,
            })

        pri_stats = all_role_stats[0] if all_role_stats else None
        role_rank = pri_stats["rating_rank"] if pri_stats else 0
        role_cum_rank = pri_stats["cumulative_rank"] if pri_stats else 0
        role_total = pri_stats["role_total"] if pri_stats else 0
        role_cum_z = pri_stats["cumulative_z"] if pri_stats else 0.0
        role_rating = pri_stats["bayesian_rating"] if pri_stats else 0.0

        # Top 3 best works by z_score
        top_works = sorted(sorted_records, key=lambda r: r["z_score"], reverse=True)[:3]
        best_works = [
            {
                "work_title": r["work_title"],
                "work_id": r["work_id"],
                "year": r["year"],
                "role": r["role"],
                "z_score": round(r["z_score"], 3),
            }
            for r in top_works
        ]

        # Timeline
        trajectory = [
            {
                "year": r["year"],
                "work_title": r["work_title"],
                "work_id": r["work_id"],
                "role": r["role"],
                "z_score": round(r["z_score"], 3),
            }
            for r in sorted_records
        ]

        return {
            "name": staff_name,
            "bayesian_rating": round(bayesian_rating, 3),
            "career_cumulative_z": round(z_sum, 2),
            "raw_mean_z": round(raw_mean, 3),
            "peak_z": round(peak_z, 3),
            "std_z": round(std_z, 3),
            "total_works": work_count,
            "overall_rank": overall_rank,
            "cumulative_rank": cumulative_rank,
            "total_staff": self.total_staff_count,
            "primary_role": primary_role,
            "role_rank": role_rank,
            "role_cumulative_rank": role_cum_rank,
            "role_cumulative_z": role_cum_z,
            "role_bayesian_rating": role_rating,
            "role_total": role_total,
            "all_role_stats": all_role_stats,
            "roles": role_counts,
            "best_works": best_works,
            "career_trajectory": trajectory,
        }

    def get_leaderboard(
        self,
        role: Optional[str] = None,
        sort_by: str = "rating",
        min_works: int = 1,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Generates capability leaderboard ranked by Bayesian rating S(a) or cumulative sum Z.
        Args:
            role: Optional role filter
            sort_by: 'rating' (S(a)順) or 'cumulative' (生涯通算累積和ΣZ順)
            min_works: Minimum participated works filter
            limit: Top N results
        """
        if not self.is_built:
            raise RuntimeError("Evaluator must be built first.")

        leaderboard = []
        eff_m = self.get_m(role)
        for name, records in self.staff_records.items():
            if role:
                filtered_records = [r for r in records if r["role"] == role]
            else:
                filtered_records = records

            if len(filtered_records) < min_works:
                continue

            z_vals = [r["z_score"] for r in filtered_records]
            k = len(filtered_records)
            z_sum = float(sum(z_vals))
            rating = float(z_sum / (k + eff_m))
            mean_z = float(np.mean(z_vals))
            peak_z = float(np.max(z_vals))

            best_work = max(filtered_records, key=lambda r: r["z_score"])

            leaderboard.append({
                "name": name,
                "role": role or "all",
                "works_count": k,
                "bayesian_rating": round(rating, 3),
                "career_cumulative_z": round(z_sum, 2),
                "mean_z": round(mean_z, 3),
                "peak_z": round(peak_z, 3),
                "best_work_title": best_work["work_title"],
                "best_work_year": best_work["year"],
                "best_work_z": round(best_work["z_score"], 3),
            })

        if sort_by in ("cumulative", "z_sum"):
            leaderboard.sort(key=lambda x: x["career_cumulative_z"], reverse=True)
        else:
            leaderboard.sort(key=lambda x: x["bayesian_rating"], reverse=True)

        total_len = len(leaderboard)
        for rank_idx, item in enumerate(leaderboard, start=1):
            item["rank"] = rank_idx
            item["total_count"] = total_len
        return leaderboard[:limit]

    def search_staff(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Searches staff members by name substring or exact match."""
        q = query.strip().lower()
        matches = []
        for name in self.staff_records:
            if q in name.lower():
                profile = self.get_staff_profile(name)
                if profile:
                    matches.append({
                        "name": name,
                        "rating": profile["bayesian_rating"],
                        "works_count": profile["total_works"],
                        "roles": list(profile["roles"].keys()),
                    })
        matches.sort(key=lambda x: x["rating"], reverse=True)
        return matches[:limit]
