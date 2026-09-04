"""
Automated Monthly Pipeline Update Script for CreditDB.
Executed by GitHub Actions or manually to:
1. Harvest latest anime & ratings from AniList & Bangumi APIs.
2. Re-train the Bayesian quality decomposition model & GBDT predictor.
3. Re-export all static datasets into creditdb/docs/data/ for GitHub Pages.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path

# Dynamically locate project root
cur = Path(__file__).resolve().parent
ROOT_DIR = cur.parent.parent if cur.parent.name == "creditdb" else cur.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from animeevaluate.data.bulk_collector import BulkDataCollector
try:
    from creditdb.scripts.export_static_data import export_all
except ImportError:
    from scripts.export_static_data import export_all


def update_creditdb():
    print("=" * 70)
    print("  CreditDB: 月次自動更新パイプライン開始")
    print("=" * 70)

    # 1. Check & harvest latest entries from AniList API
    print("\n[Step 1/3] AniList & Bangumi API から最新アニメ・レビューを巡回中...")
    try:
        collector = BulkDataCollector(data_dir=ROOT_DIR / "data")
        collector.harvest_all(target_years=range(2024, 2027), min_score=60.0)
        print("  -> 最新データの巡回・蓄積が完了しました。")
    except Exception as e:
        print(f"  [WARN] 外部APIからの収集に失敗またはスキップしました ({e})。既存データで再学習を続行行します。")

    # 2. Re-train and re-export static data
    print("\n[Step 2/3] モデル再学習および静的JSONデータのエクスポート中...")
    export_all()

    print("\n[Step 3/3] CreditDB のデータ更新が正常に完了しました。")
    print("=" * 70)


if __name__ == "__main__":
    update_creditdb()
