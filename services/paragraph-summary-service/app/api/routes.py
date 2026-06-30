from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from typing import Any
import uuid

from app.records.schema import SummaryRequest
from app.scheduler.dispatcher import (
    JOBS,
    JobState,
    ProviderConfigurationError,
    _run_job_background,
    get_job,
    validate_provider_configuration,
)

router = APIRouter()

class JobResponse(BaseModel):
    job_id: str
    status: str
    message: str

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    completed_records: int
    failed_records: int
    total_records: int
    stats: dict[str, Any]
    error: str | None
    created_at: str
    updated_at: str


def job_status_response(job: JobState) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        completed_records=job.completed_records,
        failed_records=job.failed_records,
        total_records=job.total_records,
        stats=job.stats,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )

@router.post("/paragraph-summaries", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_summary_job(request: SummaryRequest, background_tasks: BackgroundTasks):
    if not request.records:
        raise HTTPException(status_code=400, detail="No records provided")
    record_ids = [record.record_id for record in request.records]
    if len(record_ids) != len(set(record_ids)):
        raise HTTPException(status_code=400, detail="Duplicate record_id values are not allowed")
    try:
        validate_provider_configuration()
    except ProviderConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    
    job_id = str(uuid.uuid4())
    job = JobState(job_id, request.document_id, len(request.records))
    JOBS[job_id] = job
    
    background_tasks.add_task(_run_job_background, job, request)
    return JobResponse(job_id=job_id, status="accepted", message="Summary job started")

@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
def read_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_status_response(job)


@router.get("/jobs", response_model=list[JobStatusResponse])
def list_job_statuses():
    """List compact in-memory job summaries without request records or artifacts."""

    return [job_status_response(job) for job in reversed(JOBS.values())]

@router.get("/jobs/{job_id}/artifact")
def read_job_artifact(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="Artifact not ready")
    
    # The backend consumes the artifact as a JSON array of line-shaped objects.
    return [line.model_dump() for line in job.artifact_lines]

@router.post("/jobs/{job_id}/cancel", response_model=JobStatusResponse)
def cancel_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status in {"pending", "running", "accepted", "paused"}:
        job.status = "cancelled"
        job._run_gate.set()
        job.touch()
    return job_status_response(job)

@router.post("/jobs/{job_id}/pause", response_model=JobStatusResponse)
def pause_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == "paused":
        return job_status_response(job)

    if job.status in {"pending", "running", "accepted"}:
        job.status = "paused"
        job._run_gate.clear()
        job.touch()
        return job_status_response(job)

    raise HTTPException(status_code=409, detail=f"Cannot pause job in terminal state: {job.status}")

@router.post("/jobs/{job_id}/resume", response_model=JobStatusResponse)
def resume_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == "running":
        return job_status_response(job)

    if job.status == "paused":
        job.status = "running"
        job._run_gate.set()
        job.touch()
        return job_status_response(job)

    raise HTTPException(status_code=409, detail=f"Cannot resume job from state: {job.status}")

@router.get("/health")
def health_check():
    from app.config import settings
    return {
        "status": "ok",
        "provider": settings.summary_service_provider,
        "model": settings.summary_service_model,
    }
