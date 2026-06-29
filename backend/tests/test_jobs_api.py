from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from deepreader.storage.db import build_engine, init_db
from deepreader.storage.repositories import (
    JOB_STATUS_FAILED,
    get_job,
    refresh_job_progress,
    set_job_status,
    set_job_remote_progress,
    set_job_step_status,
)


def test_jobs_api_lists_and_reads_jobs(client: TestClient, examples_dir: Path) -> None:
    source_path = examples_dir / "troubleshooting_log.txt"
    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    document_id = ingest_response.json()["document"]["id"]
    job = client.post(f"/documents/{document_id}/summaries/run").json()

    list_response = client.get("/jobs")
    assert list_response.status_code == 200
    jobs = list_response.json()
    assert jobs[0]["id"] == job["id"]
    assert jobs[0]["job_type"] == "record_summary"
    assert jobs[0]["status"] == "completed"
    assert jobs[0]["remote_job_id"] is None
    assert jobs[0]["remote_status"] is None
    assert jobs[0]["remote_stats"] == {}
    assert jobs[0]["steps"] == []

    detail_response = client.get(f"/jobs/{job['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["completed_steps"] == detail["total_steps"]
    assert detail["steps"]
    assert detail["steps"][0]["target_stable_id"]


def test_jobs_api_returns_404_for_missing_job(client: TestClient) -> None:
    response = client.get("/jobs/999")

    assert response.status_code == 404


def test_jobs_api_exposes_persisted_remote_progress(client: TestClient, examples_dir: Path) -> None:
    source_path = examples_dir / "simple_manual.txt"
    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    document_id = ingest_response.json()["document"]["id"]
    job_payload = client.post(f"/documents/{document_id}/summaries/run").json()

    with client.app.state.SessionLocal() as session:
        job = get_job(session, job_payload["id"])
        assert job is not None
        set_job_remote_progress(
            session,
            job,
            remote_job_id="remote-observable-1",
            status_data={
                "status": "running",
                "completed_records": 2,
                "failed_records": 1,
                "total_records": 5,
                "stats": {"provider": "gemini", "completed_batches": 1},
            },
        )
        session.commit()

    response = client.get(f"/jobs/{job_payload['id']}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["remote_job_id"] == "remote-observable-1"
    assert payload["remote_status"] == "running"
    assert payload["remote_completed_records"] == 2
    assert payload["remote_failed_records"] == 1
    assert payload["remote_total_records"] == 5
    assert payload["remote_stats"]["provider"] == "gemini"


def test_init_db_migrates_existing_sqlite_jobs_for_remote_observability(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'legacy.sqlite3'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    job_type VARCHAR(100) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    total_steps INTEGER NOT NULL,
                    completed_steps INTEGER NOT NULL,
                    failed_steps INTEGER NOT NULL,
                    error_message TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    finished_at DATETIME
                )
                """
            )
        )

    init_db(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("jobs")}
    assert {"remote_job_id", "remote_progress_json"} <= columns
    engine.dispose()


def test_jobs_api_lists_job_steps(client: TestClient, examples_dir: Path) -> None:
    source_path = examples_dir / "simple_manual.txt"
    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    document_id = ingest_response.json()["document"]["id"]
    job = client.post(f"/documents/{document_id}/summaries/run").json()

    response = client.get(f"/jobs/{job['id']}/steps")

    assert response.status_code == 200
    steps = response.json()
    assert steps
    assert {step["status"] for step in steps} == {"completed"}
    assert all(step["target_stable_id"] for step in steps)


def test_jobs_api_retries_failed_summary_steps(client: TestClient, examples_dir: Path) -> None:
    source_path = examples_dir / "simple_manual.txt"
    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    document_id = ingest_response.json()["document"]["id"]
    job_payload = client.post(f"/documents/{document_id}/summaries/run").json()

    app = client.app
    session_factory = app.state.SessionLocal
    with session_factory() as session:
        job = get_job(session, job_payload["id"])
        assert job is not None
        failed_step = job.steps[0]
        first_attempt_count = failed_step.attempt_count
        set_job_step_status(session, failed_step, JOB_STATUS_FAILED, error_message="forced retry regression")
        refresh_job_progress(session, job)
        set_job_status(session, job, JOB_STATUS_FAILED, error_message="forced retry regression")
        session.commit()

    retry_response = client.post(f"/jobs/{job_payload['id']}/retry-failed")

    assert retry_response.status_code == 200
    retried_job = retry_response.json()
    assert retried_job["status"] == "completed"
    assert retried_job["failed_steps"] == 0
    assert retried_job["completed_steps"] == retried_job["total_steps"]
    retried_step = [step for step in retried_job["steps"] if step["error_message"] is None][0]
    assert retried_step["status"] == "completed"
    assert retried_step["attempt_count"] == first_attempt_count + 1
