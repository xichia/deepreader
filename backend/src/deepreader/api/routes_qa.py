"""Local extractive QA routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from deepreader.answer.evidence import EvidencePacket, evidence_packets_from_results
from deepreader.answer.extractive_answerer import LocalExtractiveAnswerer
from deepreader.api.routes_documents import get_session
from deepreader.retrieval.indexes import items_from_records, items_from_summaries, retrieve
from deepreader.storage.models import Answer, AnswerCitation
from deepreader.storage.repositories import (
    create_answer,
    get_answer,
    get_document,
    list_answers,
    list_records_for_search,
    list_summaries_for_search,
)

router = APIRouter(tags=["qa"])


class QaRequest(BaseModel):
    question: str = Field(min_length=1)
    document_id: int | None = None
    limit: int = Field(default=8, ge=1, le=50)
    use_source_text: bool = True
    use_summaries: bool = True
    use_local_vector: bool = True
    use_fusion: bool = True


class CitationOut(BaseModel):
    stable_id: str
    record_id: int
    quoted_text: str
    section_title: str | None
    page_number: int | None
    chapter_index: int | None
    order_index: int
    source_hash: str


class EvidenceOut(BaseModel):
    stable_id: str
    record_id: int
    source_text: str
    summary: str | None
    section_title: str | None
    page_number: int | None
    chapter_index: int | None
    order_index: int
    retrieval_method: str
    score: float
    source_hash: str
    metadata: dict[str, Any]
    component_scores: dict[str, float]


class QaResponse(BaseModel):
    answer_id: int | None
    question: str
    answer: str
    confidence: str
    citations: list[CitationOut]
    evidence: list[EvidenceOut]
    used_evidence: list[EvidenceOut]
    unused_evidence: list[EvidenceOut]
    retrieval_settings: dict[str, Any]


class StoredAnswerOut(BaseModel):
    id: int
    document_id: int | None
    question: str
    answer: str
    confidence: str
    citations: list[CitationOut]
    evidence: list[EvidenceOut]
    retrieval_settings: dict[str, Any]
    created_at: str


@router.post("/qa/ask", response_model=QaResponse)
def ask_question(request: QaRequest, session: Session = Depends(get_session)) -> QaResponse:
    if request.document_id is not None and get_document(session, request.document_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    if not request.use_source_text and not request.use_summaries:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one retrieval target must be enabled.",
        )

    records = list_records_for_search(session, request.document_id)
    summaries = list_summaries_for_search(session, request.document_id) if request.use_summaries else []
    retrieval_results = retrieve(
        request.question,
        source_items=items_from_records(records),
        summary_items=items_from_summaries(summaries),
        limit=request.limit,
        use_source_text=request.use_source_text,
        use_summaries=request.use_summaries,
        use_bm25=True,
        use_local_vector=request.use_local_vector,
        use_fusion=request.use_fusion,
    )
    evidence = evidence_packets_from_results(retrieval_results)
    answer = LocalExtractiveAnswerer().answer(request.question, evidence)
    retrieval_settings = request.model_dump()

    stored = create_answer(
        session,
        document_id=request.document_id,
        question=request.question,
        answer_text=answer.answer,
        confidence=answer.confidence,
        retrieval_settings=retrieval_settings,
        evidence=[packet.to_dict() for packet in evidence],
        citations=[citation.to_dict() for citation in answer.citations],
    )

    return QaResponse(
        answer_id=stored.id,
        question=answer.question,
        answer=answer.answer,
        confidence=answer.confidence,
        citations=[CitationOut(**citation.to_dict()) for citation in answer.citations],
        evidence=[evidence_out(packet) for packet in evidence],
        used_evidence=[evidence_out(packet) for packet in answer.used_evidence],
        unused_evidence=[evidence_out(packet) for packet in answer.unused_evidence],
        retrieval_settings=retrieval_settings,
    )


@router.get("/answers", response_model=list[StoredAnswerOut])
def get_answers(
    document_id: int | None = None,
    session: Session = Depends(get_session),
) -> list[StoredAnswerOut]:
    if document_id is not None and get_document(session, document_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return [stored_answer_out(answer) for answer in list_answers(session, document_id)]


@router.get("/answers/{answer_id}", response_model=StoredAnswerOut)
def get_answer_by_id(answer_id: int, session: Session = Depends(get_session)) -> StoredAnswerOut:
    answer = get_answer(session, answer_id)
    if answer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Answer not found.")
    return stored_answer_out(answer)


def evidence_out(packet: EvidencePacket) -> EvidenceOut:
    return EvidenceOut(**packet.to_dict())


def stored_answer_out(answer: Answer) -> StoredAnswerOut:
    return StoredAnswerOut(
        id=answer.id,
        document_id=answer.document_id,
        question=answer.question,
        answer=answer.answer_text,
        confidence=answer.confidence,
        citations=[citation_out(citation) for citation in answer.citations],
        evidence=[EvidenceOut(**packet) for packet in answer.evidence_json],
        retrieval_settings=answer.retrieval_settings_json,
        created_at=answer.created_at.isoformat(),
    )


def citation_out(citation: AnswerCitation) -> CitationOut:
    return CitationOut(
        stable_id=citation.stable_id,
        record_id=citation.record_id,
        quoted_text=citation.quoted_text,
        section_title=citation.section_title,
        page_number=citation.page_number,
        chapter_index=citation.chapter_index,
        order_index=citation.order_index,
        source_hash=citation.source_hash,
    )
