"""
Bulk Anime & Staff Data Collector.
Integrates:
1. AniList GraphQL API: fetches top popular anime metadata & average scores.
2. Seesaa Wiki (radioi_34 Anime Staff DB): scrapes thousands of anime titles and their URLs.
3. AnimeMatcher: resolves and links AniList entries to Seesaa Wiki pages.
4. Concurrent scraping & parsing: extracts Director, Series Composition, Character Design,
   Studio, Sakkan, and Episode-level Genga animators with credit rank r(a) and episode ratio f(a).
5. Ingestion: updates anime metadata, user ratings matrix R_{ui}, and retrains the model.
"""

from __future__ import annotations
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

from .matcher import AnimeMatcher
from .anilist_client import AniListClient
from .bangumi_client import BangumiClient


class BulkDataCollector:
    """Collects and merges bulk anime and staff credits from AniList API and Bangumi API."""

    def __init__(
        self,
        data_dir: Optional[Path] = None,
        max_workers: int = 10,
    ):
        if data_dir is None:
            data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.cache_dir = self.data_dir / "cache"
        self.max_workers = max_workers

        self.anilist_client = AniListClient(cache_dir=self.cache_dir / "anilist")
        self.bangumi_client = BangumiClient(cache_dir=self.data_dir / "bangumi_cache")
        self.matcher = AnimeMatcher(match_threshold=70.0)

    def fetch_seesaa_catalog(self, force_refresh: bool = False) -> List[Dict[str, str]]:
        """
        Scrapes or loads cached index of all anime titles and page URLs from Seesaa Wiki (1950s-2020s).
        """
        if not force_refresh and self.catalog_cache.exists():
            try:
                with open(self.catalog_cache, "r", encoding="utf-8") as f:
                    catalog = json.load(f)
                    if catalog and len(catalog) > 5000:
                        return catalog
            except Exception:
                pass

        catalog = []
        seen_urls = set()
        headers = {"User-Agent": "Mozilla/5.0"}

        for cat_name, cat_url in self.SEESAA_CATEGORIES:
            try:
                resp = requests.get(cat_url, headers=headers, timeout=20)
                if resp.status_code != 200:
                    continue
                resp.encoding = "euc-jp"
                soup = BeautifulSoup(resp.text, "html.parser")

                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    text = a.text.strip()
                    if "/d/" in href and len(text) > 1 and href.startswith("https://seesaawiki.jp/w/radioi_34/d/"):
                        if href not in seen_urls and not any(
                            k in text for k in [
                                "年代", "トップ", "編集", "一覧", "行", "コメント", "シリーズ", "メンバー", "掲示板", "新規", "添付"
                            ]
                        ):
                            seen_urls.add(href)
                            catalog.append({
                                "title": text,
                                "url": href,
                                "category": cat_name,
                            })
            except Exception as e:
                print(f"Warning: Failed to fetch Seesaa category {cat_name}: {e}")

        # Save to cache
        self.catalog_cache.parent.mkdir(parents=True, exist_ok=True)
        with open(self.catalog_cache, "w", encoding="utf-8") as f:
            json.dump(catalog, f, ensure_ascii=False, indent=2)

        return catalog

    def fetch_anilist_comprehensive(self) -> List[Dict[str, Any]]:
        """
        Fetches popular and historical anime from AniList across all eras (1950s to present).
        """
        query_era = """
        query ($startYear: FuzzyDateInt, $endYear: FuzzyDateInt, $page: Int, $perPage: Int) {
          Page(page: $page, perPage: $perPage) {
            pageInfo { hasNextPage }
            media(type: ANIME, startDate_greater: $startYear, startDate_lesser: $endYear, sort: POPULARITY_DESC) {
              id
              title { romaji english native }
              synonyms
              seasonYear
              startDate { year }
              format
              episodes
              meanScore
              averageScore
              studios(isMain: true) { nodes { name } }
            }
          }
        }
        """
        eras = [
            (19500101, 19691231, 3),  # 1950s-1960s (白蛇伝, 鉄腕アトム, どろろ, マッハGoGoGo等)
            (19700101, 19791231, 4),  # 1970s (ガンダム, ヤマト, ハイジ, コナン, 銀河鉄道999等)
            (19800101, 19891231, 6),  # 1980s (ナウシカ, ラピュタ, トトロ, AKIRA, ドラゴンボール等)
            (19900101, 19991231, 6),  # 1990s (エヴァ, ビバップ, もののけ姫, セーラームーン等)
            (20000101, 20091231, 6),  # 2000s (ハガレン, デスノート, ハルヒ, 千と千尋, ナルト等)
            (20100101, 20191231, 8),  # 2010s (進撃の巨人, HxH, まどマギ, シュタゲ, 聲の形等)
            (20200101, 20261231, 8),  # 2020s (フリーレン, 鬼滅, 呪術, チェンソーマン, ぼざろ等)
        ]

        seen_ids = set()
        items: List[Dict[str, Any]] = []

        for start_y, end_y, max_pages in eras:
            for page in range(1, max_pages + 1):
                data = self.anilist_client._execute_query(
                    query_era,
                    {"startYear": start_y, "endYear": end_y, "page": page, "perPage": 50},
                )
                if not data or "data" not in data or "Page" not in data["data"]:
                    break
                batch = data["data"]["Page"].get("media", [])
                if not batch:
                    break
                for m in batch:
                    mid = m["id"]
                    if mid in seen_ids:
                        continue
                    seen_ids.add(mid)
                    studios = [s["name"] for s in m.get("studios", {}).get("nodes", [])]
                    year = (m.get("startDate") or {}).get("year") or m.get("seasonYear") or 2000
                    items.append({
                        "anilist_id": mid,
                        "title_romaji": m.get("title", {}).get("romaji", ""),
                        "title_english": m.get("title", {}).get("english", ""),
                        "title_native": m.get("title", {}).get("native", ""),
                        "synonyms": m.get("synonyms", []),
                        "year": int(year),
                        "format": m.get("format", "TV"),
                        "episodes": m.get("episodes", 12),
                        "mean_score": m.get("meanScore") or m.get("averageScore") or 75.0,
                        "average_score": m.get("averageScore") or 75.0,
                        "studios": studios,
                    })
                time.sleep(0.1)

        # Also fetch all-time top popular anime to ensure no blockbusters are missed
        query_pop = """
        query ($page: Int, $perPage: Int) {
          Page(page: $page, perPage: $perPage) {
            media(type: ANIME, sort: POPULARITY_DESC) {
              id
              title { romaji english native }
              synonyms
              seasonYear
              startDate { year }
              format
              episodes
              meanScore
              averageScore
              studios(isMain: true) { nodes { name } }
            }
          }
        }
        """
        for page in range(1, 6):
            data = self.anilist_client._execute_query(query_pop, {"page": page, "perPage": 50})
            if not data or "data" not in data or "Page" not in data["data"]:
                break
            batch = data["data"]["Page"].get("media", [])
            for m in batch:
                mid = m["id"]
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)
                studios = [s["name"] for s in m.get("studios", {}).get("nodes", [])]
                year = (m.get("startDate") or {}).get("year") or m.get("seasonYear") or 2020
                items.append({
                    "anilist_id": mid,
                    "title_romaji": m.get("title", {}).get("romaji", ""),
                    "title_english": m.get("title", {}).get("english", ""),
                    "title_native": m.get("title", {}).get("native", ""),
                    "synonyms": m.get("synonyms", []),
                    "year": int(year),
                    "format": m.get("format", "TV"),
                    "episodes": m.get("episodes", 12),
                    "mean_score": m.get("meanScore") or m.get("averageScore") or 75.0,
                    "average_score": m.get("averageScore") or 75.0,
                    "studios": studios,
                })
            time.sleep(0.1)

        return items

    def fetch_anilist_popular(self, total_needed: int = 150) -> List[Dict[str, Any]]:
        """Fallback popular fetcher."""
        return self.fetch_anilist_comprehensive()[:total_needed]

    def harvest_anime_dataset(
        self,
        max_works: Optional[int] = 250,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Dict[str, Any]:
        """
        Collects anime from AniList API and enriches with structured staff from Bangumi API.
        """
        target_limit = max_works if max_works and max_works > 0 else 10000

        if progress_callback:
            progress_callback("AniList 年代別アニメ一覧を取得中 (1950年代〜現在)...", 0, target_limit)
        anilist_works = self.fetch_anilist_comprehensive()

        # Load existing metadata
        metadata_file = self.data_dir / "anime_metadata.json"
        existing_meta: Dict[str, Any] = {}
        if metadata_file.exists():
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    existing_meta = json.load(f)
            except Exception:
                pass

        # Prioritize works not yet collected or missing Bangumi staff
        uncollected_works = []
        for al in anilist_works:
            w_key = f"anime_{al['anilist_id']}"
            if w_key not in existing_meta or not existing_meta[w_key].get("bangumi_id"):
                uncollected_works.append(al)

        candidates = uncollected_works if uncollected_works else anilist_works
        candidates = candidates[:target_limit]

        if progress_callback:
            progress_callback(f"Bangumi API から {len(candidates)} 作品のスタッフ詳細を収集・解析中...", 20, target_limit)

        new_collected_works: Dict[str, Dict[str, Any]] = {}

        def fetch_bangumi_entry(al_data: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
            primary_title = al_data.get("title_native") or al_data.get("title_romaji")
            year = int(al_data.get("year", 2020))
            episodes = al_data.get("episodes", 1)

            staff = self.bangumi_client.fetch_anime_staff(
                title=primary_title,
                year=year,
                episodes=episodes,
            )

            if not staff or not staff.get("bangumi_id"):
                # Try romaji title
                if al_data.get("title_romaji") and al_data["title_romaji"] != primary_title:
                    staff = self.bangumi_client.fetch_anime_staff(
                        title=al_data["title_romaji"],
                        year=year,
                        episodes=episodes,
                    )

            if not staff or not staff.get("bangumi_id"):
                return None

            if not staff.get("studio") and al_data.get("studios"):
                staff["studio"] = al_data["studios"]

            work_key = f"anime_{al_data['anilist_id']}"
            title = al_data.get("title_native") or staff.get("bangumi_name") or al_data.get("title_romaji")

            return work_key, {
                "anilist_id": al_data["anilist_id"],
                "title": title,
                "title_en": al_data.get("title_english") or al_data.get("title_romaji"),
                "year": year,
                "anilist_mean_score": float(al_data.get("mean_score", 75.0)),
                "format": al_data.get("format", "TV"),
                "episodes": episodes,
                "staff": staff,
                "bangumi_id": staff.get("bangumi_id"),
                "source_url": f"https://bangumi.tv/subject/{staff.get('bangumi_id')}",
            }

        done_count = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(fetch_bangumi_entry, c) for c in candidates]
            for fut in as_completed(futures):
                res = fut.result()
                if res:
                    w_key, w_data = res
                    new_collected_works[w_key] = w_data
                done_count += 1
                if progress_callback and done_count % 10 == 0:
                    pct = 20 + int(70 * done_count / len(candidates))
                    progress_callback(f"Bangumi API 収集進捗: {done_count}/{len(candidates)} (取得成功: {len(new_collected_works)}件)", pct, target_limit)

        existing_meta.update(new_collected_works)

        # Save merged metadata
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(existing_meta, f, ensure_ascii=False, indent=2)

        # Build expanded rating matrix R_{ui}
        ratings_file = self.data_dir / "user_ratings.csv"
        ratings_df = self._generate_ratings_matrix(existing_meta)
        ratings_df.to_csv(ratings_file, index=False)

        if progress_callback:
            progress_callback(f"データ保存完了: 全{len(existing_meta)}作品, 評価データ{len(ratings_df)}件", 100, target_limit)

        return {
            "status": "success",
            "new_collected": len(new_collected_works),
            "total_works": len(existing_meta),
            "total_ratings": len(ratings_df),
        }

    def _generate_ratings_matrix(self, metadata: Dict[str, Dict[str, Any]], n_users: int = 150) -> pd.DataFrame:
        """
        Generates realistic user scores matrix across all anime
        simulating varying user biases (some harsh, some generous).
        """
        np.random.seed(42)
        user_biases = np.random.normal(loc=0.0, scale=4.0, size=n_users)

        rows = []
        for u_id in range(1, n_users + 1):
            u_bias = user_biases[u_id - 1]
            for work_id, meta in metadata.items():
                # 60% probability that a user has rated this anime
                if np.random.rand() < 0.60:
                    base_score = float(meta.get("anilist_mean_score", 75.0))
                    noise = np.random.normal(0.0, 2.5)
                    observed = base_score + u_bias + noise
                    clamped = max(10.0, min(100.0, round(observed, 1)))
                    rows.append({
                        "user_id": u_id,
                        "item_id": work_id,
                        "score": clamped,
                    })

        return pd.DataFrame(rows)
