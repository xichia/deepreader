"""Synchronous summary job runner with checkpointing."""

from __future__ import annotations

import logging
import os
import time

from sqlalchemy.orm import Session

from deepreader.summarise.checkpoints import find_existing_summary_checkpoint
from deepreader.summarise.local import LocalExtractiveSummariser
from deepreader.summarise.summariser import SummaryInput, Summariser
from deepreader.storage.models import DocumentRecord, Job, JobStep
from deepreader.storage.repositories import (
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_RUNNING,
    create_job,
    create_job_step,
    create_record_summary,
    get_document_record,
    get_document,
    get_job,
    list_document_records,
    list_job_steps,
    refresh_job_progress,
    set_job_status,
    set_job_step_status,
)

LOGGER = logging.getLogger(__name__)
SUMMARY_JOB_TYPE = "record_summary"
SUMMARY_STEP_TYPE = "summarise_record"
SUMMARY_TARGET_TYPE = "document_record"
REMOTE_SUMMARISER_NAME = "mock"
REMOTE_MAX_POLLS = 60
REMOTE_POLL_INTERVAL_SECONDS = 2


class SummaryJobRunner:
    """Run deterministic record summaries for a document.

    Local work runs inline. The optional remote path also keeps this backend
    call synchronous while it polls the paragraph service. Existing summaries
    with the same summariser and source hash are treated as checkpoints.
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

        backend = os.getenv("DEEPREADER_SUMMARY_BACKEND", "local")
        allow_remote = os.getenv("DEEPREADER_ALLOW_REMOTE_SUMMARY_SERVICE", "false").lower() == "true"

        if backend == "remote" and allow_remote:
            return self._run_remote_job(session, job, records, steps)

        for record, step in zip(records, steps, strict=True):
            self._run_record_step(session, job, record, step)

        refresh_job_progress(session, job)
        if job.failed_steps:
            set_job_status(session, job, JOB_STATUS_FAILED, error_message="One or more summary steps failed.")
        else:
            set_job_status(session, job, JOB_STATUS_COMPLETED)
        session.commit()
        session.refresh(job)
        LOGGER.info("Finished summary job %s with status %s", job.id, job.status)
        return job

    def _run_remote_job(
        self,
        session: Session,
        job: Job,
        records: list[DocumentRecord],
        steps: list[JobStep],
    ) -> Job:
        from deepreader.summarise.artifact_importer import import_summary_artifact
        from deepreader.summarise.remote_client import RemoteSummaryClient

        remote_job_id: str | None = None
        submitted_stable_ids: set[str] = set()

        try:
            records_to_send = []
            for record, step in zip(records, steps, strict=True):
                set_job_step_status(session, step, JOB_STATUS_RUNNING, increment_attempt=True)
                checkpoint = find_existing_summary_checkpoint(
                    session,
                    record=record,
                    summariser_name=REMOTE_SUMMARISER_NAME,
                )
                if checkpoint is not None:
                    set_job_step_status(session, step, JOB_STATUS_COMPLETED)
                    continue

                submitted_stable_ids.add(record.stable_id)
                records_to_send.append(
                    {
                        "record_id": record.stable_id,
                        "stable_id": record.stable_id,
                        "source_ref": f"chapter {record.chapter_index}" if record.chapter_index is not None else None,
                        "text": record.source_text,
                        "source_hash": record.source_hash,
                        "metadata": record.metadata_json,
                    }
                )

            refresh_job_progress(session, job)
            session.commit()

            if not records_to_send:
                set_job_status(session, job, JOB_STATUS_COMPLETED)
                session.commit()
                session.refresh(job)
                return job

            client = RemoteSummaryClient()
            remote_job_id = client.submit_job(str(job.document_id), records_to_send)

            status_data: dict = {}
            for poll_number in range(REMOTE_MAX_POLLS):
                status_data = client.get_job_status(remote_job_id)
                if status_data.get("status") in {"completed", "failed"}:
                    break
                if poll_number < REMOTE_MAX_POLLS - 1:
                    time.sleep(REMOTE_POLL_INTERVAL_SECONDS)
            else:
                raise TimeoutError(f"Remote summary job {remote_job_id} did not finish before the polling timeout.")

            artifact = client.get_job_artifact(remote_job_id)
            import_stats = import_summary_artifact(session, job.document_id, artifact)
            imported_ids = set(import_stats["imported_record_ids"])
            skipped_ids = set(import_stats["skipped_record_ids"])
            failed_ids = set(import_stats["failed_record_ids"])

            remote_failed = status_data.get("status") == "failed"
            if remote_failed and not failed_ids:
                failed_ids = submitted_stable_ids

            for record, step in zip(records, steps, strict=True):
                if record.stable_id not in submitted_stable_ids:
                    continue
                if record.stable_id in failed_ids:
                    set_job_step_status(
                        session,
                        step,
                        JOB_STATUS_FAILED,
                        error_message="Remote summary artifact reported or contained an invalid result.",
                    )
                elif record.stable_id in imported_ids or record.stable_id in skipped_ids:
                    set_job_step_status(session, step, JOB_STATUS_COMPLETED)
                else:
                    set_job_step_status(
                        session,
                        step,
                        JOB_STATUS_FAILED,
                        error_message="Remote summary artifact did not contain this record.",
                    )

            refresh_job_progress(session, job)
            if job.failed_steps or remote_failed or import_stats["failed"]:
                details = "; ".join(import_stats["errors"])
                error_message = f"Remote summary job {remote_job_id} failed."
                if details:
                    error_message = f"{error_message} Import errors: {details}"
                set_job_status(session, job, JOB_STATUS_FAILED, error_message=error_message)
            else:
                set_job_status(session, job, JOB_STATUS_COMPLETED)
            session.commit()
            session.refresh(job)
            LOGGER.info("Imported %s remote summaries for job %s", import_stats["imported"], job.id)
            return job
        except Exception as exc:
            session.rollback()
            persisted_job = get_job(session, job.id)
            if persisted_job is None:  # pragma: no cover - defensive persistence guard
                raise
            prefix = f"Remote summary job {remote_job_id} failed" if remote_job_id else "Remote summary submission failed"
            error_message = f"{prefix}: {exc}"
            LOGGER.error("%s", error_message)
            for step in list_job_steps(session, persisted_job.id):
                if step.status != JOB_STATUS_COMPLETED:
                    set_job_step_status(session, step, JOB_STATUS_FAILED, error_message=error_message)
            refresh_job_progress(session, persisted_job)
            set_job_status(session, persisted_job, JOB_STATUS_FAILED, error_message=error_message)
            session.commit()
            session.refresh(persisted_job)
            return persisted_job

    def retry_failed_steps(self, session: Session, job_id: int) -> Job:
        job = get_job(session, job_id)
        if job is None:
            raise ValueError(f"Job {job_id} does not exist.")
        if job.job_type != SUMMARY_JOB_TYPE:
            raise ValueError(f"Job {job_id} is not a summary job.")

        failed_steps = [step for step in list_job_steps(session, job.id) if step.status == JOB_STATUS_FAILED]
        if not failed_steps:
            return job

        LOGGER.info("Retrying %s failed summary steps for job %s", len(failed_steps), job.id)
        set_job_status(session, job, JOB_STATUS_RUNNING)
        session.commit()

        for step in failed_steps:
            record = get_document_record(session, step.target_id)
            if record is None:
                set_job_step_status(
                    session,
                    step,
                    JOB_STATUS_FAILED,
                    error_message=f"Target record {step.target_id} no longer exists.",
                    increment_attempt=True,
                )
                refresh_job_progress(session, job)
                session.commit()
                continue
            self._run_record_step(session, job, record, step)

        refresh_job_progress(session, job)
        if job.failed_steps:
            set_job_status(session, job, JOB_STATUS_FAILED, error_message="One or more summary steps failed.")
        else:
            set_job_status(session, job, JOB_STATUS_COMPLETED)
        session.commit()
        session.refresh(job)
        return job

    def _run_record_step(
        self,
        session: Session,
        job: Job,
        record: DocumentRecord,
        step: JobStep,
    ) -> None:
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
