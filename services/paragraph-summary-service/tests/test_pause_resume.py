import asyncio
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.scheduler.dispatcher import JOBS, JobState
from app.records.schema import InputRecord, SummaryRequest

client = TestClient(app)

def test_pause_resume_state_transitions():
    JOBS.clear()
    job = JobState("job-pr-1", "doc1", 5)
    job.status = "running"
    JOBS["job-pr-1"] = job

    # 1. Pause running job -> paused
    res = client.post("/jobs/job-pr-1/pause")
    assert res.status_code == 200
    assert res.json()["status"] == "paused"
    assert job.status == "paused"
    assert not job._run_gate.is_set()

    # 2. Pause paused job is idempotent
    res = client.post("/jobs/job-pr-1/pause")
    assert res.status_code == 200
    assert res.json()["status"] == "paused"

    # 3. Resume paused job -> running
    res = client.post("/jobs/job-pr-1/resume")
    assert res.status_code == 200
    assert res.json()["status"] == "running"
    assert job.status == "running"
    assert job._run_gate.is_set()

    # 4. Resume running job is idempotent
    res = client.post("/jobs/job-pr-1/resume")
    assert res.status_code == 200
    assert res.json()["status"] == "running"


def test_terminal_jobs_fail_pause_resume():
    JOBS.clear()
    for terminal in ("completed", "failed", "cancelled"):
        job = JobState(f"job-{terminal}", "doc1", 5)
        job.status = terminal
        JOBS[f"job-{terminal}"] = job

        res = client.post(f"/jobs/job-{terminal}/pause")
        assert res.status_code == 409

        res = client.post(f"/jobs/job-{terminal}/resume")
        assert res.status_code == 409


def test_cancel_from_paused():
    JOBS.clear()
    job = JobState("job-cancel", "doc1", 5)
    job.status = "paused"
    job._run_gate.clear()
    JOBS["job-cancel"] = job

    res = client.post("/jobs/job-cancel/cancel")
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"
    assert job.status == "cancelled"
    assert job._run_gate.is_set()  # Gate should wake up workers to exit


@pytest.mark.asyncio
async def test_pause_resume_behavior_with_delayed_batches(monkeypatch):
    from app.config import settings
    from app.scheduler.dispatcher import _run_job_background

    JOBS.clear()
    monkeypatch.setattr(settings, "summary_service_provider", "mock")
    monkeypatch.setattr(settings, "summary_mock_provider_delay_ms", 100)
    monkeypatch.setattr(settings, "summary_batch_max_records", 1)
    monkeypatch.setattr(settings, "summary_lane_count", 1)

    records = [
        InputRecord(record_id=f"r{i}", text="test text", source_hash=f"h{i}")
        for i in range(5)
    ]
    request = SummaryRequest(document_id="doc-pr", records=records)
    job = JobState("job-delay-pr", "doc-pr", 5)
    JOBS["job-delay-pr"] = job

    # Start job
    task = asyncio.create_task(_run_job_background(job, request))
    await asyncio.sleep(0.02)  # yield to let first batch start

    # Pause it
    res = client.post("/jobs/job-delay-pr/pause")
    assert res.status_code == 200
    assert res.json()["status"] == "paused"

    # Wait to ensure only the first (in-flight) batch completes, and no new batches start
    await asyncio.sleep(0.2)
    assert job.status == "paused"
    assert len(job.artifact_lines) == 1
    assert job.completed_records == 1
    assert job.failed_records == 0

    # Resume the job
    res = client.post("/jobs/job-delay-pr/resume")
    assert res.status_code == 200
    assert res.json()["status"] == "running"

    # Wait for the task to finish completely
    await task
    assert job.status == "completed"
    assert job.completed_records == 5
    assert job.failed_records == 0
    assert len(job.artifact_lines) == 5

    # Check for no duplicate record_ids
    record_ids = [line.record_id for line in job.artifact_lines]
    assert len(record_ids) == len(set(record_ids))
