"""
FastAPI Backend Application for Anime Quality Evaluation & Prediction Dashboard.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from animeevaluate.pipeline import AnimePipeline

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize and train pipeline on startup
    pipeline.train()
    yield

app = FastAPI(
    title="Anime Latent Quality Predictor & Staff Evaluator",
    version="0.1.0",
    description="Mathematical Latent Quality Decomposition, GBDT Prediction, SHAP Factor Attribution & Staff Capability Evaluation",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_no_cache_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


pipeline = AnimePipeline()


class PredictRequest(BaseModel):
    title: str = "新規企画アニメ"
    year: int = 2024
    director: Optional[str] = ""
    series_comp: Optional[str] = ""
    char_design: Optional[str] = ""
    music: Optional[str] = ""
    art_dir: Optional[str] = ""
    studio: Optional[str] = ""
    genga: Optional[List[str]] = []


@app.get("/api/status")
def get_status():
    if not pipeline.is_trained:
        pipeline.train()
    return {
        "status": "ready",
        "works_count": len(pipeline.works_metadata),
        "ratings_count": len(pipeline.ratings_df) if pipeline.ratings_df is not None else 0,
        "metrics": pipeline.evaluation_metrics,
        "global_mean": round(pipeline.bias_model.global_mean, 2),
    }


@app.get("/api/comparison")
def get_comparison():
    if not pipeline.is_trained:
        pipeline.train()
    return pipeline.get_comparison_table()


@app.get("/api/leaderboard")
def get_leaderboard(
    role: Optional[str] = Query(None, description="Role filter: director, genga, char_design, studio, etc."),
    sort_by: str = Query("rating", description="Sort order: rating or cumulative"),
    min_works: int = Query(1, description="Minimum works"),
    limit: int = Query(1000, description="Limit"),
):
    if not pipeline.is_trained:
        pipeline.train()
    role_param = None if role in ("all", "none", "", None) else role
    return pipeline.get_staff_leaderboard(
        role=role_param, sort_by=sort_by, min_works=min_works, limit=limit
    )


@app.get("/api/staff/{name}")
def get_staff_detail(name: str):
    if not pipeline.is_trained:
        pipeline.train()
    profile = pipeline.get_staff_profile(name)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Staff '{name}' not found")
    return profile


@app.get("/api/staff-search")
def search_staff(q: str = Query(..., min_length=1)):
    if not pipeline.is_trained:
        pipeline.train()
    return pipeline.search_staff(q)


@app.get("/api/search")
def unified_search(q: str = Query(..., min_length=1)):
    """Unified search returning matching anime works and staff members."""
    if not pipeline.is_trained:
        pipeline.train()
    works = pipeline.search_works(q, limit=15)
    staff = pipeline.search_staff(q)
    return {
        "query": q,
        "works": works,
        "staff": staff,
    }


@app.get("/api/anime/{work_id}")
def get_anime_detail(work_id: str):
    """Returns comprehensive anime information, staff credits, and SHAP attribution."""
    if not pipeline.is_trained:
        pipeline.train()
    detail = pipeline.get_work_detail(work_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"Anime '{work_id}' not found")
    return detail


@app.post("/api/predict")
def predict_quality(req: PredictRequest):
    if not pipeline.is_trained:
        pipeline.train()

    genga_input = []
    for idx, name in enumerate(req.genga or []):
        cleaned = name.strip()
        if cleaned:
            genga_input.append({"name": cleaned, "rank": idx + 1, "ep_ratio": 1.0})

    staff_dict = {
        "director": [req.director.strip()] if req.director and req.director.strip() else [],
        "series_comp": [req.series_comp.strip()] if req.series_comp and req.series_comp.strip() else [],
        "char_design": [req.char_design.strip()] if req.char_design and req.char_design.strip() else [],
        "music": [req.music.strip()] if req.music and req.music.strip() else [],
        "art_dir": [req.art_dir.strip()] if req.art_dir and req.art_dir.strip() else [],
        "studio": [req.studio.strip()] if req.studio and req.studio.strip() else [],
        "genga": genga_input,
    }

    result = pipeline.predict_custom(title=req.title, release_year=req.year, staff=staff_dict)
    return result


class CollectRequest(BaseModel):
    max_works: int = 100


@app.post("/api/collect")
def collect_data(req: CollectRequest):
    from animeevaluate.data.bulk_collector import BulkDataCollector
    collector = BulkDataCollector()
    stat = collector.harvest_anime_dataset(max_works=req.max_works)
    pipeline.train()
    return {
        "status": "success",
        "new_collected": stat["new_collected"],
        "total_works": stat["total_works"],
        "total_ratings": stat["total_ratings"],
        "metrics": pipeline.evaluation_metrics,
    }


@app.post("/api/retrain")
def retrain():
    return pipeline.train()


# Mount static files
import sys
if getattr(sys, "frozen", False):
    meipass_static = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve() / "animeevaluate" / "web" / "static"
    exe_static = Path(sys.executable).resolve().parent / "animeevaluate" / "web" / "static"
    if meipass_static.exists():
        static_dir = meipass_static
    elif exe_static.exists():
        static_dir = exe_static
    else:
        static_dir = Path(__file__).resolve().parent / "static"
else:
    static_dir = Path(__file__).resolve().parent / "static"

static_dir.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
