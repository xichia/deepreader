from fastapi import APIRouter, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from typing import Any
import uuid

from app.records.schema import SummaryRequest, SummaryArtifactLine
from app.scheduler.dispatcher import _run_job_background, get_job, JobState, JOBS

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

@router.post("/paragraph-summaries", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_summary_job(request: SummaryRequest, background_tasks: BackgroundTasks):
    if not request.records:
        raise HTTPException(status_code=400, detail="No records provided")
    record_ids = [record.record_id for record in request.records]
    if len(record_ids) != len(set(record_ids)):
        raise HTTPException(status_code=400, detail="Duplicate record_id values are not allowed")
    
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
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        completed_records=job.completed_records,
        failed_records=job.failed_records,
        total_records=job.total_records,
        stats=job.stats,
    )

@router.get("/jobs/{job_id}/artifact")
def read_job_artifact(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="Artifact not ready")
    
    # The backend consumes the artifact as a JSON array of line-shaped objects.
    return [line.model_dump() for line in job.artifact_lines]

@router.get("/health")
def health_check():
    from app.config import settings
    return {"status": "ok", "provider": settings.summary_service_provider}
