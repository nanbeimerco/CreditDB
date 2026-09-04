"""
Anime Title Normalization and Fuzzy Entity Resolution Matcher.
Links Seesaa Wiki titles with AniList entries using:
- NFKC unicode normalization
- Punctuation, bracket, and season suffix stripping
- Kana normalization (Katakana <-> Hiragana)
- RapidFuzz token sort ratio & partial ratio
- Alias dictionary mapping
"""

from __future__ import annotations
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple, Union
from rapidfuzz import fuzz


class AnimeMatcher:
    """Matches anime titles between Japanese Wiki and AniList databases."""

    # Built-in aliases for notable anime series
    COMMON_ALIASES: Dict[str, List[str]] = {
        "進撃の巨人": ["Shingeki no Kyojin", "Attack on Titan"],
        "呪術廻戦": ["Jujutsu Kaisen"],
        "鬼滅の刃": ["Kimetsu no Yaiba", "Demon Slayer: Kimetsu no Yaiba"],
        "映像研には手を出すな！": ["Eizouken ni wa Te wo Dasu na!", "Keep Your Hands Off Eizouken!"],
        "チェンソーマン": ["Chainsaw Man"],
        "ぼっち・ざ・ろっく！": ["Bocchi the Rock!"],
        "葬送のフリーレン": ["Sousou no Frieren", "Frieren: Beyond Journey's End"],
        "新世紀エヴァンゲリオン": ["Neon Genesis Evangelion", "Shinseiki Evangelion"],
        "涼宮ハルヒの憂鬱": ["Suzumiya Haruhi no Yuuutsu", "The Melancholy of Haruhi Suzumiya"],
        "魔法少女まどか☆マギカ": ["Mahou Shoujo Madoka★Magica", "Puella Magi Madoka Magica"],
        "四畳半神話大系": ["Yojouhan Shinwa Taikei", "The Tatami Galaxy"],
        "モブサイコ100": ["Mob Psycho 100"],
        "ワンパンマン": ["One Punch Man"],
    }

    def __init__(self, match_threshold: float = 70.0):
        self.match_threshold = match_threshold

    @staticmethod
    def normalize_title(title: str) -> str:
        """
        Normalizes Japanese/English titles for robust string comparison:
        - Unicode NFKC (fullwidth -> halfwidth alphanumeric, unified punctuation)
        - Remove bracketed notes like （2020年）, [TV], 【1期】
        - Lowercase
        - Remove special punctuation
        """
        if not title:
            return ""
        # 1. Unicode normalization
        t = unicodedata.normalize("NFKC", str(title))
        # 2. Remove parenthetical year/season notes
        t = re.sub(r"[\(（\[【][^()（）\[\]【】]*?(?:\d{4}|年|第\d|期|TV|放送|版)[^()（）\[\]【】]*?[\)）\]】]", "", t)
        # 3. Convert Katakana to Hiragana for phonetic normalization
        t = AnimeMatcher._katakana_to_hiragana(t)
        # 4. Remove symbols and extra whitespace
        t = re.sub(r"[・★☆◆◇♪!！?？:：\-—_~～'\"`「」『』\s]+", "", t)
        return t.lower().strip()

    @staticmethod
    def _katakana_to_hiragana(text: str) -> str:
        """Converts Katakana characters to Hiragana."""
        res = []
        for ch in text:
            code = ord(ch)
            if 0x30A1 <= code <= 0x30F6:
                res.append(chr(code - 0x60))
            else:
                res.append(ch)
        return "".join(res)

    def compute_similarity(self, title_a: str, title_b: str) -> float:
        """
        Computes composite fuzzy similarity between two anime titles (0.0 to 100.0).
        """
        norm_a = self.normalize_title(title_a)
        norm_b = self.normalize_title(title_b)

        if not norm_a or not norm_b:
            return 0.0

        if norm_a == norm_b:
            return 100.0

        # Exact substring match bonus
        if norm_a in norm_b or norm_b in norm_a:
            ratio = max(len(norm_a), len(norm_b))
            sub_ratio = min(len(norm_a), len(norm_b)) / ratio
            if sub_ratio > 0.6:
                return float(90.0 + 10.0 * sub_ratio)

        r_token = fuzz.token_sort_ratio(norm_a, norm_b)
        r_partial = fuzz.partial_ratio(norm_a, norm_b)
        r_simple = fuzz.ratio(norm_a, norm_b)

        return float(0.5 * r_token + 0.3 * r_simple + 0.2 * r_partial)

    def find_best_match(
        self,
        query: str,
        candidates: List[Dict[str, Any]],
        title_key: str = "title",
    ) -> Optional[Tuple[Dict[str, Any], float]]:
        """
        Finds the best matching candidate anime from a list of candidate dictionaries.
        Each candidate dictionary can have 'title', 'title_native', 'title_romaji', 'title_english', 'synonyms'.
        """
        best_cand: Optional[Dict[str, Any]] = None
        best_score: float = 0.0

        # Precompute query variants (original + aliases)
        query_variants = [query]
        for canonical, aliases in self.COMMON_ALIASES.items():
            if query == canonical or query in aliases:
                query_variants.extend(aliases)
                query_variants.append(canonical)

        for cand in candidates:
            cand_titles = []
            # Gather all candidate title variations
            if title_key in cand and cand[title_key]:
                cand_titles.append(cand[title_key])
            for k in ["title_native", "title_romaji", "title_english"]:
                if cand.get(k):
                    cand_titles.append(cand[k])
            if cand.get("synonyms") and isinstance(cand["synonyms"], list):
                cand_titles.extend(cand["synonyms"])

            # Find max score across query variants and candidate title variations
            cand_max_score = 0.0
            for q_var in query_variants:
                for ct in cand_titles:
                    score = self.compute_similarity(q_var, ct)
                    if score > cand_max_score:
                        cand_max_score = score

            if cand_max_score > best_score:
                best_score = cand_max_score
                best_cand = cand

        if best_cand is not None and best_score >= self.match_threshold:
            return best_cand, best_score
        return None
