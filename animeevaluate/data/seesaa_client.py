"""
Seesaa Wiki Anime Staff Database (radioi_34) Scraper and Parser.
Extracts:
- Work title, broadcast period / year, total episode count
- Main staff (Director, Series Composition, Character Design, Studio, Unit Director)
- Episode-level staff (Key Animators with credit order r(a) and episode participation ratio f(a), Animation Directors)
Includes disk caching and text normalization.
"""

from __future__ import annotations
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import requests
from bs4 import BeautifulSoup


class SeesaaStaffClient:
    """Scrapes and parses anime staff data from Seesaa Wiki (radioi_34)."""

    BASE_URL = "https://seesaawiki.jp/w/radioi_34/"

    def __init__(self, cache_dir: Optional[Union[str, Path]] = None, request_delay: float = 0.5):
        if cache_dir is None:
            cache_dir = Path(__file__).resolve().parent.parent.parent / "data" / "cache" / "seesaa"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.request_delay = request_delay
        self.last_request_time = 0.0

    def _get_cache_path(self, url: str) -> Path:
        h = hashlib.md5(url.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{h}.html"

    def fetch_page_html(self, url: str) -> Optional[str]:
        """Fetches page HTML with disk caching and EUC-JP decoding."""
        cache_path = self._get_cache_path(url)
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                pass

        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
        }

        try:
            self.last_request_time = time.time()
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code != 200:
                return None
            # Seesaa Wiki pages are typically EUC-JP
            resp.encoding = "euc-jp"
            html_content = resp.text
            with open(cache_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            return html_content
        except Exception:
            return None

    def parse_anime_page(self, html_content: str, source_url: str = "") -> Dict[str, Any]:
        """
        Parses anime details, main staff, and episode-by-episode credits.
        """
        soup = BeautifulSoup(html_content, "html.parser")
        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.split("-")[0].strip()

        user_area = soup.find("div", class_="user-area")
        if not user_area:
            return {"title": title, "year": 0, "staff": {}}

        text_lines = [l.strip() for l in user_area.get_text().split("\n") if l.strip()]

        # 1. Parse Broadcast year & total episodes
        year = self._extract_year(text_lines)
        has_episode_headers = any(
            re.search(r"^(?:第\s*\d+\s*話|#\s*\d+|\d+話|Episode\s*\d+|ACT\s*\d+)", l, re.I)
            for l in text_lines
        )
        if not has_episode_headers:
            total_episodes = 1
        else:
            total_episodes = self._extract_total_episodes(text_lines)

        # 2. Parse Main staff (Director, Series Composition, Character Design, Studio)
        main_staff = self._extract_main_staff(text_lines)

        # 3. Parse Episode by episode credits
        episode_credits = self._extract_episode_credits(text_lines)

        # 4. Aggregate Genga & Sakkan credits
        genga_staff = self._aggregate_genga(episode_credits, total_episodes)
        sakkan_staff = self._aggregate_sakkan(episode_credits)

        combined_sakkan = []
        for s in main_staff.get("sakkan", []) + sakkan_staff:
            if s not in combined_sakkan and len(s) >= 2:
                combined_sakkan.append(s)

        enshutsu_staff = []
        for ep in episode_credits:
            for n in ep.get("conte_enshutsu", []):
                if n not in enshutsu_staff and len(n) >= 2:
                    enshutsu_staff.append(n)
        combined_unit_director = []
        for u in main_staff.get("unit_director", []) + enshutsu_staff:
            if u not in combined_unit_director and len(u) >= 2:
                combined_unit_director.append(u)

        staff_data = {
            "director": main_staff.get("director", []),
            "series_comp": main_staff.get("series_comp", []),
            "char_design": main_staff.get("char_design", []),
            "studio": main_staff.get("studio", []),
            "unit_director": combined_unit_director,
            "sakkan": combined_sakkan,
            "genga": genga_staff,
        }

        return {
            "title": title,
            "year": year,
            "total_episodes": total_episodes,
            "staff": staff_data,
            "source_url": source_url,
        }

    def _extract_year(self, lines: List[str]) -> int:
        for line in lines[:35]:
            # Look for 放送期間: 2020年 or 2020年
            m = re.search(r"(?:放送期間|放送開始|公開年|放送日)?[:：]?\s*(19\d{2}|20\d{2})年", line)
            if m:
                return int(m.group(1))
            m2 = re.search(r"\b(19\d{2}|20\d{2})\b", line)
            if m2 and any(k in line for k in ["放送", "公開", "年"]):
                return int(m2.group(1))
        return 0

    def _extract_total_episodes(self, lines: List[str]) -> int:
        for line in lines[:35]:
            m = re.search(r"全\s*(\d+)\s*話", line)
            if m:
                return int(m.group(1))
        # Estimate from episode count later if not found
        return 12

    COMPANY_EXCLUDES = [
        "スタジオ", "プロダクション", "アニメーション", "フィルム", "じゃんぐるじむ",
        "わあぷ", "アニメアール", "コア", "動画", "仕上", "制作", "背景", "撮影",
        "音響", "ピクチャーズ", "コミックス", "小学館", "集英社", "講談社", "キティ",
        "オフィス", "工房", "グループ", "アトリエ", "デザイン", "メカマン", "ヤマト",
        "エンタテインメント", "ピエロ", "ぴえろ", "サンライズ", "東映", "マッドハウス",
        "ボンズ", "シャフト", "ガイナックス", "トリガー", "ユーフォーテーブル",
    ]

    BAD_TOKENS = [
        "話", "放送", "放映", "サブタイトル", "タイトル", "クール", "パート", "op", "ed",
        "mission", "stage", "act", "episode", "第", "ノンクレジット", "ほか", "他", "連載",
        "原作", "製作", "協力", "委員会", "アバン", "アイキャッチ", "予告", "提供", "監督",
        "脚本", "演出", "コンテ", "作画", "原画", "デザイン", "制作進行", "プロデューサー",
    ]

    def _is_clean_person_name(self, name: str) -> bool:
        name = name.strip()
        if len(name) < 2 or len(name) > 10:
            return False
        # Reject any digits (Arabic or full-width)
        if re.search(r"[\d０-９]", name):
            return False
        # Reject punctuation, colons, slashes, brackets
        if re.search(r"[/:\.・_~〜\-－―=＝#＃@＠\(\)（）\[\]「」『』]", name):
            return False
        # Reject role keywords, department labels, and TV metadata
        name_lower = name.lower()
        for bt in [
            "話", "放送", "放映", "サブタイトル", "タイトル", "クール", "パート", "op", "ed",
            "mission", "stage", "act", "episode", "ノンクレジット", "ほか", "他", "連載",
            "原作", "製作", "制作進行", "プロデューサー", "委員会", "アバン", "アイキャッチ", "予告", "提供",
            "絵コンテ", "コンテ", "演出", "脚本", "作画", "原画", "動画", "美術", "撮影", "音響",
            "効果", "色彩", "仕上", "編集", "制作", "宣伝", "進行", "設定", "デザイン", "デザイナー",
            "プロデュース", "監督", "作監", "総作監", "キャラデザ", "シリーズ構成", "構成", "シナリオ",
            "キャスト", "cast", "文芸", "選曲", "録音", "整音", "特効",
            "アクション", "コンセプト", "アート", "ビジュアル", "エフェクト", "メカニック", "メカ",
            "プロップ", "サブキャラクター", "チーフ", "メイン", "エピソード", "シリーズ", "スーパーバイザー",
            "ディレクター", "アニメーション", "アニメーター", "ピクセル", "vfx", "3dcg", "cg",
            "モデリング", "リギング", "色指定", "検査",
            "series", "director", "directors", "composition", "producer", "producers",
            "designer", "designers", "design", "chief", "assistant", "concept", "action",
            "art", "visual", "effect", "effects", "supervisor", "animation", "animator",
            "animators", "character", "characters", "staff", "credit", "credits",
            "original", "story", "screenplay", "script", "music", "sound", "editing", "editor",
        ]:
            if bt in name_lower:
                return False
        # Reject company / studio names
        for comp in self.COMPANY_EXCLUDES:
            if comp in name:
                return False
        # Must be valid Japanese Kanji / Hiragana / Katakana or Latin
        if not re.match(r"^[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF A-Za-z]+$", name):
            return False
        return True

    def _split_names(self, text: str) -> List[str]:
        """Splits whitespace or comma delimited Japanese staff names and filters out non-names."""
        cleaned = re.sub(r"[*＊]\d+", "", text)
        cleaned = re.sub(r"\[.*?\]", "", cleaned)
        cleaned = re.sub(r"（.*?）", "", cleaned)
        cleaned = re.sub(r"\(.*?\)", "", cleaned)
        cleaned = re.sub(r"「.*?」", "", cleaned)
        cleaned = re.sub(r"『.*?』", "", cleaned)
        raw_parts = re.split(r"[\s\u3000\t,、/・&＆]+", cleaned)
        names = []
        for p in raw_parts:
            p = p.strip()
            if self._is_clean_person_name(p):
                names.append(p)
        return names

    def _extract_main_staff(self, lines: List[str]) -> Dict[str, List[str]]:
        staff: Dict[str, List[str]] = {
            "director": [],
            "series_comp": [],
            "char_design": [],
            "studio": [],
            "unit_director": [],
            "sakkan": [],
        }

        i = 0
        n_lines = len(lines)
        while i < n_lines:
            line = lines[i]
            cleaned = re.sub(r"[*＊]\d+", "", line).strip()
            cleaned = re.sub(r"\[.*?\]", "", cleaned).strip()

            # Check if this is the start of actual episode credits list
            # 1. Episode header like 第1話「...」 or #01 ...
            if re.search(r"^(?:第\s*0?1\s*話|第[０-９\d]+話|#\s*0?1\b|Episode\s*0?1\b|MISSION:\s*0?1\b)\s*[「『\s]", cleaned, re.I):
                break
            # 2. Section header followed by episodes (not an anchor link)
            if cleaned in ["各話リスト", "各話スタッフ", "放映リスト", "放送リスト", "エピソードリスト"]:
                # Check next few lines: if followed by episode headers or table, break!
                has_ep_following = any(
                    re.search(r"^(?:第|#|MISSION:|Episode|\d+話|話数|サブタイトル)", lines[k].strip(), re.I)
                    for k in range(i + 1, min(n_lines, i + 6))
                )
                if has_ep_following:
                    break
                else:
                    i += 1
                    continue

            # Skip standalone section headers
            if cleaned in ["原画", "■原画", "【原画】", "各話スタッフ", "メインスタッフ", "スタッフ", "スタッフクレジット"]:
                i += 1
                continue

            parts = []
            if "：" in cleaned or ":" in cleaned:
                parts = re.split(r"[:：]", cleaned, maxsplit=1)
            else:
                for kw in [
                    "監督", "総監督", "ディレクター", "シリーズ構成", "脚本", "シナリオ",
                    "キャラクターデザイン", "キャラデザ", "キャラクター設計", "キャラクター原案",
                    "作画監督", "総作画監督", "作監", "演出", "絵コンテ",
                    "アニメーション制作", "アニメ制作", "制作協力", "制作会社", "制作スタジオ",
                ]:
                    if cleaned.startswith(kw) and len(cleaned) > len(kw) and cleaned[len(kw)] in " \u3000\t":
                        parts = [kw, cleaned[len(kw):]]
                        break

                # If no inline value, check if line is a role header with names on following lines
                if not parts:
                    clean_hdr = re.sub(r"（.*?）|\(.*?\)|〔.*?〕|\[.*?\]", "", cleaned).strip()
                    sub_r = [r.strip() for r in re.split(r"[・/、&＆]+", clean_hdr) if r.strip()]
                    if sub_r and any(r in [
                        "監督", "総監督", "ディレクター", "シリーズディレクター",
                        "シリーズ構成", "構成", "脚本", "シナリオ",
                        "キャラクターデザイン", "キャラデザ", "キャラクター設計", "キャラクター原案",
                        "総作画監督", "作画監督", "作監", "演出", "助監督", "副監督",
                        "アニメーション制作", "制作", "アニメ制作", "制作協力", "制作会社", "制作スタジオ",
                    ] for r in sub_r):
                        val_names: List[str] = []
                        j = i + 1
                        while j < min(n_lines, i + 6):
                            next_l = re.sub(r"[*＊]\d+", "", lines[j]).strip()
                            if next_l and next_l not in ["×", "・", "―", "-", "─"]:
                                next_l_lower = next_l.lower()
                                # Skip English translation headers (e.g. 'SERIES COMPOSITION', 'SERIES DIRECTOR')
                                if any(next_l_lower.startswith(eh) for eh in [
                                    "series", "director", "composition", "chief", "episode",
                                    "animation", "character", "action", "concept", "art", "producer"
                                ]):
                                    j += 1
                                    continue
                                if any(next_l.startswith(k) for k in [
                                    "監督", "原作", "製作", "キャラクター", "美術", "色彩", "撮影", "音響",
                                    "編集", "音楽", "各話", "第", "脚本", "絵コンテ", "演出", "作画", "原画",
                                    "動画", "仕上", "制作", "cast", "キャスト",
                                ]):
                                    break
                                extracted = self._split_names(next_l)
                                if extracted:
                                    val_names.extend(extracted)
                                    break
                            j += 1
                        if val_names:
                            parts = [clean_hdr, " ".join(val_names)]
                            i = j

            if parts and len(parts) == 2:
                hdr, val = parts[0].strip(), parts[1].strip()
                sub_roles = [r.strip() for r in re.split(r"[・/、&＆]+", hdr) if r.strip()]
                names = self._split_names(val)
                if not names:
                    i += 1
                    continue

                for sr in sub_roles:
                    # Director
                    if (sr in ["監督", "総監督", "ディレクター", "シリーズディレクター"]) and not any(
                        k in sr for k in ["美術", "撮影", "音響", "録音", "音楽", "CG", "3D", "助", "副"]
                    ):
                        staff["director"].extend(names)
                    # Series comp / Script
                    if any(k in sr for k in ["脚本", "シリーズ構成", "構成", "シナリオ"]) and not any(
                        k in sr for k in ["録音", "音楽", "音響", "宣伝", "編集"]
                    ):
                        staff["series_comp"].extend(names)
                    # Char design
                    if any(k in sr for k in ["キャラクターデザイン", "キャラデザ", "キャラクター設計", "キャラクター原案", "人物設定"]):
                        staff["char_design"].extend(names)
                    # Studio
                    if (
                        any(k in sr for k in ["アニメーション制作", "アニメーション制作協力", "制作協力", "アニメ制作", "制作スタジオ"])
                        or (sr in ["制作", "制作会社"] and not any(k in cleaned for k in ["プロデューサー", "進行", "担当", "デスク", "事務", "宣伝"]))
                    ) and not any(k in sr for k in ["プロデューサー", "進行", "担当", "事務", "デスク", "マネージャー"]):
                        staff["studio"].extend(names)
                    # Unit director
                    if any(k in sr for k in ["演出", "副監督", "助監督", "絵コンテ", "コンテ"]):
                        staff["unit_director"].extend(names)
                    # Sakkan
                    if any(k in sr for k in ["作画監督", "総作画監督", "作監"]) and not any(k in sr for k in ["動画"]):
                        staff["sakkan"].extend(names)

            i += 1

        # Deduplicate
        for k in staff:
            seen = set()
            unique = []
            for n in staff[k]:
                if n not in seen and len(n) >= 2:
                    seen.add(n)
                    unique.append(n)
            staff[k] = unique

        return staff

    def _extract_episode_credits(self, lines: List[str]) -> List[Dict[str, Any]]:
        """Parses credits segmented by episode, or whole film credits if single-part."""
        episodes: List[Dict[str, Any]] = []
        current_ep: Optional[Dict[str, Any]] = None
        current_role: Optional[str] = None

        has_episode_headers = any(
            re.search(r"^(?:第\s*\d+\s*話|第[０-９\d]+話|#\s*\d+|\d+話|Episode\s*\d+|ACT\s*\d+|MISSION:\s*\d+)", l, re.I)
            for l in lines
        )

        if not has_episode_headers:
            current_ep = {
                "ep_num": 1,
                "genga": [],
                "sakkan": [],
                "conte_enshutsu": [],
            }
            episodes.append(current_ep)

        for line in lines:
            cleaned = re.sub(r"[*＊]\d+", "", line).strip()
            cleaned = re.sub(r"\[.*?\]", "", cleaned).strip()

            ep_m = re.search(
                r"^(?:第\s*(\d+)\s*話|第([０-９\d]+)話|#\s*(\d+)|(\d+)話|Episode\s*(\d+)|ACT\s*(\d+)|MISSION:\s*(\d+))",
                cleaned,
                re.I,
            )
            if ep_m:
                num_str = ep_m.group(1) or ep_m.group(2) or ep_m.group(3) or ep_m.group(4) or ep_m.group(5) or ep_m.group(6) or ep_m.group(7) or "1"
                try:
                    ep_num = int(num_str)
                except ValueError:
                    ep_num = 1
                current_ep = {
                    "ep_num": ep_num,
                    "genga": [],
                    "sakkan": [],
                    "conte_enshutsu": [],
                }
                episodes.append(current_ep)
                current_role = None
                continue

            if not current_ep:
                continue

            # Standalone role headers
            if cleaned in ["原画", "■原画", "【原画】", "原画マン", "第一原画", "第1原画", "作画", "メインアニメーター"]:
                current_role = "genga"
                continue
            elif any(
                cleaned.startswith(k)
                for k in [
                    "第二原画", "第2原画", "2原", "動画", "仕上", "仕上げ", "背景", "撮影",
                    "音響", "編集", "色彩", "色指定", "検査", "特効", "制作進行", "制作担当",
                    "宣伝", "協力", "キャスト", "声の出演", "脚本", "サブタイトル", "放送", "放映",
                ]
            ):
                current_role = None
                continue

            # Check role lines with : / ： or spaces
            parts = []
            if "：" in cleaned or ":" in cleaned:
                parts = re.split(r"[:：]", cleaned, maxsplit=1)
            else:
                for kw in ["原画", "第一原画", "第1原画", "作画監督", "総作画監督", "作監", "演出", "絵コンテ"]:
                    if cleaned.startswith(kw) and len(cleaned) > len(kw) and cleaned[len(kw)] in " \u3000\t":
                        parts = [kw, cleaned[len(kw):]]
                        break

            if parts and len(parts) == 2:
                hdr, val = parts[0].strip(), parts[1].strip()
                sub_roles = [r.strip() for r in re.split(r"[・/、&＆]+", hdr) if r.strip()]
                names = self._split_names(val)

                if any(r in ["原画", "原画マン", "第一原画", "作画"] for r in sub_roles):
                    current_role = "genga"
                    current_ep["genga"].extend(names)
                    continue
                elif any(k in hdr for k in ["作画監督", "総作画監督", "作監"]):
                    current_role = "sakkan"
                    current_ep["sakkan"].extend(names)
                    continue
                elif any(k in hdr for k in ["演出", "絵コンテ", "コンテ"]):
                    current_role = "conte_enshutsu"
                    current_ep["conte_enshutsu"].extend(names)
                    continue
                else:
                    current_role = None
                    continue

            # Continuation lines for current role
            if current_role == "genga":
                names = self._split_names(cleaned)
                current_ep["genga"].extend(names)
            elif current_role == "sakkan":
                names = self._split_names(cleaned)
                current_ep["sakkan"].extend(names)
            elif current_role == "conte_enshutsu":
                names = self._split_names(cleaned)
                current_ep["conte_enshutsu"].extend(names)

        return episodes

    def _aggregate_genga(self, episode_credits: List[Dict[str, Any]], total_episodes: int) -> List[Dict[str, Any]]:
        """
        Computes credit order r(a) and episode participation ratio f(a) for each animator.
        """
        ep_count = max(len(episode_credits), total_episodes, 1)
        animator_stats: Dict[str, Dict[str, Any]] = {}

        for ep in episode_credits:
            g_list = ep.get("genga", [])
            for rank_0, name in enumerate(g_list):
                rank_1 = rank_0 + 1  # 1-based credit order
                if name not in animator_stats:
                    animator_stats[name] = {"ranks": [], "episodes": set()}
                animator_stats[name]["ranks"].append(rank_1)
                animator_stats[name]["episodes"].add(ep.get("ep_num", 1))

        results: List[Dict[str, Any]] = []
        for name, data in animator_stats.items():
            avg_rank = float(sum(data["ranks"]) / len(data["ranks"]))
            ep_ratio = float(len(data["episodes"]) / ep_count)
            results.append({
                "name": name,
                "rank": round(avg_rank, 2),
                "ep_ratio": round(ep_ratio, 3),
                "episodes_count": len(data["episodes"]),
            })

        # Sort by average rank
        results.sort(key=lambda x: x["rank"])
        return results

    def _aggregate_sakkan(self, episode_credits: List[Dict[str, Any]]) -> List[str]:
        seen = set()
        results = []
        for ep in episode_credits:
            for n in ep.get("sakkan", []):
                if n not in seen and len(n) >= 2:
                    seen.add(n)
                    results.append(n)
        return results
