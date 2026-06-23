"""Synchronous summary job runner with checkpointing."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from deepreader.summarise.checkpoints import find_existing_summary_checkpoint
from deepreader.summarise.local import LocalExtractiveSummariser
from deepreader.summarise.summariser import SummaryInput, Summariser
from deepreader.storage.models import Job
from deepreader.storage.repositories import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    create_job,
    create_job_step,
    create_record_summary,
    get_document,
    list_document_records,
    refresh_job_progress,
    set_job_status,
    set_job_step_status,
)

LOGGER = logging.getLogger(__name__)
SUMMARY_JOB_TYPE = "record_summary"
SUMMARY_STEP_TYPE = "summarise_record"
SUMMARY_TARGET_TYPE = "document_record"


class SummaryJobRunner:
    """Run deterministic record summaries for a document.

    The runner is synchronous for v0.2, but it records jobs and steps as if the
    work were background processing. Existing summaries with the same
    summariser and source hash are treated as checkpoints and skipped.
    """

    def __init__(self, summariser: Summariser | None = None) -> None:
        self.summariser = summariser or LocalExtractiveSummariser()

    def run_for_document(self, session: Session, document_id: int) -> Job:
        document = get_document(session, document_id)
        if document is None:
            raise ValueError(f"Document {document_id} does not exist.")

        records = list_document_records(session, document_id)
        job = create_job(
            session,
            document_id=document_id,
            job_type=SUMMARY_JOB_TYPE,
            total_steps=len(records),
        )
        steps = [
            create_job_step(
                session,
                job_id=job.id,
                step_type=SUMMARY_STEP_TYPE,
                target_type=SUMMARY_TARGET_TYPE,
                target_id=record.id,
            )
            for record in records
        ]
        session.commit()

        LOGGER.info("Started summary job %s for document %s", job.id, document_id)
        set_job_status(session, job, JOB_STATUS_RUNNING)
        session.commit()

        for record, step in zip(records, steps, strict=True):
            try:
                set_job_step_status(session, step, JOB_STATUS_RUNNING, increment_attempt=True)
                session.commit()

                checkpoint = find_existing_summary_checkpoint(
                    session,
                    record=record,
                    summariser_name=self.summariser.name,
                )
                if checkpoint is None:
                    generated = self.summariser.summarise(
                        SummaryInput(
                            stable_id=record.stable_id,
                            source_text=record.source_text,
                            source_hash=record.source_hash,
                            metadata=record.metadata_json,
                        )
                    )
                    create_record_summary(
                        session,
                        record=record,
                        summary_text=generated.summary_text,
                        summariser_name=generated.summariser_name,
                        summary_hash=generated.summary_hash,
                    )
                    LOGGER.info("Summarised record %s for job %s", record.id, job.id)
                else:
                    LOGGER.info("Skipped record %s for job %s; checkpoint exists", record.id, job.id)

                set_job_step_status(session, step, JOB_STATUS_COMPLETED)
            except Exception as exc:  # pragma: no cover - defensive job bookkeeping
                LOGGER.exception("Summary step failed for record %s in job %s", record.id, job.id)
                set_job_step_status(session, step, JOB_STATUS_FAILED, error_message=str(exc))

            refresh_job_progress(session, job)
            session.commit()

        refresh_job_progress(session, job)
        if job.failed_steps:
            set_job_status(session, job, JOB_STATUS_FAILED, error_message="One or more summary steps failed.")
        else:
            set_job_status(session, job, JOB_STATUS_COMPLETED)
        session.commit()
        session.refresh(job)
        LOGGER.info("Finished summary job %s with status %s", job.id, job.status)
        return job
