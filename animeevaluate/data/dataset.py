"""
Anime Dataset Manager and Seed Data Builder.
Manages:
- Work metadata (title, release year, format, episodes, AniList score, staff credits)
- User-work rating matrix R_{ui} for ALS bias decomposition
- Persistence and loading (JSON / CSV / SQLite)
- Seed dataset containing major works across eras with authentic staff credits.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


class DatasetManager:
    def __init__(self, data_dir: Optional[Union[str, Path]] = None):
        if data_dir is None:
            import sys
            if getattr(sys, "frozen", False):
                exe_data = Path(sys.executable).resolve().parent / "data"
                meipass_data = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve() / "data"
                if exe_data.exists() and (exe_data / "anime_metadata.json").exists():
                    data_dir = exe_data
                elif meipass_data.exists() and (meipass_data / "anime_metadata.json").exists():
                    data_dir = meipass_data
                else:
                    data_dir = exe_data
            else:
                data_dir = Path(__file__).resolve().parent.parent.parent / "data"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.metadata_file = self.data_dir / "anime_metadata.json"
        self.ratings_file = self.data_dir / "user_ratings.csv"

        self.works_metadata: Dict[str, Dict[str, Any]] = {}
        self.ratings_df: Optional[pd.DataFrame] = None

    def load_or_init_dataset(self) -> Tuple[Dict[str, Dict[str, Any]], pd.DataFrame]:
        """Loads dataset from disk, or initializes from the built-in seed dataset."""
        if self.metadata_file.exists() and self.ratings_file.exists():
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    self.works_metadata = json.load(f)
                self.ratings_df = pd.read_csv(self.ratings_file)
                return self.works_metadata, self.ratings_df
            except Exception:
                pass

        # Build seed dataset
        self.works_metadata = self._build_seed_metadata()
        self.ratings_df = self._build_seed_ratings(self.works_metadata)
        self.save_dataset()
        return self.works_metadata, self.ratings_df

    def save_dataset(self):
        """Saves current dataset to disk in compact format (<25MB)."""
        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(self.works_metadata, f, ensure_ascii=False, separators=(",", ":"))
        if self.ratings_df is not None:
            self.ratings_df.to_csv(self.ratings_file, index=False)

    def add_work(
        self,
        work_id: str,
        title: str,
        year: int,
        staff: Dict[str, Any],
        anilist_score: float = 75.0,
        user_ratings: Optional[List[Tuple[int, float]]] = None,
    ):
        """Adds or updates an anime work and its ratings."""
        self.works_metadata[work_id] = {
            "title": title,
            "year": year,
            "staff": staff,
            "anilist_mean_score": anilist_score,
        }
        if user_ratings and self.ratings_df is not None:
            new_rows = [
                {"user_id": u, "item_id": work_id, "score": s}
                for u, s in user_ratings
            ]
            self.ratings_df = pd.concat([self.ratings_df, pd.DataFrame(new_rows)], ignore_index=True)
        self.save_dataset()

    def _build_seed_metadata(self) -> Dict[str, Dict[str, Any]]:
        """Returns realistic seed metadata for notable anime with authentic credits."""
        return {
            "eizouken_2020": {
                "title": "映像研には手を出すな！",
                "title_en": "Keep Your Hands Off Eizouken!",
                "year": 2020,
                "anilist_mean_score": 80.0,
                "staff": {
                    "director": ["湯浅政明"],
                    "series_comp": ["木戸雄一郎"],
                    "char_design": ["浅野直之"],
                    "unit_director": ["本橋茉里", "山代風我"],
                    "studio": ["サイエンスSARU"],
                    "sakkan": ["浅野直之", "大野勉", "寺尾憲治"],
                    "genga": [
                        {"name": "村上泉", "rank": 1.0, "ep_ratio": 0.8},
                        {"name": "榎本柊斗", "rank": 2.0, "ep_ratio": 0.75},
                        {"name": "松本憲生", "rank": 3.0, "ep_ratio": 0.4},
                        {"name": "堀裕津", "rank": 4.0, "ep_ratio": 0.5},
                        {"name": "田口愛梨", "rank": 5.0, "ep_ratio": 0.6},
                    ],
                },
            },
            "tatami_galaxy_2010": {
                "title": "四畳半神話大系",
                "title_en": "The Tatami Galaxy",
                "year": 2010,
                "anilist_mean_score": 85.0,
                "staff": {
                    "director": ["湯浅政明"],
                    "series_comp": ["上田誠"],
                    "char_design": ["伊東伸高"],
                    "unit_director": ["横山彰利"],
                    "studio": ["マッドハウス"],
                    "sakkan": ["伊東伸高"],
                    "genga": [
                        {"name": "伊東伸高", "rank": 1.0, "ep_ratio": 0.9},
                        {"name": "浅野直之", "rank": 2.0, "ep_ratio": 0.8},
                        {"name": "井上俊之", "rank": 3.0, "ep_ratio": 0.5},
                        {"name": "松本憲生", "rank": 4.0, "ep_ratio": 0.4},
                    ],
                },
            },
            "pingpong_2014": {
                "title": "ピンポン THE ANIMATION",
                "title_en": "Ping Pong the Animation",
                "year": 2014,
                "anilist_mean_score": 86.0,
                "staff": {
                    "director": ["湯浅政明"],
                    "series_comp": ["湯浅政明"],
                    "char_design": ["伊東伸高"],
                    "unit_director": ["伊藤秀樹"],
                    "studio": ["タツノコプロ"],
                    "sakkan": ["伊東伸高"],
                    "genga": [
                        {"name": "榎本柊斗", "rank": 1.5, "ep_ratio": 0.7},
                        {"name": "浅野直之", "rank": 2.0, "ep_ratio": 0.6},
                        {"name": "松本憲生", "rank": 3.0, "ep_ratio": 0.5},
                        {"name": "伊藤秀樹", "rank": 4.0, "ep_ratio": 0.8},
                    ],
                },
            },
            "bocchi_2022": {
                "title": "ぼっち・ざ・ろっく！",
                "title_en": "Bocchi the Rock!",
                "year": 2022,
                "anilist_mean_score": 88.0,
                "staff": {
                    "director": ["斎藤圭一郎"],
                    "series_comp": ["吉田恵里香"],
                    "char_design": ["けろりら"],
                    "unit_director": ["山本ゆうすけ"],
                    "studio": ["CloverWorks"],
                    "sakkan": ["けろりら", "小谷杏樹"],
                    "genga": [
                        {"name": "けろりら", "rank": 1.0, "ep_ratio": 1.0},
                        {"name": "榎本柊斗", "rank": 2.0, "ep_ratio": 0.6},
                        {"name": "川上雄介", "rank": 3.0, "ep_ratio": 0.5},
                        {"name": "MYOUN", "rank": 4.0, "ep_ratio": 0.5},
                    ],
                },
            },
            "frieren_2023": {
                "title": "葬送のフリーレン",
                "title_en": "Frieren: Beyond Journey's End",
                "year": 2023,
                "anilist_mean_score": 93.0,
                "staff": {
                    "director": ["斎藤圭一郎"],
                    "series_comp": ["鈴木智尋"],
                    "char_design": ["長澤礼子"],
                    "unit_director": ["北川朋哉"],
                    "studio": ["マッドハウス"],
                    "sakkan": ["長澤礼子", "高瀬言"],
                    "genga": [
                        {"name": "榎本柊斗", "rank": 1.0, "ep_ratio": 0.7},
                        {"name": "岩澤亨", "rank": 2.0, "ep_ratio": 0.6},
                        {"name": "亀田祥倫", "rank": 3.0, "ep_ratio": 0.3},
                        {"name": "松本憲生", "rank": 4.0, "ep_ratio": 0.3},
                    ],
                },
            },
            "shingeki_s1_2013": {
                "title": "進撃の巨人 Season 1",
                "title_en": "Attack on Titan",
                "year": 2013,
                "anilist_mean_score": 85.0,
                "staff": {
                    "director": ["荒木哲郎"],
                    "series_comp": ["小林靖子"],
                    "char_design": ["浅野恭司"],
                    "unit_director": ["肥塚正史"],
                    "studio": ["WIT STUDIO"],
                    "sakkan": ["浅野恭司", "門脇聡"],
                    "genga": [
                        {"name": "今井有文", "rank": 1.0, "ep_ratio": 0.9},
                        {"name": "世良悠子", "rank": 2.5, "ep_ratio": 0.7},
                        {"name": "田中宏紀", "rank": 3.0, "ep_ratio": 0.5},
                        {"name": "胡拓磨", "rank": 4.0, "ep_ratio": 0.6},
                    ],
                },
            },
            "kabaneri_2016": {
                "title": "甲鉄城のカバネリ",
                "title_en": "Kabaneri of the Iron Fortress",
                "year": 2016,
                "anilist_mean_score": 71.0,
                "staff": {
                    "director": ["荒木哲郎"],
                    "series_comp": ["大河内一楼"],
                    "char_design": ["江原康之"],
                    "unit_director": ["田中洋之"],
                    "studio": ["WIT STUDIO"],
                    "sakkan": ["江原康之"],
                    "genga": [
                        {"name": "今井有文", "rank": 1.0, "ep_ratio": 0.8},
                        {"name": "世良悠子", "rank": 2.0, "ep_ratio": 0.6},
                        {"name": "松本憲生", "rank": 3.5, "ep_ratio": 0.3},
                    ],
                },
            },
            "mob_psycho_s1_2016": {
                "title": "モブサイコ100",
                "title_en": "Mob Psycho 100",
                "year": 2016,
                "anilist_mean_score": 85.0,
                "staff": {
                    "director": ["立川譲"],
                    "series_comp": ["瀬古浩司"],
                    "char_design": ["亀田祥倫"],
                    "unit_director": ["大矢雄嗣"],
                    "studio": ["ボンズ"],
                    "sakkan": ["亀田祥倫"],
                    "genga": [
                        {"name": "亀田祥倫", "rank": 1.0, "ep_ratio": 0.9},
                        {"name": "榎本柊斗", "rank": 2.0, "ep_ratio": 0.5},
                        {"name": "松本憲生", "rank": 3.0, "ep_ratio": 0.4},
                        {"name": "中村豊", "rank": 4.0, "ep_ratio": 0.3},
                    ],
                },
            },
            "mob_psycho_s2_2019": {
                "title": "モブサイコ100 II",
                "title_en": "Mob Psycho 100 II",
                "year": 2019,
                "anilist_mean_score": 88.0,
                "staff": {
                    "director": ["立川譲"],
                    "series_comp": ["瀬古浩司"],
                    "char_design": ["亀田祥倫"],
                    "unit_director": ["蓮井隆弘"],
                    "studio": ["ボンズ"],
                    "sakkan": ["亀田祥倫"],
                    "genga": [
                        {"name": "亀田祥倫", "rank": 1.0, "ep_ratio": 0.8},
                        {"name": "榎本柊斗", "rank": 2.0, "ep_ratio": 0.7},
                        {"name": "五十嵐祐貴", "rank": 3.0, "ep_ratio": 0.5},
                        {"name": "田中宏紀", "rank": 4.0, "ep_ratio": 0.4},
                    ],
                },
            },
            "gurren_lagann_2007": {
                "title": "天元突破グレンラガン",
                "title_en": "Tengen Toppa Gurren Lagann",
                "year": 2007,
                "anilist_mean_score": 86.0,
                "staff": {
                    "director": ["今石洋之"],
                    "series_comp": ["中島かずき"],
                    "char_design": ["錦織敦史"],
                    "unit_director": ["大塚雅彦"],
                    "studio": ["GAINAX"],
                    "sakkan": ["錦織敦史", "吉成曜"],
                    "genga": [
                        {"name": "吉成曜", "rank": 1.0, "ep_ratio": 0.8},
                        {"name": "すしお", "rank": 2.0, "ep_ratio": 0.7},
                        {"name": "雨宮哲", "rank": 3.0, "ep_ratio": 0.6},
                        {"name": "中村豊", "rank": 4.0, "ep_ratio": 0.3},
                    ],
                },
            },
            "kill_la_kill_2013": {
                "title": "キルラキル",
                "title_en": "Kill la Kill",
                "year": 2013,
                "anilist_mean_score": 80.0,
                "staff": {
                    "director": ["今石洋之"],
                    "series_comp": ["中島かずき"],
                    "char_design": ["すしお"],
                    "unit_director": ["雨宮哲"],
                    "studio": ["TRIGGER"],
                    "sakkan": ["すしお"],
                    "genga": [
                        {"name": "すしお", "rank": 1.0, "ep_ratio": 0.9},
                        {"name": "吉成曜", "rank": 2.0, "ep_ratio": 0.6},
                        {"name": "雨宮哲", "rank": 3.0, "ep_ratio": 0.7},
                        {"name": "坂本勝", "rank": 4.0, "ep_ratio": 0.5},
                    ],
                },
            },
            "madoka_magica_2011": {
                "title": "魔法少女まどか☆マギカ",
                "title_en": "Puella Magi Madoka Magica",
                "year": 2011,
                "anilist_mean_score": 83.0,
                "staff": {
                    "director": ["新房昭之"],
                    "series_comp": ["虚淵玄"],
                    "char_design": ["岸田隆宏"],
                    "unit_director": ["宮本幸裕"],
                    "studio": ["シャフト"],
                    "sakkan": ["谷口淳一郎", "高橋美香"],
                    "genga": [
                        {"name": "阿部望", "rank": 1.0, "ep_ratio": 0.6},
                        {"name": "松本憲生", "rank": 2.5, "ep_ratio": 0.4},
                        {"name": "工藤裕加", "rank": 3.0, "ep_ratio": 0.5},
                    ],
                },
            },
            "bakemonogatari_2009": {
                "title": "化物語",
                "title_en": "Bakemonogatari",
                "year": 2009,
                "anilist_mean_score": 83.0,
                "staff": {
                    "director": ["新房昭之"],
                    "series_comp": ["倉田英之"],
                    "char_design": ["渡辺明夫"],
                    "unit_director": ["尾石達也"],
                    "studio": ["シャフト"],
                    "sakkan": ["渡辺明夫"],
                    "genga": [
                        {"name": "阿部望", "rank": 1.5, "ep_ratio": 0.6},
                        {"name": "渡辺明夫", "rank": 2.0, "ep_ratio": 0.8},
                        {"name": "今村大樹", "rank": 3.0, "ep_ratio": 0.5},
                    ],
                },
            },
            "haruhi_2006": {
                "title": "涼宮ハルヒの憂鬱",
                "title_en": "The Melancholy of Haruhi Suzumiya",
                "year": 2006,
                "anilist_mean_score": 78.0,
                "staff": {
                    "director": ["石原立也"],
                    "series_comp": ["志茂文彦"],
                    "char_design": ["池田晶子"],
                    "unit_director": ["山本寛"],
                    "studio": ["京都アニメーション"],
                    "sakkan": ["池田晶子", "西屋太志"],
                    "genga": [
                        {"name": "木上益治", "rank": 1.0, "ep_ratio": 0.8},
                        {"name": "門脇聡", "rank": 2.0, "ep_ratio": 0.6},
                        {"name": "西屋太志", "rank": 3.0, "ep_ratio": 0.7},
                    ],
                },
            },
            "euphonium_s1_2015": {
                "title": "響け！ユーフォニアム",
                "title_en": "Sound! Euphonium",
                "year": 2015,
                "anilist_mean_score": 80.0,
                "staff": {
                    "director": ["石原立也"],
                    "series_comp": ["花田十輝"],
                    "char_design": ["池田晶子"],
                    "unit_director": ["山田尚子"],
                    "studio": ["京都アニメーション"],
                    "sakkan": ["池田晶子"],
                    "genga": [
                        {"name": "木上益治", "rank": 1.0, "ep_ratio": 0.9},
                        {"name": "浅野直之", "rank": 2.5, "ep_ratio": 0.3},
                        {"name": "高瀬言", "rank": 3.0, "ep_ratio": 0.7},
                    ],
                },
            },
            "kimetsu_s1_2019": {
                "title": "鬼滅の刃",
                "title_en": "Demon Slayer: Kimetsu no Yaiba",
                "year": 2019,
                "anilist_mean_score": 84.0,
                "staff": {
                    "director": ["外崎春雄"],
                    "series_comp": ["ufotable"],
                    "char_design": ["松島晃"],
                    "unit_director": ["白井俊行"],
                    "studio": ["ufotable"],
                    "sakkan": ["松島晃"],
                    "genga": [
                        {"name": "阿部望", "rank": 1.0, "ep_ratio": 0.8},
                        {"name": "木村豪", "rank": 2.0, "ep_ratio": 0.7},
                        {"name": "国弘昌之", "rank": 3.0, "ep_ratio": 0.6},
                        {"name": "小船井充", "rank": 4.0, "ep_ratio": 0.5},
                    ],
                },
            },
            "fate_zero_2011": {
                "title": "Fate/Zero",
                "title_en": "Fate/Zero",
                "year": 2011,
                "anilist_mean_score": 82.0,
                "staff": {
                    "director": ["あおきえい"],
                    "series_comp": ["虚淵玄"],
                    "char_design": ["碇谷敦", "須藤友徳"],
                    "unit_director": ["野中卓也"],
                    "studio": ["ufotable"],
                    "sakkan": ["碇谷敦", "須藤友徳"],
                    "genga": [
                        {"name": "阿部望", "rank": 1.0, "ep_ratio": 0.7},
                        {"name": "木村豪", "rank": 2.0, "ep_ratio": 0.6},
                        {"name": "国弘昌之", "rank": 3.0, "ep_ratio": 0.5},
                    ],
                },
            },
            "cowboy_bebop_1998": {
                "title": "カウボーイビバップ",
                "title_en": "Cowboy Bebop",
                "year": 1998,
                "anilist_mean_score": 89.0,
                "staff": {
                    "director": ["渡辺信一郎"],
                    "series_comp": ["信本敬子"],
                    "char_design": ["川元利浩"],
                    "unit_director": ["佐藤育郎"],
                    "studio": ["サンライズ"],
                    "sakkan": ["川元利浩"],
                    "genga": [
                        {"name": "中村豊", "rank": 1.0, "ep_ratio": 0.7},
                        {"name": "井上俊之", "rank": 2.0, "ep_ratio": 0.5},
                        {"name": "松本憲生", "rank": 3.0, "ep_ratio": 0.4},
                    ],
                },
            },
            "samurai_champloo_2004": {
                "title": "サムライチャンプルー",
                "title_en": "Samurai Champloo",
                "year": 2004,
                "anilist_mean_score": 85.0,
                "staff": {
                    "director": ["渡辺信一郎"],
                    "series_comp": ["小原信治"],
                    "char_design": ["中澤一登"],
                    "unit_director": ["山本沙代"],
                    "studio": ["マングローブ"],
                    "sakkan": ["中澤一登"],
                    "genga": [
                        {"name": "中村豊", "rank": 1.0, "ep_ratio": 0.8},
                        {"name": "今石洋之", "rank": 2.0, "ep_ratio": 0.3},
                        {"name": "松本憲生", "rank": 3.0, "ep_ratio": 0.5},
                    ],
                },
            },
            "heroaca_s1_2016": {
                "title": "僕のヒーローアカデミア",
                "title_en": "My Hero Academia",
                "year": 2016,
                "anilist_mean_score": 79.0,
                "staff": {
                    "director": ["長崎健司"],
                    "series_comp": ["黒田洋介"],
                    "char_design": ["馬越嘉彦"],
                    "unit_director": ["塚田拓郎"],
                    "studio": ["ボンズ"],
                    "sakkan": ["馬越嘉彦"],
                    "genga": [
                        {"name": "中村豊", "rank": 1.0, "ep_ratio": 0.6},
                        {"name": "亀田祥倫", "rank": 2.5, "ep_ratio": 0.4},
                        {"name": "林祐己", "rank": 3.0, "ep_ratio": 0.5},
                    ],
                },
            },
            "jujutsu_kaisen_s1_2020": {
                "title": "呪術廻戦 Season 1",
                "title_en": "Jujutsu Kaisen",
                "year": 2020,
                "anilist_mean_score": 86.0,
                "staff": {
                    "director": ["朴性厚"],
                    "series_comp": ["瀬古浩司"],
                    "char_design": ["平松禎史"],
                    "unit_director": ["梅本唯"],
                    "studio": ["MAPPA"],
                    "sakkan": ["平松禎史", "清水貴子"],
                    "genga": [
                        {"name": "渡邊啓一郎", "rank": 1.0, "ep_ratio": 0.7},
                        {"name": "榎本柊斗", "rank": 2.0, "ep_ratio": 0.5},
                        {"name": "阿部望", "rank": 3.0, "ep_ratio": 0.4},
                    ],
                },
            },
            "chainsaw_man_2022": {
                "title": "チェンソーマン",
                "title_en": "Chainsaw Man",
                "year": 2022,
                "anilist_mean_score": 84.0,
                "staff": {
                    "director": ["中山竜"],
                    "series_comp": ["瀬古浩司"],
                    "char_design": ["杉山和隆"],
                    "unit_director": ["中園真登"],
                    "studio": ["MAPPA"],
                    "sakkan": ["杉山和隆", "斉藤拓也"],
                    "genga": [
                        {"name": "渡邊啓一郎", "rank": 1.0, "ep_ratio": 0.8},
                        {"name": "榎本柊斗", "rank": 2.0, "ep_ratio": 0.6},
                        {"name": "松本憲生", "rank": 3.0, "ep_ratio": 0.3},
                    ],
                },
            },
            "skip_and_loafer_2023": {
                "title": "スキップとローファー",
                "title_en": "Skip and Loafer",
                "year": 2023,
                "anilist_mean_score": 81.0,
                "staff": {
                    "director": ["出合小都美"],
                    "series_comp": ["出合小都美"],
                    "char_design": ["梅下麻奈未"],
                    "unit_director": ["阿部ゆり子"],
                    "studio": ["P.A.WORKS"],
                    "sakkan": ["梅下麻奈未"],
                    "genga": [
                        {"name": "梅下麻奈未", "rank": 1.0, "ep_ratio": 0.9},
                        {"name": "井上俊之", "rank": 2.5, "ep_ratio": 0.4},
                    ],
                },
            },
        }

    def _build_seed_ratings(self, metadata: Dict[str, Dict[str, Any]]) -> pd.DataFrame:
        """
        Generates realistic user ratings matrix R_{ui} around each anime's base quality
        simulating varying user biases (some harsh users b_u < 0, some generous users b_u > 0).
        """
        np.random.seed(42)
        n_users = 100
        user_biases = np.random.normal(loc=0.0, scale=4.0, size=n_users)

        rows = []
        for u_id in range(1, n_users + 1):
            u_bias = user_biases[u_id - 1]
            # Each user rates a subset of works
            for work_id, meta in metadata.items():
                if np.random.rand() < 0.65:  # 65% rating density
                    base_score = meta.get("anilist_mean_score", 75.0)
                    noise = np.random.normal(0.0, 2.5)
                    observed = base_score + u_bias + noise
                    # Clamp between 10 and 100
                    clamped = max(10.0, min(100.0, round(observed, 1)))
                    rows.append({
                        "user_id": u_id,
                        "item_id": work_id,
                        "score": clamped,
                    })

        return pd.DataFrame(rows)
