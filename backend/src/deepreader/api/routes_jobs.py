"""Job inspection routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from deepreader.api.routes_documents import get_session
from deepreader.storage.models import Job, JobStep
from deepreader.storage.repositories import get_job, list_jobs

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobStepOut(BaseModel):
    id: int
    job_id: int
    step_type: str
    target_type: str
    target_id: int
    status: str
    attempt_count: int
    error_message: str | None
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
    error_message: str | None
    created_at: str
    updated_at: str
    finished_at: str | None
    steps: list[JobStepOut] = []


def job_step_out(step: JobStep) -> JobStepOut:
    return JobStepOut(
        id=step.id,
        job_id=step.job_id,
        step_type=step.step_type,
        target_type=step.target_type,
        target_id=step.target_id,
        status=step.status,
        attempt_count=step.attempt_count,
        error_message=step.error_message,
        created_at=step.created_at.isoformat(),
        updated_at=step.updated_at.isoformat(),
        finished_at=step.finished_at.isoformat() if step.finished_at else None,
    )


def job_out(job: Job, *, include_steps: bool = True) -> JobOut:
    return JobOut(
        id=job.id,
        document_id=job.document_id,
        job_type=job.job_type,
        status=job.status,
        total_steps=job.total_steps,
        completed_steps=job.completed_steps,
        failed_steps=job.failed_steps,
        error_message=job.error_message,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        steps=[job_step_out(step) for step in job.steps] if include_steps else [],
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
