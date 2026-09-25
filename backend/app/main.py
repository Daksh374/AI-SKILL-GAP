"""FastAPI application entrypoint.

    uvicorn backend.app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.app.config import get_settings
from backend.app.db.database import init_db
from backend.app.knowledge import get_kb
from backend.app.ml.predictor import ModelNotTrainedError, get_predictor
from backend.app.nlp.spacy_loader import get_nlp
from backend.app.routers import market, meta, resumes, roadmap

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("career_engine")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    get_kb()
    get_nlp()
    try:
        get_predictor()
    except ModelNotTrainedError as exc:
        logger.error("%s", exc)
    if not settings.tavily_configured:
        logger.warning("TAVILY_API_KEY not set: market intelligence and learning resources will report 'not configured'.")
    if not settings.secret_key:
        logger.warning("SECRET_KEY not set: session ids are hashed without a key. Set SECRET_KEY in .env.")
    yield


app = FastAPI(
    title="AI Skill-Gap & Career Intelligence Engine",
    version="1.0.0",
    description="Resume NLP → ML career ranking → deterministic skill gap → Tavily-backed market data & learning roadmap.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error. See server logs."})


for r in (meta.router, resumes.router, roadmap.router, market.router):
    app.include_router(r)
