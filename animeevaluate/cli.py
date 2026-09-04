"""
Command-line Interface for Anime Quality Prediction & Staff Evaluation.
Usage:
    python cli.py --train
    python cli.py --predict "作品名" --year 2024 --director "監督名" --genga "原画1,原画2"
    python cli.py --compare
    python cli.py --staff "スタッフ名"
    python cli.py --leaderboard [director|genga|studio|char_design]
    python cli.py --serve [--port 8000]
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import uvicorn
from animeevaluate.pipeline import AnimePipeline


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Formats a neat markdown-like terminal table."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            # Account for fullwidth characters approximate width
            cell_w = len(str(cell).encode("utf-8")) // 2 + 1 if any(ord(c) > 127 for c in str(cell)) else len(str(cell))
            if cell_w > col_widths[idx]:
                col_widths[idx] = cell_w

    header_line = " | ".join(f"{h:<{col_widths[i]}}" for i, h in enumerate(headers))
    sep_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    row_lines = [
        " | ".join(f"{str(cell):<{col_widths[i]}}" for i, cell in enumerate(row))
        for row in rows
    ]
    return f"{header_line}\n{sep_line}\n" + "\n".join(row_lines)


def main():
    parser = argparse.ArgumentParser(
        description="Anime Latent Quality Predictor & Staff Capability Evaluator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--train", action="store_true", help="Train ALS bias model and GBDT predictor")
    parser.add_argument("--collect", type=int, nargs="?", const=100, help="Bulk collect real anime & staff from Seesaa Wiki & AniList (default: 100)")
    parser.add_argument("--predict", type=str, help="Predict quality for a custom work title")
    parser.add_argument("--year", type=int, default=2024, help="Release year for prediction (default: 2024)")
    parser.add_argument("--director", type=str, default="", help="Director name")
    parser.add_argument("--series_comp", type=str, default="", help="Series composition / screenwriter")
    parser.add_argument("--char_design", type=str, default="", help="Character designer")
    parser.add_argument("--studio", type=str, default="", help="Animation studio")
    parser.add_argument("--genga", type=str, default="", help="Comma-separated key animators (in credit order)")
    parser.add_argument("--compare", action="store_true", help="Display side-by-side comparison with AniList")
    parser.add_argument("--staff", type=str, help="Show capability profile and history for staff member")
    parser.add_argument("--search", type=str, help="Search anime works and staff members by keyword")
    parser.add_argument("--anime", type=str, help="Display detailed anime metadata, full staff credits, and SHAP attribution")
    parser.add_argument("--leaderboard", type=str, nargs="?", const="all", help="Show staff leaderboard by role")
    parser.add_argument("--serve", action="store_true", help="Start Web Dashboard (FastAPI server)")
    parser.add_argument("--port", type=int, default=8000, help="Port for web dashboard (default: 8000)")

    args = parser.parse_args()

    # If run in frozen .exe without args, default to serve and auto-open browser
    if getattr(sys, "frozen", False) and len(sys.argv) <= 1:
        args.serve = True
        import threading
        import time
        import webbrowser

        def _open_browser():
            time.sleep(2.0)
            webbrowser.open(f"http://localhost:{args.port}")

        threading.Thread(target=_open_browser, daemon=True).start()

    if args.serve:
        print(f"Starting Anime Quality Prediction Web Dashboard on http://localhost:{args.port} ...")
        from animeevaluate.web.app import app
        uvicorn.run(app, host="0.0.0.0", port=args.port, reload=False)
        return

    pipeline = AnimePipeline()

    if args.collect:
        from animeevaluate.data.bulk_collector import BulkDataCollector
        print(f"=== Seesaa Wiki & AniList API から最大 {args.collect} 作品のスタッフデータを収集・名寄せ開始 ===")
        collector = BulkDataCollector()
        def on_prog(msg, pct, total):
            print(f"[{pct:3d}%] {msg}")
        stat = collector.harvest_anime_dataset(max_works=args.collect, progress_callback=on_prog)
        print(f"\n収集完了! 新規取得: {stat['new_collected']} 作品, 全登録作品数: {stat['total_works']} 作品, 評点数: {stat['total_ratings']} 件")
        print("モデルを再学習中...")
        res = pipeline.train()
        print(f"再学習完了: RMSE={res['metrics']['rmse']:.4f}, MAE={res['metrics']['mae']:.4f}, Pearson R={res['metrics']['pearson_r']:.4f}")
        return

    # Train if requested or not trained
    print("Initializing & Training Pipeline...")
    res = pipeline.train()
    print(f"Dataset: {res['total_works']} works, {res['total_ratings']} ratings.")
    print(f"Metrics: RMSE={res['metrics']['rmse']:.4f}, MAE={res['metrics']['mae']:.4f}, Pearson R={res['metrics']['pearson_r']:.4f}")

    if args.predict:
        genga_list = [g.strip() for g in args.genga.split(",") if g.strip()]
        staff_input = {
            "director": [args.director] if args.director else [],
            "series_comp": [args.series_comp] if args.series_comp else [],
            "char_design": [args.char_design] if args.char_design else [],
            "studio": [args.studio] if args.studio else [],
            "genga": [{"name": g, "rank": idx + 1, "ep_ratio": 1.0} for idx, g in enumerate(genga_list)],
        }

        pred = pipeline.predict_custom(title=args.predict, release_year=args.year, staff=staff_input)
        print("\n" + "=" * 60)
        print(f"予測結果: 【{pred['title']}】 (公開年: {pred['release_year']})")
        print("=" * 60)
        print(f"予測潜在クオリティ (Zスコア) : {pred['predicted_z']:+.3f}")
        print(f"AniList換算予測スコア        : {pred['predicted_anilist_score']:.1f} / 100")
        print(f"ベース基準値 (Base Z)        : {pred['base_z']:+.3f}")
        print("\n【SHAP 主因分析 - スコア押し上げ要因 (Positive Factors)】:")
        for idx, f in enumerate(pred["top_positive_factors"], start=1):
            print(f"  {idx}. {f['label_ja']} -> SHAP: {f['shap_value']:+.3f} (特徴量値: {f['feature_value']:.2f})")
        print("\n【SHAP 主因分析 - スコア押し下げ要因 (Negative Factors)】:")
        for idx, f in enumerate(pred["top_negative_factors"], start=1):
            print(f"  {idx}. {f['label_ja']} -> SHAP: {f['shap_value']:+.3f} (特徴量値: {f['feature_value']:.2f})")
        print("=" * 60)
        return

    if args.compare:
        print("\n" + "=" * 95)
        print("【AniList 評価 vs バイアス補正値 vs モデル予測値 並列比較テーブル】")
        print("=" * 95)
        comp = pipeline.get_comparison_table()
        headers = ["タイトル", "公開年", "AniList点", "補正実力b_i", "真値Z", "予測値Z", "予測換算", "乖離(残差)", "判定"]
        rows = []
        for item in comp:
            rows.append([
                item["title"],
                str(item["year"]),
                f"{item['anilist_raw_score']:.1f}",
                f"{item['debiased_b_i']:+.2f}",
                f"{item['true_z_score']:+.2f}",
                f"{item['predicted_z_score']:+.2f}",
                f"{item['predicted_score']:.1f}",
                f"{item['residual']:+.2f}",
                item["performance_verdict"],
            ])
        print(format_table(headers, rows))
        print("=" * 95)
        return

    if args.staff:
        profile = pipeline.get_staff_profile(args.staff)
        if not profile:
            print(f"スタッフ '{args.staff}' のデータは見つかりませんでした。")
            matches = pipeline.search_staff(args.staff)
            if matches:
                print("類似候補:", ", ".join(m["name"] for m in matches))
            return

        print("\n" + "=" * 60)
        print(f"スタッフ能力評価プロファイル: 【{profile['name']}】")
        print("=" * 60)
        print(f"ベイジアン総合レーティング S(a) : {profile['bayesian_rating']:+.3f}")
        print(f"参加作品平均潜在スコア Mean(Z) : {profile['raw_mean_z']:+.3f}")
        print(f"キャリア最高スコア Peak(Z)     : {profile['peak_z']:+.3f}")
        print(f"総参加作品数                  : {profile['total_works']} 作")
        print(f"担当役職別参加回数            : {profile['roles']}")
        print("\n【代表作 (Top Works)】:")
        for w in profile["best_works"]:
            print(f"  - {w['work_title']} ({w['year']}) [{w['role']}] : Z = {w['z_score']:+.2f}")
        print("=" * 60)
        return

    if args.search:
        print("\n" + "=" * 70)
        print(f"【検索キーワード: '{args.search}' の検索結果】")
        print("=" * 70)
        works = pipeline.search_works(args.search, limit=15)
        staff = pipeline.search_staff(args.search)

        print(f"\n🎬 アニメ作品 ({len(works)}件):")
        if works:
            headers = ["作品ID", "タイトル", "公開年", "AniList点", "真値Z", "監督", "スタジオ"]
            rows = []
            for w in works:
                rows.append([
                    w["work_id"],
                    w["title"],
                    str(w["year"]),
                    f"{w['anilist_raw_score']:.1f}",
                    f"{w['true_z_score']:+.2f}",
                    ", ".join(w["director"]) or "-",
                    ", ".join(w["studio"]) or "-",
                ])
            print(format_table(headers, rows))
        else:
            print("  該当する作品は見つかりませんでした。")

        print(f"\n👤 制作陣・スタッフ ({len(staff)}件):")
        if staff:
            headers = ["スタッフ名", "主役職", "総合実力S(a)", "参加作品数"]
            rows = []
            for s in staff:
                rows.append([
                    s["name"],
                    ", ".join(s["roles"]) or "-",
                    f"{s['rating']:+.3f}",
                    f"{s['works_count']} 作",
                ])
            print(format_table(headers, rows))
        else:
            print("  該当するスタッフは見つかりませんでした。")
        print("=" * 70)
        return

    if args.anime:
        detail = pipeline.get_work_detail(args.anime)
        if not detail:
            # Try searching by title
            works = pipeline.search_works(args.anime, limit=1)
            if works:
                detail = pipeline.get_work_detail(works[0]["work_id"])

        if not detail:
            print(f"作品 '{args.anime}' の詳細データは見つかりませんでした。")
            return

        print("\n" + "=" * 75)
        print(f"アニメ作品詳細: 【{detail['title']}】 ({detail['year']}年公開)")
        print(f"原題/英題: {detail.get('title_en', '-')}")
        print("=" * 75)
        print(f"AniList素点平均             : {detail['anilist_raw_score']:.1f} / 100")
        print(f"バイアス補正後実力 (b_i)    : {detail['debiased_b_i']:+.2f}")
        print(f"年代補正真値 (Z_i)          : {detail['true_z_score']:+.3f}")
        print(f"GBDTモデル予測値 (Ẑ_i)     : {detail['predicted_z_score']:+.3f}")
        print(f"予測換算スコア              : {detail['predicted_score']:.1f} / 100")
        print(f"乖離 (残差: Z_i - Ẑ_i)     : {detail['residual']:+.3f}")
        print(f"総合判定                    : {detail['performance_verdict']}")

        staff = detail.get("staff", {})
        print("\n【制作陣スタッフ情報 (Seesaa Wiki抽出)】:")
        print(f"  ・監督           : {', '.join(staff.get('director', [])) or '-'}")
        print(f"  ・シリーズ構成/脚本: {', '.join(staff.get('series_comp', [])) or '-'}")
        print(f"  ・キャラデザ     : {', '.join(staff.get('char_design', [])) or '-'}")
        print(f"  ・制作スタジオ   : {', '.join(staff.get('studio', [])) or '-'}")
        print(f"  ・演出/副監督    : {', '.join(staff.get('unit_director', [])) or '-'}")
        print(f"  ・作画監督       : {', '.join(staff.get('sakkan', [])[:10]) or '-'}")
        g_list = staff.get("genga", [])
        print(f"  ・原画 ({len(g_list)}名) :")
        for g in g_list[:15]:
            name = g["name"] if isinstance(g, dict) else str(g)
            rank = f"(順位: {g['rank']})" if isinstance(g, dict) and "rank" in g else ""
            print(f"     - {name} {rank}")
        if len(g_list) > 15:
            print(f"     ... 他 {len(g_list) - 15}名")

        print("\n【TreeSHAP 主因分析 (スコア押し上げ/押し下げ)】:")
        for idx, f in enumerate(detail["top_positive_factors"][:3], start=1):
            print(f"  🟢 押し上げ要因 {idx}: {f['label_ja']} (SHAP: {f['shap_value']:+.3f})")
        for idx, f in enumerate(detail["top_negative_factors"][:3], start=1):
            print(f"  🔴 押し下げ要因 {idx}: {f['label_ja']} (SHAP: {f['shap_value']:+.3f})")
        print("=" * 75)
        return

    if args.leaderboard:
        role_arg = None if args.leaderboard in ["all", "none", ""] else args.leaderboard
        lb = pipeline.get_staff_leaderboard(role=role_arg, min_works=1, limit=20)
        print("\n" + "=" * 80)
        print(f"【スタッフ能力レーティング リーダーボード (役職: {role_arg or '全役職'})】")
        print("=" * 80)
        headers = ["順位", "名前", "主役職", "作品数", "レーティングS(a)", "平均Z", "最高Z", "最高評価作"]
        rows = []
        for idx, row in enumerate(lb, start=1):
            rows.append([
                str(idx),
                row["name"],
                row["role"],
                str(row["works_count"]),
                f"{row['bayesian_rating']:+.3f}",
                f"{row['mean_z']:+.2f}",
                f"{row['peak_z']:+.2f}",
                f"{row['best_work_title']} ({row['best_work_year']})",
            ])
        print(format_table(headers, rows))
        print("=" * 80)
        return

    # Default action if no flag specified: show summary and web command
    print("\n[INFO] 使用可能なオプション:")
    print("  python cli.py --serve            Webダッシュボードを起動 (http://localhost:8000)")
    print("  python cli.py --compare          AniList評価と予測値の並列比較一覧を表示")
    print("  python cli.py --predict 作品名   指定スタッフでの予測とSHAP要因分析")
    print("  python cli.py --staff スタッフ名 スタッフの能力プロファイル・レーティングを表示")
    print("  python cli.py --leaderboard      スタッフランキング一覧を表示")


if __name__ == "__main__":
    main()
