"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from deepreader.api.routes_documents import router as documents_router
from deepreader.api.routes_search import router as search_router
from deepreader.api.upload_safety import get_max_upload_bytes
from deepreader.storage.db import build_engine, build_session_factory, init_db


def create_app(database_url: str | None = None, upload_max_bytes: int | None = None) -> FastAPI:
    app = FastAPI(title="DeepReader Backend", version="0.1.0")

    engine = build_engine(database_url)
    init_db(engine)
    app.state.engine = engine
    app.state.SessionLocal = build_session_factory(engine)
    app.state.upload_max_bytes = upload_max_bytes or get_max_upload_bytes()

    app.include_router(documents_router)
    app.include_router(search_router)

    return app


app = create_app()
