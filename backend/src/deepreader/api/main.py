"""FastAPI application factory."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from deepreader.api.routes_jobs import router as jobs_router
from deepreader.api.routes_documents import router as documents_router
from deepreader.api.routes_qa import router as qa_router
from deepreader.api.routes_search import router as search_router
from deepreader.api.routes_summaries import router as summaries_router
from deepreader.api.upload_safety import get_max_upload_bytes
from deepreader.storage.db import build_engine, build_session_factory, init_db

DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)


def get_cors_origins() -> list[str]:
    raw_origins = os.getenv("DEEPREADER_CORS_ORIGINS")
    if raw_origins is None:
        return list(DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


def create_app(database_url: str | None = None, upload_max_bytes: int | None = None) -> FastAPI:
    app = FastAPI(title="DeepReader Backend", version="0.4.0")

    cors_origins = get_cors_origins()
    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

    engine = build_engine(database_url)
    init_db(engine)
    app.state.engine = engine
    app.state.SessionLocal = build_session_factory(engine)
    app.state.upload_max_bytes = upload_max_bytes or get_max_upload_bytes()

    app.include_router(documents_router)
    app.include_router(summaries_router)
    app.include_router(search_router)
    app.include_router(jobs_router)
    app.include_router(qa_router)

    return app


app = create_app()
