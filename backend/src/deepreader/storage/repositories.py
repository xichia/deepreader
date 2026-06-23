"""Repository functions for documents, records, and search logging."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from deepreader.records.ids import hash_bytes, hash_text, stable_record_id
from deepreader.records.metadata import ParsedDocument, build_record_metadata
from deepreader.storage.models import Document, DocumentRecord, SearchQuery


def ingest_parsed_document(
    session: Session,
    *,
    parsed_document: ParsedDocument,
    source_filename: str,
    source_type: str,
    source_bytes: bytes,
) -> Document:
    source_hash = hash_bytes(source_bytes)
    title = parsed_document.title or Path(source_filename).stem or "Untitled document"

    document = Document(
        title=title,
        source_filename=source_filename,
        source_type=source_type,
        source_hash=source_hash,
    )
    session.add(document)
    session.flush()

    for order_index, parsed_record in enumerate(parsed_document.records):
        record = DocumentRecord(
            document_id=document.id,
            stable_id=stable_record_id(
                source_hash,
                order_index,
                chapter_index=parsed_record.chapter_index,
                page_number=parsed_record.page_number,
            ),
            record_type=parsed_record.record_type,
            chapter_index=parsed_record.chapter_index,
            section_title=parsed_record.section_title,
            page_number=parsed_record.page_number,
            order_index=order_index,
            source_text=parsed_record.source_text,
            source_hash=hash_text(parsed_record.source_text),
            metadata_json=build_record_metadata(parsed_record),
        )
        session.add(record)

    session.commit()
    session.refresh(document)
    return document


def list_documents(session: Session) -> list[Document]:
    return list(session.scalars(select(Document).order_by(Document.id)))


def get_document(session: Session, document_id: int) -> Document | None:
    return session.scalar(
        select(Document)
        .options(selectinload(Document.records))
        .where(Document.id == document_id)
    )


def list_document_records(session: Session, document_id: int) -> list[DocumentRecord]:
    return list(
        session.scalars(
            select(DocumentRecord)
            .where(DocumentRecord.document_id == document_id)
            .order_by(DocumentRecord.order_index)
        )
    )


def list_records_for_search(session: Session, document_id: int | None = None) -> list[DocumentRecord]:
    statement = select(DocumentRecord).order_by(DocumentRecord.document_id, DocumentRecord.order_index)
    if document_id is not None:
        statement = statement.where(DocumentRecord.document_id == document_id)
    return list(session.scalars(statement))


def log_search_query(session: Session, query: str) -> SearchQuery:
    search_query = SearchQuery(query=query)
    session.add(search_query)
    session.commit()
    session.refresh(search_query)
    return search_query
