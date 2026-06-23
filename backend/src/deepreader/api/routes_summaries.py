"""Summary generation and inspection routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from deepreader.api.routes_documents import get_session
from deepreader.api.routes_jobs import JobOut, job_out
from deepreader.storage.models import RecordSummary
from deepreader.storage.repositories import get_document, list_document_summaries
from deepreader.summarise.service import SummaryJobRunner

router = APIRouter(prefix="/documents", tags=["summaries"])


class RecordSummaryOut(BaseModel):
    id: int
    document_id: int
    record_id: int
    stable_id: str
    summary_text: str
    summariser_name: str
    summary_hash: str
    source_hash: str
    created_at: str


def summary_out(summary: RecordSummary) -> RecordSummaryOut:
    return RecordSummaryOut(
        id=summary.id,
        document_id=summary.document_id,
        record_id=summary.record_id,
        stable_id=summary.stable_id,
        summary_text=summary.summary_text,
        summariser_name=summary.summariser_name,
        summary_hash=summary.summary_hash,
        source_hash=summary.source_hash,
        created_at=summary.created_at.isoformat(),
    )


@router.post("/{document_id}/summaries/run", response_model=JobOut)
def run_document_summaries(document_id: int, session: Session = Depends(get_session)) -> JobOut:
    if get_document(session, document_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")

    runner = SummaryJobRunner()
    job = runner.run_for_document(session, document_id)
    return job_out(job)


@router.get("/{document_id}/summaries", response_model=list[RecordSummaryOut])
def get_document_summaries(document_id: int, session: Session = Depends(get_session)) -> list[RecordSummaryOut]:
    if get_document(session, document_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    return [summary_out(summary) for summary in list_document_summaries(session, document_id)]
