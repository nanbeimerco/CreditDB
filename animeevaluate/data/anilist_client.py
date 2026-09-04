"""
AniList GraphQL API Client.
Collects:
- Anime metadata (format, release year, episode count, averageScore, meanScore, studios)
- User-level rating scores (userId, score) for Item-User bias decomposition.
Includes local file caching and rate limit handling.
"""

from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests


class AniListClient:
    """Client for AniList GraphQL API with local caching."""

    ENDPOINT = "https://graphql.anilist.co"

    def __init__(self, cache_dir: Optional[Union[str, Path]] = None, request_delay: float = 0.7):
        if cache_dir is None:
            cache_dir = Path(__file__).resolve().parent.parent.parent / "data" / "cache" / "anilist"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.request_delay = request_delay
        self.last_request_time = 0.0

    def _get_cache_path(self, key: str) -> Path:
        h = hashlib.md5(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{h}.json"

    def _execute_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        cache_key = json.dumps({"q": query, "v": variables or {}}, sort_keys=True)
        cache_file = self._get_cache_path(cache_key)

        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        # Rate-limiting throttle
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AnimeQualityPredictor/1.0",
        }

        retries = 3
        for attempt in range(retries):
            try:
                self.last_request_time = time.time()
                resp = requests.post(
                    self.ENDPOINT,
                    json={"query": query, "variables": variables or {}},
                    headers=headers,
                    timeout=15,
                )
                if resp.status_code == 429:
                    wait_sec = int(resp.headers.get("Retry-After", 5))
                    time.sleep(wait_sec)
                    continue
                if resp.status_code != 200:
                    return None
                data = resp.json()
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return data
            except Exception:
                if attempt == retries - 1:
                    return None
                time.sleep(1.0)
        return None

    def search_anime(self, title: str) -> Optional[Dict[str, Any]]:
        """Searches for an anime by title and returns its metadata."""
        query = """
        query ($search: String) {
          Media(search: $search, type: ANIME) {
            id
            title {
              romaji
              english
              native
            }
            synonyms
            seasonYear
            startDate {
              year
              month
              day
            }
            format
            episodes
            meanScore
            averageScore
            popularity
            studios(isMain: true) {
              nodes {
                name
              }
            }
          }
        }
        """
        res = self._execute_query(query, {"search": title})
        if res and "data" in res and res["data"] and "Media" in res["data"]:
            media = res["data"]["Media"]
            if media:
                studio_names = [s["name"] for s in media.get("studios", {}).get("nodes", [])]
                year = media.get("seasonYear") or (media.get("startDate", {}) or {}).get("year")
                return {
                    "anilist_id": media["id"],
                    "title_romaji": media.get("title", {}).get("romaji", ""),
                    "title_english": media.get("title", {}).get("english", ""),
                    "title_native": media.get("title", {}).get("native", ""),
                    "synonyms": media.get("synonyms", []),
                    "year": year or 0,
                    "format": media.get("format", "TV"),
                    "episodes": media.get("episodes", 1),
                    "mean_score": media.get("meanScore"),
                    "average_score": media.get("averageScore"),
                    "popularity": media.get("popularity", 0),
                    "studios": studio_names,
                }
        return None

    def fetch_user_scores(self, media_id: int, max_entries: int = 150) -> List[Dict[str, Any]]:
        """
        Fetches user scores for a given mediaId from MediaList.
        Returns list of {'user_id': int, 'score': float}.
        """
        query = """
        query ($mediaId: Int, $perPage: Int) {
          Page(page: 1, perPage: $perPage) {
            mediaList(mediaId: $mediaId, type: ANIME, status: COMPLETED) {
              userId
              score(format: POINT_100)
            }
          }
        }
        """
        res = self._execute_query(query, {"mediaId": media_id, "perPage": min(max_entries, 50)})
        ratings = []
        if res and "data" in res and res["data"] and "Page" in res["data"]:
            items = res["data"]["Page"].get("mediaList", [])
            for item in items:
                sc = item.get("score", 0)
                if sc and sc > 0:
                    ratings.append({"user_id": item["userId"], "score": float(sc)})
        return ratings
