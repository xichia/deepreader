"""Repository functions for documents, jobs, summaries, and search logging."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from deepreader.records.ids import hash_bytes, hash_text, stable_record_id
from deepreader.records.metadata import ParsedDocument, build_record_metadata
from deepreader.storage.models import (
    Answer,
    AnswerCitation,
    Document,
    DocumentRecord,
    Job,
    JobStep,
    RecordSummary,
    SearchQuery,
)

JOB_STATUS_PENDING = "pending"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_COMPLETED = "completed"
JOB_STATUS_FAILED = "failed"

VALID_STATUSES = {
    JOB_STATUS_PENDING,
    JOB_STATUS_RUNNING,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ingest_parsed_document(
    session: Session,
    *,
    parsed_document: ParsedDocument,
    source_filename: str,
    source_type: str,
    source_bytes: bytes | None = None,
    source_hash: Mapped[str] | str | None = None,
) -> Document:
    if source_hash is None:
        if source_bytes is None:
            raise ValueError("Either source_bytes or source_hash must be provided")
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


def get_document_record(session: Session, record_id: int) -> DocumentRecord | None:
    return session.scalar(select(DocumentRecord).where(DocumentRecord.id == record_id))


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


def create_job(
    session: Session,
    *,
    document_id: int,
    job_type: str,
    total_steps: int = 0,
) -> Job:
    job = Job(
        document_id=document_id,
        job_type=job_type,
        status=JOB_STATUS_PENDING,
        total_steps=total_steps,
        completed_steps=0,
        failed_steps=0,
    )
    session.add(job)
    session.flush()
    return job


def create_job_step(
    session: Session,
    *,
    job_id: int,
    step_type: str,
    target_type: str,
    target_id: int,
) -> JobStep:
    step = JobStep(
        job_id=job_id,
        step_type=step_type,
        target_type=target_type,
        target_id=target_id,
        status=JOB_STATUS_PENDING,
        attempt_count=0,
    )
    session.add(step)
    session.flush()
    return step


def set_job_status(
    session: Session,
    job: Job,
    status: str,
    *,
    error_message: str | None = None,
) -> Job:
    _validate_status(status)
    job.status = status
    job.error_message = error_message
    job.updated_at = utc_now()
    if status in {JOB_STATUS_COMPLETED, JOB_STATUS_FAILED}:
        job.finished_at = utc_now()
    else:
        job.finished_at = None
    session.add(job)
    session.flush()
    return job


def set_job_step_status(
    session: Session,
    step: JobStep,
    status: str,
    *,
    error_message: str | None = None,
    increment_attempt: bool = False,
) -> JobStep:
    _validate_status(status)
    step.status = status
    step.error_message = error_message
    if increment_attempt:
        step.attempt_count += 1
    step.updated_at = utc_now()
    if status in {JOB_STATUS_COMPLETED, JOB_STATUS_FAILED}:
        step.finished_at = utc_now()
    else:
        step.finished_at = None
    session.add(step)
    session.flush()
    return step


def refresh_job_progress(session: Session, job: Job) -> Job:
    steps = list_job_steps(session, job.id)
    job.total_steps = len(steps)
    job.completed_steps = sum(1 for step in steps if step.status == JOB_STATUS_COMPLETED)
    job.failed_steps = sum(1 for step in steps if step.status == JOB_STATUS_FAILED)
    job.updated_at = utc_now()
    session.add(job)
    session.flush()
    return job


def list_jobs(session: Session, document_id: int | None = None) -> list[Job]:
    statement = (
        select(Job)
        .options(selectinload(Job.steps))
        .order_by(Job.created_at.desc(), Job.id.desc())
    )
    if document_id is not None:
        statement = statement.where(Job.document_id == document_id)
    return list(session.scalars(statement))


def get_job(session: Session, job_id: int) -> Job | None:
    return session.scalar(
        select(Job)
        .options(selectinload(Job.steps))
        .options(selectinload(Job.document).selectinload(Document.records))
        .where(Job.id == job_id)
    )


def list_job_steps(session: Session, job_id: int) -> list[JobStep]:
    return list(session.scalars(select(JobStep).where(JobStep.job_id == job_id).order_by(JobStep.id)))


def create_record_summary(
    session: Session,
    *,
    record: DocumentRecord,
    summary_text: str,
    summariser_name: str,
    summary_hash: str,
) -> RecordSummary:
    summary = RecordSummary(
        document_id=record.document_id,
        record_id=record.id,
        stable_id=record.stable_id,
        summary_text=summary_text,
        summariser_name=summariser_name,
        summary_hash=summary_hash,
        source_hash=record.source_hash,
    )
    session.add(summary)
    session.flush()
    return summary


def get_record_summary_checkpoint(
    session: Session,
    *,
    record_id: int,
    summariser_name: str,
    source_hash: str,
) -> RecordSummary | None:
    return session.scalar(
        select(RecordSummary)
        .where(RecordSummary.record_id == record_id)
        .where(RecordSummary.summariser_name == summariser_name)
        .where(RecordSummary.source_hash == source_hash)
    )


def list_document_summaries(
    session: Session,
    document_id: int,
    *,
    current_only: bool = True,
    summariser_name: str | None = None,
) -> list[RecordSummary]:
    statement = (
        select(RecordSummary)
        .join(DocumentRecord, RecordSummary.record_id == DocumentRecord.id)
        .options(selectinload(RecordSummary.record))
        .where(RecordSummary.document_id == document_id)
        .order_by(DocumentRecord.order_index, RecordSummary.id)
    )
    if current_only:
        statement = statement.where(RecordSummary.source_hash == DocumentRecord.source_hash)
    if summariser_name is not None:
        statement = statement.where(RecordSummary.summariser_name == summariser_name)
    return list(session.scalars(statement))


def list_summaries_for_search(
    session: Session,
    document_id: int | None = None,
    *,
    summariser_name: str | None = None,
) -> list[RecordSummary]:
    statement = (
        select(RecordSummary)
        .join(DocumentRecord, RecordSummary.record_id == DocumentRecord.id)
        .options(selectinload(RecordSummary.record))
        .where(RecordSummary.source_hash == DocumentRecord.source_hash)
        .order_by(RecordSummary.document_id, DocumentRecord.order_index, RecordSummary.id)
    )
    if document_id is not None:
        statement = statement.where(RecordSummary.document_id == document_id)
    if summariser_name is not None:
        statement = statement.where(RecordSummary.summariser_name == summariser_name)
    return list(session.scalars(statement))


def _validate_status(status: str) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status}")


def create_answer(
    session: Session,
    *,
    document_id: int | None,
    question: str,
    answer_text: str,
    confidence: str,
    retrieval_settings: dict,
    evidence: list[dict],
    citations: list[dict],
) -> Answer:
    answer = Answer(
        document_id=document_id,
        question=question,
        answer_text=answer_text,
        confidence=confidence,
        retrieval_settings_json=retrieval_settings,
        evidence_json=evidence,
    )
    session.add(answer)
    session.flush()

    for citation in citations:
        session.add(
            AnswerCitation(
                answer_id=answer.id,
                record_id=citation["record_id"],
                stable_id=citation["stable_id"],
                quoted_text=citation["quoted_text"],
                section_title=citation.get("section_title"),
                page_number=citation.get("page_number"),
                chapter_index=citation.get("chapter_index"),
                order_index=citation["order_index"],
                source_hash=citation["source_hash"],
            )
        )

    session.commit()
    return get_answer(session, answer.id) or answer


def list_answers(session: Session, document_id: int | None = None) -> list[Answer]:
    statement = (
        select(Answer)
        .options(selectinload(Answer.citations))
        .order_by(Answer.created_at.desc(), Answer.id.desc())
    )
    if document_id is not None:
        statement = statement.where(Answer.document_id == document_id)
    return list(session.scalars(statement))


def get_answer(session: Session, answer_id: int) -> Answer | None:
    return session.scalar(
        select(Answer)
        .options(selectinload(Answer.citations))
        .where(Answer.id == answer_id)
    )
