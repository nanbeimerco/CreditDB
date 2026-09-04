"""
Static Data Exporter for CreditDB v1.1.0.
Generates lightweight static JSON files for GitHub Pages and Electron:
- docs/data/summary.json
- docs/data/works.json (all 5,452 works with staff [{name, rt, ct}])
- docs/data/leaderboards.json (role-specific rankings with tiers)
- docs/data/profiles.json (staff profiles with overall and role tiers)
"""

from __future__ import annotations
import datetime
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from animeevaluate.pipeline import AnimePipeline


def get_tier_info(deviation_score: float, rank: int, total: int) -> dict:
    pct = (rank / total) * 100.0 if total > 0 else 100.0
    if deviation_score >= 70.0:
        tier = "S+"
    elif deviation_score >= 65.0:
        tier = "S"
    elif deviation_score >= 60.0:
        tier = "A+"
    elif deviation_score >= 55.0:
        tier = "A"
    elif deviation_score >= 50.0:
        tier = "B+"
    elif deviation_score >= 45.0:
        tier = "B"
    elif deviation_score >= 40.0:
        tier = "C"
    else:
        tier = "D"
    return {"tier": tier, "percentile": round(pct, 2)}


def get_staff_tier(rank: int, total: int) -> str:
    if total <= 0 or rank <= 0:
        return "-"
    pct = (rank / total) * 100.0
    if pct <= 2.3:
        return "S+"
    elif pct <= 6.7:
        return "S"
    elif pct <= 15.9:
        return "A+"
    elif pct <= 30.9:
        return "A"
    elif pct <= 50.0:
        return "B+"
    elif pct <= 70.0:
        return "B"
    elif pct <= 85.0:
        return "C"
    else:
        return "D"


def export_all():
    print("=" * 60)
    print("CreditDB v1.1.0: 静的データエクスポート開始")
    print("=" * 60)

    pipeline = AnimePipeline(data_dir=ROOT_DIR / "data")
    print("[1/4] モデルとデータセットをロード & 訓練中...")
    pipeline.train()

    total_works = len(pipeline.works_metadata)
    total_staff = pipeline.staff_evaluator.total_staff_count
    print(f"  -> 総作品数: {total_works}, 総スタッフ数: {total_staff}")

    # Automatically detect target data directory
    if (ROOT_DIR / "creditdb" / "docs" / "data").exists():
        output_dir = ROOT_DIR / "creditdb" / "docs" / "data"
    elif (ROOT_DIR / "docs" / "data").exists():
        output_dir = ROOT_DIR / "docs" / "data"
    else:
        output_dir = ROOT_DIR / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Leaderboards (All staff, compact format, client-side sortable)
    print("\n[2/4] リーダーボード (leaderboards.json) を生成中 (全スタッフ完全収録)...")
    roles = ["all", "director", "series_comp", "char_design", "sakkan", "genga", "unit_director", "music", "art_dir"]
    leaderboards = {}

    for r in roles:
        r_arg = None if r == "all" else r
        r_total = int(pipeline.staff_evaluator.role_staff_counts.get(r, total_staff) if r != "all" else total_staff)
        lb_rating = pipeline.staff_evaluator.get_leaderboard(role=r_arg, sort_by="rating", limit=100000)
        cum_ranks = pipeline.staff_evaluator.role_cumulative_ranks.get(r, {}) if r != "all" else pipeline.staff_evaluator.cumulative_ranks

        role_items = []
        for it in lb_rating:
            name = it["name"]
            r_rk = it["rank"]
            c_rk = cum_ranks.get(name, r_rk)
            r_tier = get_staff_tier(r_rk, r_total)
            c_tier = get_staff_tier(c_rk, r_total)

            role_items.append({
                "n": name,
                "w": it["works_count"],
                "r": round(float(it["bayesian_rating"]), 3),
                "z": round(float(it["career_cumulative_z"]), 2),
                "rk": r_rk,
                "ck": c_rk,
                "rt": r_tier,
                "ct": c_tier,
                "bt": it.get("best_work_title", "") or "",
                "by": int(it.get("best_work_year", 0)),
                "bz": round(float(it.get("best_work_z", 0)), 2),
            })

        leaderboards[r] = {
            "items": role_items,
            "total_count": r_total,
        }

    lb_file = output_dir / "leaderboards.json"
    with open(lb_file, "w", encoding="utf-8") as f:
        json.dump(leaderboards, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {lb_file} (サイズ: {lb_file.stat().st_size / 1024 / 1024:.2f} MB)")

    # 2. Works data with staff tiers
    print("\n[3/4] 作品データ (works.json) を生成中 (各スタッフの部門別Tier付与)...")
    comp_table = pipeline.get_comparison_table()

    # Pre-build fast lookup for staff tiers by role
    # staff_role_tiers: (name, role) -> (rating_tier, cum_tier)
    role_tier_cache = {}
    for r in ["director", "series_comp", "char_design", "sakkan", "genga", "unit_director", "music", "art_dir"]:
        r_total = pipeline.staff_evaluator.role_staff_counts.get(r, 0)
        r_ranks = pipeline.staff_evaluator.role_ranks.get(r, {})
        r_cum_ranks = pipeline.staff_evaluator.role_cumulative_ranks.get(r, {})
        for name, rk in r_ranks.items():
            c_rk = r_cum_ranks.get(name, 0)
            t_r = get_staff_tier(rk, r_total)
            t_c = get_staff_tier(c_rk, r_total)
            role_tier_cache[(name, r)] = (t_r, t_c)

    works_list = []
    for item in comp_table:
        wid = item["work_id"]
        meta = pipeline.works_metadata.get(wid, {})
        dev_score = float(item["deviation_score"])
        dev_rank = int(item["z_score_rank"])
        raw_score = float(item["anilist_raw_score"])
        raw_rank = int(item["raw_score_rank"])
        tier_info = get_tier_info(dev_score, dev_rank, total_works)

        raw_staff = meta.get("staff", {})
        compact_staff = {}
        for r in ["director", "series_comp", "char_design", "sakkan", "unit_director", "music", "art_dir"]:
            val = raw_staff.get(r, [])
            if isinstance(val, str):
                val = [val] if val else []
            s_objs = []
            for n in val:
                n = str(n).strip()
                if not n:
                    continue
                tr, tc = role_tier_cache.get((n, r), ("-", "-"))
                s_objs.append({"name": n, "rt": tr, "ct": tc})
            if s_objs:
                compact_staff[r] = s_objs

        # Studio
        studios = raw_staff.get("studio", [])
        if isinstance(studios, str):
            studios = [studios]
        compact_staff["studio"] = [str(x).strip() for x in studios if x]

        # Genga
        genga_val = raw_staff.get("genga", [])
        g_objs = []
        if isinstance(genga_val, list):
            for g in genga_val:
                if isinstance(g, str):
                    gn = g.strip()
                elif isinstance(g, dict) and g.get("name"):
                    gn = str(g["name"]).strip()
                else:
                    continue
                if gn:
                    tr, tc = role_tier_cache.get((gn, "genga"), ("-", "-"))
                    g_objs.append({"name": gn, "rt": tr, "ct": tc})
        if g_objs:
            compact_staff["genga"] = g_objs[:15]

        works_list.append({
            "id": wid,
            "title": item["title"],
            "title_en": meta.get("title_en", ""),
            "year": int(item["year"]),
            "deviation_score": dev_score,
            "deviation_rank": dev_rank,
            "anilist_raw_score": raw_score,
            "raw_rank": raw_rank,
            "tier": tier_info["tier"],
            "percentile": tier_info["percentile"],
            "staff": compact_staff,
        })

    works_list.sort(key=lambda x: x["deviation_score"], reverse=True)

    works_file = output_dir / "works.json"
    with open(works_file, "w", encoding="utf-8") as f:
        json.dump(works_list, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {works_file} (サイズ: {works_file.stat().st_size / 1024 / 1024:.2f} MB)")

    # 3. Staff Profiles with overall & role tiers
    print("\n[4/4] スタッフ詳細プロファイル (profiles.json) を生成中...")
    profiles = {}
    active_names = set()
    for r in roles:
        r_items = leaderboards[r]["items"]
        for it in r_items[:300]:
            active_names.add(it["n"])
        cum_sorted = sorted(r_items, key=lambda x: x["ck"])
        for it in cum_sorted[:300]:
            active_names.add(it["n"])

    print(f"  -> 収録スタッフ数: {len(active_names)} 名")
    for name in active_names:
        prof = pipeline.staff_evaluator.get_staff_profile(name)
        if prof:
            ov_r_tier = get_staff_tier(prof["overall_rank"], total_staff)
            ov_c_tier = get_staff_tier(prof["cumulative_rank"], total_staff)

            role_stats_with_tiers = []
            for st in prof.get("all_role_stats", []):
                r = st["role"]
                rt = get_staff_tier(st["rating_rank"], st["role_total"])
                ct = get_staff_tier(st["cumulative_rank"], st["role_total"])
                role_stats_with_tiers.append({
                    "role": r,
                    "works_count": st["works_count"],
                    "bayesian_rating": st["bayesian_rating"],
                    "career_cumulative_z": st["cumulative_z"],
                    "rating_rank": st["rating_rank"],
                    "cumulative_rank": st["cumulative_rank"],
                    "role_total": st["role_total"],
                    "rating_tier": rt,
                    "cum_tier": ct,
                })

            profiles[name] = {
                "name": prof["name"],
                "bayesian_rating": prof["bayesian_rating"],
                "career_cumulative_z": prof["career_cumulative_z"],
                "overall_rating_tier": ov_r_tier,
                "overall_cum_tier": ov_c_tier,
                "total_works": prof["total_works"],
                "overall_rank": prof["overall_rank"],
                "cumulative_rank": prof["cumulative_rank"],
                "primary_role": prof["primary_role"],
                "all_role_stats": role_stats_with_tiers,
                "best_works": prof["best_works"],
                "career_trajectory": prof["career_trajectory"],
            }

    profiles_file = output_dir / "profiles.json"
    with open(profiles_file, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False, separators=(",", ":"))
    print(f"  -> {profiles_file} (サイズ: {profiles_file.stat().st_size / 1024 / 1024:.2f} MB)")

    # 4. Summary
    years = [w["year"] for w in works_list if w["year"] > 1900]
    summary = {
        "title": "CreditDB",
        "version": "1.1.0",
        "description": "アニメ作品・偏差値・制作陣能力評価 Web図鑑",
        "total_works": total_works,
        "total_staff": total_staff,
        "year_min": min(years) if years else 1960,
        "year_max": max(years) if years else 2026,
        "updated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    summary_file = output_dir / "summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"  -> {summary_file}")

    print("\nCreditDB v1.1.0 静的データのエクスポートが完了しました。")


if __name__ == "__main__":
    export_all()
