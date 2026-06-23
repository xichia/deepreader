"""Search routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from deepreader.api.routes_documents import get_session
from deepreader.retrieval.bm25 import search_records
from deepreader.storage.models import DocumentRecord
from deepreader.storage.repositories import get_document, list_records_for_search, log_search_query

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    document_id: int | None = None
    limit: int = Field(default=10, ge=1, le=50)


class SearchResultOut(BaseModel):
    record_id: int
    stable_id: str
    score: float
    retrieval_method: str
    source_text: str
    summary: None
    metadata: dict[str, Any]


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultOut]


def search_result_out(record: DocumentRecord, score: float) -> SearchResultOut:
    return SearchResultOut(
        record_id=record.id,
        stable_id=record.stable_id,
        score=score,
        retrieval_method="bm25_source_text",
        source_text=record.source_text,
        summary=None,
        metadata=record.metadata_json,
    )


@router.post("/search", response_model=SearchResponse)
def search(request: SearchRequest, session: Session = Depends(get_session)) -> SearchResponse:
    if request.document_id is not None and get_document(session, request.document_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    records = list_records_for_search(session, request.document_id)
    hits = search_records(request.query, records, limit=request.limit)
    log_search_query(session, request.query)

    return SearchResponse(
        query=request.query,
        results=[search_result_out(hit.record, hit.score) for hit in hits],
    )
