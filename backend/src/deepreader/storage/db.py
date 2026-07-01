"""Database engine and session helpers."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import Session, sessionmaker

from deepreader.storage.models import Base

DEFAULT_DATABASE_URL = "sqlite:///./data/deepreader.sqlite3"


def get_database_url() -> str:
    return os.getenv("DEEPREADER_DATABASE_URL", DEFAULT_DATABASE_URL)


def build_engine(database_url: str | None = None) -> Engine:
    url = database_url or get_database_url()
    _ensure_sqlite_parent_directory(url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_job_observability_columns(engine)


def _ensure_sqlite_job_observability_columns(engine: Engine) -> None:
    """Add v0.6 remote-job fields to existing local SQLite databases."""

    if engine.dialect.name != "sqlite" or not inspect(engine).has_table("jobs"):
        return

    column_names = {column["name"] for column in inspect(engine).get_columns("jobs")}
    statements: list[str] = []
    if "remote_job_id" not in column_names:
        statements.append("ALTER TABLE jobs ADD COLUMN remote_job_id VARCHAR(255)")
    if "remote_progress_json" not in column_names:
        statements.append("ALTER TABLE jobs ADD COLUMN remote_progress_json JSON")
    if "skipped_steps" not in column_names:
        statements.append("ALTER TABLE jobs ADD COLUMN skipped_steps INTEGER NOT NULL DEFAULT 0")
    if inspect(engine).has_table("job_steps"):
        step_columns = {column["name"] for column in inspect(engine).get_columns("job_steps")}
        if "error_code" not in step_columns:
            statements.append("ALTER TABLE job_steps ADD COLUMN error_code VARCHAR(50)")
    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _ensure_sqlite_parent_directory(database_url: str) -> None:
    parsed_url = make_url(database_url)
    if parsed_url.get_backend_name() != "sqlite":
        return

    database_path = parsed_url.database
    if not database_path or database_path == ":memory:":
        return

    path = Path(database_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
