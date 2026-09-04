"""
Bangumi API client for anime subject search and staff extraction.
Uses Bangumi API v0 (https://api.bgm.tv).
"""

import json
import logging
import os
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

USER_AGENT = "AnimeEvaluate/1.0 (https://github.com/animeevaluate)"
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "bangumi_cache")


def normalize_bangumi_title(text: str) -> str:
    """Normalizes title by removing brackets, punctuation, common prefixes/suffixes for robust comparison."""
    if not text:
        return ""
    t = re.sub(r"[\(（\[【].*?[\)）\]】]", " ", text)
    t = re.sub(r"^(劇場版|映画|アニメ|TVアニメ|OVA)\s*", "", t)
    t = t.replace("／", "/").replace("～", "~").replace("☆", "").replace("★", "")
    t = re.sub(r"[\s\:\-\_・]+", " ", t).strip().lower()
    return t


def extract_distinct_subtitles(text: str) -> List[str]:
    """Extracts distinctive subtitle or arc keywords (e.g. レゼ篇, あの日にかえりたい, 熱闘編, SUPER)."""
    if not text:
        return []
    words = re.findall(r"[\u3040-\u30ff\u4e00-\u9faf0-9a-zA-Z]{2,}(?:篇|編|巻|期)?", text)
    stopwords = {"劇場版", "映画", "アニメ", "シリーズ", "テレビ", "スペシャル", "第", "期", "the", "movie", "ova", "tv"}
    return [w for w in words if w.lower() not in stopwords and len(w) >= 2]


class BangumiClient:
    """Client for querying Bangumi v0 API to fetch anime staff credits."""

    def __init__(self, cache_dir: str = CACHE_DIR, request_delay: float = 0.25):
        self.cache_dir = cache_dir
        self.request_delay = request_delay
        self.headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        os.makedirs(self.cache_dir, exist_ok=True)

    def _http_get(self, url: str) -> Optional[Any]:
        """Performs HTTP GET with error handling and delay."""
        req = urllib.request.Request(url, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=12) as res:
                if res.status == 200:
                    data = json.loads(res.read().decode("utf-8"))
                    time.sleep(self.request_delay)
                    return data
        except Exception as e:
            logger.debug(f"Bangumi GET error for {url}: {e}")
        return None

    def _http_post(self, url: str, payload: Dict[str, Any]) -> Optional[Any]:
        """Performs HTTP POST with error handling and delay."""
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers=self.headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=12) as res:
                if res.status == 200:
                    data = json.loads(res.read().decode("utf-8"))
                    time.sleep(self.request_delay)
                    return data
        except Exception as e:
            logger.debug(f"Bangumi POST error for {url}: {e}")
        return None

    def search_subject(
        self,
        title: str,
        year: Optional[int] = None,
        episodes: Optional[int] = None,
        format_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Searches Bangumi for anime subject matching title, year, format, and episode count.
        Uses POST /v0/search/subjects with type=[2] (Anime) with strict year & remake protection.
        """
        clean_title = re.sub(r"[\s\:\-\_☆★~～]+", " ", title).strip()
        cache_key = f"search_{re.sub(r'[^a-zA-Z0-9_\u3040-\u30ff\u4e00-\u9faf]', '', clean_title)}_{year or 0}.json"
        cache_file = os.path.join(self.cache_dir, cache_key)

        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cached_item = json.load(f)
                    if cached_item and isinstance(cached_item, dict):
                        # Invalidate stale cache if year discrepancy is >= 3 years
                        c_date = cached_item.get("date", "")
                        if year and c_date and len(c_date) >= 4 and c_date[:4].isdigit():
                            c_year = int(c_date[:4])
                            if abs(c_year - year) >= 3:
                                cached_item = None
                    if cached_item:
                        return cached_item
            except Exception:
                pass

        payload = {
            "keyword": clean_title,
            "filter": {
                "type": [2]  # Anime
            }
        }
        res = self._http_post("https://api.bgm.tv/v0/search/subjects", payload)
        if not res or not res.get("data"):
            # Fallback query with raw title
            payload["keyword"] = title.strip()
            res = self._http_post("https://api.bgm.tv/v0/search/subjects", payload)

        candidates = res.get("data", []) if res else []
        if not candidates:
            return None

        norm_query = normalize_bangumi_title(title)
        query_subtitles = extract_distinct_subtitles(title)

        best_match = None
        best_score = -999.0

        for c in candidates:
            score = 0.0
            c_name = c.get("name", "")
            c_name_cn = c.get("name_cn", "")
            c_date = c.get("date", "")
            c_eps = c.get("eps", 0)

            norm_c_name = normalize_bangumi_title(c_name)
            norm_c_cn = normalize_bangumi_title(c_name_cn)

            # 1. Title match (Exact and Normalized)
            if norm_query and (norm_query == norm_c_name or norm_query == norm_c_cn):
                score += 70.0
            elif norm_query and (norm_query in norm_c_name or norm_c_name in norm_query or norm_query in norm_c_cn or norm_c_cn in norm_query):
                score += 40.0
            elif clean_title.lower() in c_name.lower() or c_name.lower() in clean_title.lower():
                score += 30.0

            # Subtitle / Arc matching bonus/penalty
            for sub in query_subtitles:
                if len(sub) >= 2:
                    if sub in c_name or (c_name_cn and sub in c_name_cn):
                        score += 35.0
                    else:
                        score -= 20.0

            # 2. Strict Year Match & Remake Protection
            if year:
                if c_date and len(c_date) >= 4 and c_date[:4].isdigit():
                    c_year = int(c_date[:4])
                    diff = abs(c_year - year)
                    if diff == 0:
                        score += 60.0
                    elif diff == 1:
                        score += 30.0
                    elif diff == 2:
                        score += 5.0
                    else:
                        # Heavy disqualifying penalty for year mismatch (prevents remakes matching originals)
                        score -= 50.0 * diff
                else:
                    score -= 5.0

            # 3. Format / Episode Compatibility
            is_movie_or_ova = (format_type in ("MOVIE", "OVA", "SPECIAL")) or (episodes == 1)
            is_tv = (format_type == "TV") or (episodes and episodes >= 10)

            if is_movie_or_ova:
                if c_eps and c_eps > 4:
                    score -= 60.0
                elif c_eps == 1:
                    score += 20.0
                if "劇場版" in c_name or "映画" in c_name or "OVA" in c_name:
                    score += 25.0

            if is_tv:
                if c_eps == 1 and ("劇場版" in c_name or "映画" in c_name):
                    score -= 60.0
                elif episodes and c_eps and episodes == c_eps:
                    score += 30.0
                elif episodes and c_eps and abs(episodes - c_eps) <= 2:
                    score += 15.0

            if score > best_score:
                best_score = score
                best_match = c

        # Only accept candidates meeting high-confidence threshold
        if best_match and best_score >= 40.0:
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(best_match, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return best_match

        # Do NOT fallback to candidates[0] when match is poor
        return None

    def get_subject_persons(self, subject_id: int) -> List[Dict[str, Any]]:
        """Fetches staff / persons for subject using GET /v0/subjects/{id}/persons."""
        cache_file = os.path.join(self.cache_dir, f"persons_{subject_id}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        data = self._http_get(f"https://api.bgm.tv/v0/subjects/{subject_id}/persons")
        if data is not None and isinstance(data, list):
            try:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            return data
        return []

    def fetch_anime_staff(
        self,
        title: str,
        year: Optional[int] = None,
        episodes: Optional[int] = None,
        format_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Fetches structured staff for anime title.
        Returns dictionary matching AnimeEvaluate schema:
          - director: List[str]
          - series_comp: List[str]
          - char_design: List[str]
          - sakkan: List[str]
          - genga: List[Dict[str, Any]] (name, ep_ratio/weight)
          - unit_director: List[str]
          - music: List[str]
          - art_dir: List[str]
          - studio: List[str]
          - bangumi_id: Optional[int]
        """
        match = self.search_subject(title, year=year, episodes=episodes, format_type=format_type)
        if not match:
            return {}

        subject_id = match.get("id")
        if not subject_id:
            return {}

        persons = self.get_subject_persons(subject_id)
        if not persons:
            return {}

        staff: Dict[str, Any] = {
            "director": [],
            "series_comp": [],
            "char_design": [],
            "sakkan": [],
            "genga": [],
            "unit_director": [],
            "music": [],
            "art_dir": [],
            "studio": [],
            "bangumi_id": subject_id,
            "bangumi_name": match.get("name"),
        }

        genga_set = set()
        seen_roles = {k: set() for k in staff if isinstance(staff[k], list)}

        for p in persons:
            name = p.get("name", "").strip()
            relation = p.get("relation", "").strip()
            if not name or not relation:
                continue

            # 1. Director
            if relation in ("总导演", "导演"):
                if name not in seen_roles["director"]:
                    staff["director"].append(name)
                    seen_roles["director"].add(name)

            # 2. Series Comp / Script
            elif relation in ("系列构成", "脚本"):
                if name not in seen_roles["series_comp"]:
                    staff["series_comp"].append(name)
                    seen_roles["series_comp"].add(name)

            # 3. Character Design
            elif relation in ("人物设定", "人物原案"):
                if name not in seen_roles["char_design"]:
                    staff["char_design"].append(name)
                    seen_roles["char_design"].add(name)

            # 4. Animation Director (Sakkan)
            elif relation in ("总作画监督", "作画监督", "动作作画监督", "机械作画监督", "角色作画监督"):
                if name not in seen_roles["sakkan"]:
                    staff["sakkan"].append(name)
                    seen_roles["sakkan"].add(name)

            # 5. Key Animators (Genga)
            elif relation == "原画":
                if name not in genga_set:
                    genga_set.add(name)
                    staff["genga"].append({"name": name, "ep_ratio": 1.0, "relation": "原画"})
            elif relation == "第二原画":
                if name not in genga_set:
                    genga_set.add(name)
                    staff["genga"].append({"name": name, "ep_ratio": 0.5, "relation": "第二原画"})

            # 6. Unit Director / Storyboard
            elif relation in ("分镜", "演出", "副导演"):
                if name not in seen_roles["unit_director"]:
                    staff["unit_director"].append(name)
                    seen_roles["unit_director"].add(name)

            # 7. Music (新設)
            elif relation == "音乐":
                if name not in seen_roles["music"]:
                    staff["music"].append(name)
                    seen_roles["music"].add(name)

            # 8. Art Director (新設)
            elif relation in ("美术监督", "美术设计", "背景美术"):
                if name not in seen_roles["art_dir"]:
                    staff["art_dir"].append(name)
                    seen_roles["art_dir"].add(name)

            # 9. Studio
            elif relation == "动画制作":
                if name not in seen_roles["studio"]:
                    staff["studio"].append(name)
                    seen_roles["studio"].add(name)

        return staff
