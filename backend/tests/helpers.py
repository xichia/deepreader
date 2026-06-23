from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from deepreader.ingest.text_parser import parse_text_document
from deepreader.storage.models import Document
from deepreader.storage.repositories import ingest_parsed_document


def ingest_text_fixture(session: Session, path: Path) -> Document:
    data = path.read_bytes()
    return ingest_parsed_document(
        session,
        parsed_document=parse_text_document(data.decode("utf-8")),
        source_filename=path.name,
        source_type="txt",
        source_bytes=data,
    )
