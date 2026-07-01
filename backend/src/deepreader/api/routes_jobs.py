"""Job inspection routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from deepreader.api.routes_documents import get_session
from deepreader.summarise.service import SummaryJobRunner
from deepreader.storage.models import Job, JobStep
from deepreader.storage.repositories import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_FAILED,
    get_job,
    list_job_steps,
    list_jobs,
    refresh_job_progress,
    set_job_status,
    set_job_step_status,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobStepOut(BaseModel):
    id: int
    job_id: int
    step_type: str
    target_type: str
    target_id: int
    target_stable_id: str | None
    status: str
    attempt_count: int
    error_message: str | None
    error_code: str | None
    created_at: str
    updated_at: str
    finished_at: str | None


class JobOut(BaseModel):
    id: int
    document_id: int
    job_type: str
    status: str
    total_steps: int
    completed_steps: int
    failed_steps: int
    skipped_steps: int
    error_message: str | None
    remote_job_id: str | None
    remote_status: str | None
    remote_completed_records: int | None
    remote_failed_records: int | None
    remote_total_records: int | None
    remote_stats: dict
    remote_error: str | None
    created_at: str
    updated_at: str
    finished_at: str | None
    steps: list[JobStepOut] = []


def job_step_out(step: JobStep, *, target_stable_id: str | None = None) -> JobStepOut:
    return JobStepOut(
        id=step.id,
        job_id=step.job_id,
        step_type=step.step_type,
        target_type=step.target_type,
        target_id=step.target_id,
        target_stable_id=target_stable_id,
        status=step.status,
        attempt_count=step.attempt_count,
        error_message=step.error_message,
        error_code=step.error_code,
        created_at=step.created_at.isoformat(),
        updated_at=step.updated_at.isoformat(),
        finished_at=step.finished_at.isoformat() if step.finished_at else None,
    )


def job_out(job: Job, *, include_steps: bool = True) -> JobOut:
    stable_ids = _target_stable_ids(job)
    remote_progress = job.remote_progress_json or {}
    return JobOut(
        id=job.id,
        document_id=job.document_id,
        job_type=job.job_type,
        status=job.status,
        total_steps=job.total_steps,
        completed_steps=job.completed_steps,
        failed_steps=job.failed_steps,
        skipped_steps=job.skipped_steps,
        error_message=job.error_message,
        remote_job_id=job.remote_job_id,
        remote_status=remote_progress.get("remote_status"),
        remote_completed_records=remote_progress.get("remote_completed_records"),
        remote_failed_records=remote_progress.get("remote_failed_records"),
        remote_total_records=remote_progress.get("remote_total_records"),
        remote_stats=(
            remote_progress.get("remote_stats")
            if isinstance(remote_progress.get("remote_stats"), dict)
            else {}
        ),
        remote_error=remote_progress.get("remote_error"),
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        steps=[job_step_out(step, target_stable_id=stable_ids.get(step.target_id)) for step in job.steps]
        if include_steps
        else [],
    )


@router.get("", response_model=list[JobOut])
def get_jobs(session: Session = Depends(get_session)) -> list[JobOut]:
    return [job_out(job, include_steps=False) for job in list_jobs(session)]


@router.get("/{job_id}", response_model=JobOut)
def get_job_by_id(job_id: int, session: Session = Depends(get_session)) -> JobOut:
    job = get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    return job_out(job)


@router.get("/{job_id}/steps", response_model=list[JobStepOut])
def get_job_steps_by_id(job_id: int, session: Session = Depends(get_session)) -> list[JobStepOut]:
    job = get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    stable_ids = _target_stable_ids(job)
    return [
        job_step_out(step, target_stable_id=stable_ids.get(step.target_id))
        for step in list_job_steps(session, job_id)
    ]


@router.post("/{job_id}/retry-failed", response_model=JobOut)
def retry_failed_job_steps(job_id: int, session: Session = Depends(get_session)) -> JobOut:
    if get_job(session, job_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    try:
        job = SummaryJobRunner().retry_failed_steps(session, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return job_out(job)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job_endpoint(job_id: int, session: Session = Depends(get_session)) -> JobOut:
    job = get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    if job.status not in {"pending", "running", "paused"}:
        return job_out(job)

    if job.remote_job_id:
        import httpx
        import logging
        from deepreader.summarise.remote_client import RemoteSummaryClient

        try:
            client = RemoteSummaryClient()
            client.cancel_job(job.remote_job_id)
        except Exception as exc:
            cause = exc.__cause__
            # A 404 from the remote service means the remote job no longer
            # exists and cannot be consuming quota; treat it as benign.
            if isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code == 404:
                logging.getLogger(__name__).info(
                    "Remote job %s not found during cancel; proceeding with local cancel.",
                    job.remote_job_id,
                )
            else:
                logging.getLogger(__name__).warning(
                    "Failed to cancel remote job %s: %s", job.remote_job_id, exc
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to cancel remote summary job; remote job may still be running.",
                )

    set_job_status(session, job, JOB_STATUS_CANCELLED)
    for step in job.steps:
        # No unfinished step should remain pending/running/paused after the
        # parent job is cancelled; mark each as terminally failed.
        if step.status in {"pending", "running", "paused"}:
            set_job_step_status(session, step, JOB_STATUS_FAILED, error_message="Job was cancelled.")
    refresh_job_progress(session, job)
    session.commit()

    return job_out(job)


@router.post("/{job_id}/pause", response_model=JobOut)
def pause_job_endpoint(job_id: int, session: Session = Depends(get_session)) -> JobOut:
    job = get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    if not job.remote_job_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local inline jobs are not pausable."
        )

    import httpx
    from deepreader.summarise.remote_client import RemoteSummaryClient
    from deepreader.storage.repositories import set_job_remote_progress

    try:
        client = RemoteSummaryClient()
        remote_res = client.pause_job(job.remote_job_id)
    except Exception as exc:
        cause = exc.__cause__
        if isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code == 409:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Remote transition conflict."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Remote summary service unavailable."
            )

    set_job_remote_progress(session, job, remote_job_id=job.remote_job_id, status_data=remote_res)
    job.status = "paused"
    job.finished_at = None
    session.commit()

    return job_out(job)


@router.post("/{job_id}/resume", response_model=JobOut)
def resume_job_endpoint(job_id: int, session: Session = Depends(get_session)) -> JobOut:
    job = get_job(session, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    if not job.remote_job_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Local inline jobs are not resumable."
        )

    import httpx
    from deepreader.summarise.remote_client import RemoteSummaryClient
    from deepreader.storage.repositories import set_job_remote_progress

    try:
        client = RemoteSummaryClient()
        remote_res = client.resume_job(job.remote_job_id)
    except Exception as exc:
        cause = exc.__cause__
        if isinstance(cause, httpx.HTTPStatusError) and cause.response.status_code == 409:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Remote transition conflict."
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Remote summary service unavailable."
            )

    set_job_remote_progress(session, job, remote_job_id=job.remote_job_id, status_data=remote_res)
    job.status = "running"
    job.finished_at = None
    session.commit()

    return job_out(job)


def _target_stable_ids(job: Job) -> dict[int, str]:
    if job.document is None:
        return {}
    return {record.id: record.stable_id for record in job.document.records}
