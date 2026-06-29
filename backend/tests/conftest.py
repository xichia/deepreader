from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from deepreader.api.main import create_app
from deepreader.storage.db import build_engine, build_session_factory, init_db


@pytest.fixture
def examples_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def db_session(tmp_path: Path) -> Iterator[Session]:
    engine = build_engine(f"sqlite:///{tmp_path / 'test.sqlite3'}")
    init_db(engine)
    session_factory = build_session_factory(engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(database_url=f"sqlite:///{tmp_path / 'api.sqlite3'}")
    with TestClient(app) as test_client:
        yield test_client
    app.state.engine.dispose()
