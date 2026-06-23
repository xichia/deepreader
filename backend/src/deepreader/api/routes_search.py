"""Search routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from deepreader.api.routes_documents import get_session
from deepreader.retrieval.indexes import items_from_records, items_from_summaries, retrieve
from deepreader.retrieval.schemas import RetrievalResult
from deepreader.storage.repositories import (
    get_document,
    list_records_for_search,
    list_summaries_for_search,
    log_search_query,
)

router = APIRouter(tags=["search"])


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    document_id: int | None = None
    limit: int = Field(default=10, ge=1, le=50)
    search_source_text: bool = True
    search_summaries: bool = False
    use_local_vector: bool = False
    use_fusion: bool = False


class SearchResultOut(BaseModel):
    record_id: int
    stable_id: str
    score: float
    retrieval_method: str
    source_text: str
    summary: str | None
    metadata: dict[str, Any]
    component_scores: dict[str, float] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultOut]


def search_result_out(result: RetrievalResult) -> SearchResultOut:
    return SearchResultOut(
        record_id=result.record_id,
        stable_id=result.stable_id,
        score=result.score,
        retrieval_method=result.retrieval_method,
        source_text=result.source_text,
        summary=result.summary,
        metadata=result.metadata,
        component_scores=result.component_scores,
    )


@router.post("/search", response_model=SearchResponse)
def search(request: SearchRequest, session: Session = Depends(get_session)) -> SearchResponse:
    if request.document_id is not None and get_document(session, request.document_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    if not request.search_source_text and not request.search_summaries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one search target must be enabled.",
        )

    records = list_records_for_search(session, request.document_id)
    summaries = list_summaries_for_search(session, request.document_id) if request.search_summaries else []
    retrieval_results = retrieve(
        request.query,
        source_items=items_from_records(records),
        summary_items=items_from_summaries(summaries),
        limit=request.limit,
        use_source_text=request.search_source_text,
        use_summaries=request.search_summaries,
        use_bm25=True,
        use_local_vector=request.use_local_vector,
        use_fusion=request.use_fusion,
    )
    log_search_query(session, request.query)

    return SearchResponse(
        query=request.query,
        results=[search_result_out(result) for result in retrieval_results],
    )
