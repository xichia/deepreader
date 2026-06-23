"""Document ingestion and inspection routes."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from deepreader.api.upload_safety import read_upload_bytes, validate_upload_filename
from deepreader.ingest.epub_parser import parse_epub_document
from deepreader.ingest.text_parser import parse_text_document
from deepreader.storage.models import Document, DocumentRecord
from deepreader.storage.repositories import (
    get_document,
    ingest_parsed_document,
    list_document_records,
    list_documents,
)

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentOut(BaseModel):
    id: int
    title: str
    source_filename: str
    source_type: str
    source_hash: str
    created_at: str


class DocumentDetailOut(DocumentOut):
    record_count: int


class RecordOut(BaseModel):
    id: int
    document_id: int
    stable_id: str
    record_type: str
    chapter_index: int | None
    section_title: str | None
    page_number: int | None
    order_index: int
    source_text: str
    source_hash: str
    metadata: dict[str, Any]
    created_at: str


class IngestResponse(BaseModel):
    document: DocumentDetailOut


def get_session(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.SessionLocal
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def document_out(document: Document) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        title=document.title,
        source_filename=document.source_filename,
        source_type=document.source_type,
        source_hash=document.source_hash,
        created_at=document.created_at.isoformat(),
    )


def document_detail_out(document: Document, record_count: int | None = None) -> DocumentDetailOut:
    count = record_count if record_count is not None else len(document.records)
    return DocumentDetailOut(**document_out(document).model_dump(), record_count=count)


def record_out(record: DocumentRecord) -> RecordOut:
    return RecordOut(
        id=record.id,
        document_id=record.document_id,
        stable_id=record.stable_id,
        record_type=record.record_type,
        chapter_index=record.chapter_index,
        section_title=record.section_title,
        page_number=record.page_number,
        order_index=record.order_index,
        source_text=record.source_text,
        source_hash=record.source_hash,
        metadata=record.metadata_json,
        created_at=record.created_at.isoformat(),
    )


@router.post("/ingest/text", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_text_upload(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> IngestResponse:
    filename = validate_upload_filename(file.filename, {".txt"})
    data = await read_upload_bytes(file, request.app.state.upload_max_bytes)

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text uploads must be valid UTF-8.",
        ) from exc

    parsed_document = parse_text_document(text)
    document = ingest_parsed_document(
        session,
        parsed_document=parsed_document,
        source_filename=filename,
        source_type="txt",
        source_bytes=data,
    )
    return IngestResponse(document=document_detail_out(document, len(parsed_document.records)))


@router.post("/ingest/epub", response_model=IngestResponse, status_code=status.HTTP_201_CREATED)
async def ingest_epub_upload(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> IngestResponse:
    filename = validate_upload_filename(file.filename, {".epub"})
    data = await read_upload_bytes(file, request.app.state.upload_max_bytes)

    try:
        parsed_document = parse_epub_document(data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="EPUB upload could not be parsed.",
        ) from exc

    document = ingest_parsed_document(
        session,
        parsed_document=parsed_document,
        source_filename=filename,
        source_type="epub",
        source_bytes=data,
    )
    return IngestResponse(document=document_detail_out(document, len(parsed_document.records)))


@router.get("", response_model=list[DocumentOut])
def get_documents(session: Session = Depends(get_session)) -> list[DocumentOut]:
    return [document_out(document) for document in list_documents(session)]


@router.get("/{document_id}", response_model=DocumentDetailOut)
def get_document_by_id(document_id: int, session: Session = Depends(get_session)) -> DocumentDetailOut:
    document = get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return document_detail_out(document)


@router.get("/{document_id}/records", response_model=list[RecordOut])
def get_records_by_document_id(
    document_id: int,
    session: Session = Depends(get_session),
) -> list[RecordOut]:
    if get_document(session, document_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return [record_out(record) for record in list_document_records(session, document_id)]
