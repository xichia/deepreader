from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from deepreader.storage.db import build_engine, init_db
from deepreader.storage.models import Document
from deepreader.storage.repositories import (
    JOB_STATUS_CANCELLED,
    JOB_STATUS_COMPLETED,
    JOB_STATUS_FAILED,
    JOB_STATUS_PAUSED,
    JOB_STATUS_RUNNING,
    JOB_STATUS_SKIPPED,
    create_job,
    create_job_step,
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


def test_jobs_api_cancels_active_job(client: TestClient, examples_dir: Path, monkeypatch) -> None:
    source_path = examples_dir / "simple_manual.txt"
    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    document_id = ingest_response.json()["document"]["id"]
    job_payload = client.post(f"/documents/{document_id}/summaries/run").json()

    # Manually mark the job status as running to simulate in-progress
    with client.app.state.SessionLocal() as session:
        job = get_job(session, job_payload["id"])
        assert job is not None
        job.status = "running"
        job.remote_job_id = "mock-remote-id"
        session.commit()

    # Mock the remote summary client's cancel call
    remote_cancel_calls = []
    class MockRemoteClient:
        def __init__(self):
            pass
        def cancel_job(self, remote_job_id: str):
            remote_cancel_calls.append(remote_job_id)
            return {"job_id": remote_job_id, "status": "cancelled"}

    from deepreader.summarise import remote_client
    monkeypatch.setattr(remote_client, "RemoteSummaryClient", MockRemoteClient)

    cancel_response = client.post(f"/jobs/{job_payload['id']}/cancel")

    assert cancel_response.status_code == 200
    payload = cancel_response.json()
    assert payload["status"] == "cancelled"
    assert remote_cancel_calls == ["mock-remote-id"]


def test_jobs_api_pause_and_resume_routes(client: TestClient, examples_dir: Path, monkeypatch) -> None:
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
        job.status = "running"
        job.remote_job_id = "mock-remote-id"
        session.commit()

    remote_pause_calls = []
    remote_resume_calls = []

    class MockRemoteClient:
        def __init__(self):
            pass
        def pause_job(self, remote_job_id: str):
            remote_pause_calls.append(remote_job_id)
            return {"job_id": remote_job_id, "status": "paused"}
        def resume_job(self, remote_job_id: str):
            remote_resume_calls.append(remote_job_id)
            return {"job_id": remote_job_id, "status": "running"}

    from deepreader.summarise import remote_client
    monkeypatch.setattr(remote_client, "RemoteSummaryClient", MockRemoteClient)

    # Pause
    pause_response = client.post(f"/jobs/{job_payload['id']}/pause")
    assert pause_response.status_code == 200
    payload = pause_response.json()
    assert payload["status"] == "paused"
    assert remote_pause_calls == ["mock-remote-id"]

    # Resume
    resume_response = client.post(f"/jobs/{job_payload['id']}/resume")
    assert resume_response.status_code == 200
    payload = resume_response.json()
    assert payload["status"] == "running"
    assert remote_resume_calls == ["mock-remote-id"]


def test_jobs_api_pause_resume_no_remote_id_returns_409(client: TestClient, examples_dir: Path) -> None:
    source_path = examples_dir / "simple_manual.txt"
    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    document_id = ingest_response.json()["document"]["id"]
    job_payload = client.post(f"/documents/{document_id}/summaries/run").json()

    # Local job has no remote_job_id
    pause_response = client.post(f"/jobs/{job_payload['id']}/pause")
    assert pause_response.status_code == 409
    assert "local inline jobs are not pausable" in pause_response.json()["detail"].lower()

    resume_response = client.post(f"/jobs/{job_payload['id']}/resume")
    assert resume_response.status_code == 409
    assert "local inline jobs are not resumable" in resume_response.json()["detail"].lower()


def test_jobs_api_remote_transition_conflict_returns_409(client: TestClient, examples_dir: Path, monkeypatch) -> None:
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
        job.status = "running"
        job.remote_job_id = "mock-remote-id"
        session.commit()

    import httpx

    class MockRemoteClient:
        def __init__(self):
            pass
        def pause_job(self, remote_job_id: str):
            request = httpx.Request("POST", "http://test/jobs/mock-remote-id/pause")
            response = httpx.Response(409, request=request, json={"detail": "Conflict"})
            exc = httpx.HTTPStatusError("Conflict", request=request, response=response)
            raise RuntimeError("Conflict error") from exc

    from deepreader.summarise import remote_client
    monkeypatch.setattr(remote_client, "RemoteSummaryClient", MockRemoteClient)

    pause_response = client.post(f"/jobs/{job_payload['id']}/pause")
    assert pause_response.status_code == 409
    assert "remote transition conflict" in pause_response.json()["detail"].lower()

    # Verify status is unchanged
    detail_response = client.get(f"/jobs/{job_payload['id']}")
    assert detail_response.json()["status"] == "running"


def test_jobs_api_remote_unavailable_returns_502(client: TestClient, examples_dir: Path, monkeypatch) -> None:
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
        job.status = "running"
        job.remote_job_id = "mock-remote-id"
        session.commit()

    import httpx

    class MockRemoteClient:
        def __init__(self):
            pass
        def pause_job(self, remote_job_id: str):
            request = httpx.Request("POST", "http://test/jobs/mock-remote-id/pause")
            exc = httpx.ConnectError("Connection refused", request=request)
            raise RuntimeError("Connection error") from exc

    from deepreader.summarise import remote_client
    monkeypatch.setattr(remote_client, "RemoteSummaryClient", MockRemoteClient)

    pause_response = client.post(f"/jobs/{job_payload['id']}/pause")
    assert pause_response.status_code == 502
    assert "remote summary service unavailable" in pause_response.json()["detail"].lower()

    # Verify status is unchanged
    detail_response = client.get(f"/jobs/{job_payload['id']}")
    assert detail_response.json()["status"] == "running"


def test_jobs_api_cancel_from_paused(client: TestClient, examples_dir: Path, monkeypatch) -> None:
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
        job.status = "paused"
        job.remote_job_id = "mock-remote-id"
        session.commit()

    remote_cancel_calls = []
    class MockRemoteClient:
        def __init__(self):
            pass
        def cancel_job(self, remote_job_id: str):
            remote_cancel_calls.append(remote_job_id)
            return {"job_id": remote_job_id, "status": "cancelled"}

    from deepreader.summarise import remote_client
    monkeypatch.setattr(remote_client, "RemoteSummaryClient", MockRemoteClient)

    cancel_response = client.post(f"/jobs/{job_payload['id']}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"
    assert remote_cancel_calls == ["mock-remote-id"]


def test_jobs_api_cancel_remote_failure_returns_502(client: TestClient, examples_dir: Path, monkeypatch) -> None:
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
        set_job_status(session, job, JOB_STATUS_RUNNING)
        job.remote_job_id = "mock-remote-id"
        session.commit()

    import httpx

    class MockRemoteClient:
        def __init__(self):
            pass
        def cancel_job(self, remote_job_id: str):
            request = httpx.Request("POST", f"http://test/jobs/{remote_job_id}/cancel")
            exc = httpx.ConnectError("Connection refused", request=request)
            raise RuntimeError("Remote summary service error: Connection refused") from exc

    from deepreader.summarise import remote_client
    monkeypatch.setattr(remote_client, "RemoteSummaryClient", MockRemoteClient)

    cancel_response = client.post(f"/jobs/{job_payload['id']}/cancel")
    assert cancel_response.status_code == 502
    assert "remote job may still be running" in cancel_response.json()["detail"].lower()

    detail_response = client.get(f"/jobs/{job_payload['id']}")
    assert detail_response.status_code == 200
    # Local job must NOT be marked cancelled when the remote cancel failed.
    assert detail_response.json()["status"] == "running"


def test_jobs_api_cancel_remote_404_proceeds_with_local_cancel(client: TestClient, examples_dir: Path, monkeypatch) -> None:
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
        set_job_status(session, job, JOB_STATUS_RUNNING)
        job.remote_job_id = "mock-remote-id"
        session.commit()

    import httpx

    class MockRemoteClient:
        def __init__(self):
            pass
        def cancel_job(self, remote_job_id: str):
            request = httpx.Request("POST", f"http://test/jobs/{remote_job_id}/cancel")
            response = httpx.Response(404, request=request, json={"detail": "Job not found"})
            exc = httpx.HTTPStatusError("Not Found", request=request, response=response)
            raise RuntimeError("Remote summary service error: 404") from exc

    from deepreader.summarise import remote_client
    monkeypatch.setattr(remote_client, "RemoteSummaryClient", MockRemoteClient)

    cancel_response = client.post(f"/jobs/{job_payload['id']}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"


def test_jobs_api_cancel_remote_success_refreshes_progress(client: TestClient, examples_dir: Path, monkeypatch) -> None:
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
        steps = job.steps
        set_job_status(session, job, JOB_STATUS_RUNNING)
        set_job_step_status(session, steps[0], JOB_STATUS_COMPLETED)
        for step in steps[1:]:
            set_job_step_status(session, step, JOB_STATUS_RUNNING)
        refresh_job_progress(session, job)
        job.remote_job_id = "mock-remote-id"
        session.commit()

    class MockRemoteClient:
        def __init__(self):
            pass
        def cancel_job(self, remote_job_id: str):
            return {"job_id": remote_job_id, "status": "cancelled"}

    from deepreader.summarise import remote_client
    monkeypatch.setattr(remote_client, "RemoteSummaryClient", MockRemoteClient)

    cancel_response = client.post(f"/jobs/{job_payload['id']}/cancel")
    assert cancel_response.status_code == 200
    payload = cancel_response.json()
    assert payload["status"] == "cancelled"
    assert payload["finished_at"] is not None
    total = payload["total_steps"]
    assert payload["completed_steps"] == 1
    assert payload["failed_steps"] == total - 1
    # Counters reflect all terminal accounting.
    assert payload["completed_steps"] + payload["failed_steps"] == total


def test_jobs_api_cancel_local_running_job_refreshes_progress(client: TestClient, examples_dir: Path) -> None:
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
        steps = job.steps
        set_job_status(session, job, JOB_STATUS_RUNNING)
        set_job_step_status(session, steps[0], JOB_STATUS_COMPLETED)
        for step in steps[1:]:
            set_job_step_status(session, step, JOB_STATUS_RUNNING)
        refresh_job_progress(session, job)
        # No remote_job_id: local inline job.
        session.commit()

    cancel_response = client.post(f"/jobs/{job_payload['id']}/cancel")
    assert cancel_response.status_code == 200
    payload = cancel_response.json()
    assert payload["status"] == "cancelled"
    assert payload["finished_at"] is not None
    total = payload["total_steps"]
    assert payload["completed_steps"] == 1
    assert payload["failed_steps"] == total - 1
    assert payload["completed_steps"] + payload["failed_steps"] == total


def test_jobs_api_cancel_terminates_paused_steps(client: TestClient, examples_dir: Path) -> None:
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
        steps = job.steps
        # At least one completed, one running, and one paused unfinished step.
        set_job_status(session, job, JOB_STATUS_PAUSED)
        set_job_step_status(session, steps[0], JOB_STATUS_COMPLETED)
        set_job_step_status(session, steps[1], JOB_STATUS_RUNNING)
        for step in steps[2:]:
            set_job_step_status(session, step, JOB_STATUS_PAUSED)
        refresh_job_progress(session, job)
        # No remote_job_id: local inline job.
        session.commit()

    cancel_response = client.post(f"/jobs/{job_payload['id']}/cancel")
    assert cancel_response.status_code == 200
    payload = cancel_response.json()
    assert payload["status"] == "cancelled"
    assert payload["finished_at"] is not None

    total = payload["total_steps"]
    completed = payload["completed_steps"]
    failed = payload["failed_steps"]
    # The previously-completed step stays completed; all previously running or
    # paused steps must now be terminally failed, with counters refreshed.
    assert completed == 1
    assert failed == total - 1
    assert completed + failed == total

    # Re-fetch steps and assert no unfinished step remains pending/running/paused.
    steps_response = client.get(f"/jobs/{job_payload['id']}/steps")
    assert steps_response.status_code == 200
    step_statuses = {step["status"] for step in steps_response.json()}
    assert step_statuses <= {"completed", "failed"}
    assert "paused" not in step_statuses
    assert "running" not in step_statuses
    assert "pending" not in step_statuses


def test_jobs_api_cancel_already_cancelled_is_idempotent(client: TestClient, examples_dir: Path, monkeypatch) -> None:
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
        set_job_status(session, job, JOB_STATUS_CANCELLED)
        job.remote_job_id = "mock-remote-id"
        session.commit()

    remote_cancel_calls = []

    class MockRemoteClient:
        def __init__(self):
            pass
        def cancel_job(self, remote_job_id: str):
            remote_cancel_calls.append(remote_job_id)
            return {"job_id": remote_job_id, "status": "cancelled"}

    from deepreader.summarise import remote_client
    monkeypatch.setattr(remote_client, "RemoteSummaryClient", MockRemoteClient)

    first = client.post(f"/jobs/{job_payload['id']}/cancel")
    assert first.status_code == 200
    assert first.json()["status"] == "cancelled"

    second = client.post(f"/jobs/{job_payload['id']}/cancel")
    assert second.status_code == 200
    assert second.json()["status"] == "cancelled"

    # Remote cancel is never called for an already-cancelled (terminal) job.
    assert remote_cancel_calls == []


def test_jobs_api_cancel_terminal_job_preserves_status(client: TestClient, examples_dir: Path) -> None:
    source_path = examples_dir / "simple_manual.txt"
    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    document_id = ingest_response.json()["document"]["id"]
    job_payload = client.post(f"/documents/{document_id}/summaries/run").json()

    # The locally-run job completes inline with no remote_job_id.
    assert job_payload["status"] == "completed"

    cancel_response = client.post(f"/jobs/{job_payload['id']}/cancel")
    assert cancel_response.status_code == 200
    # Terminal status is preserved (cancel is a no-op for terminal jobs).
    assert cancel_response.json()["status"] == "completed"


def _make_job(session: Session) -> tuple[Document, "Job"]:
    from deepreader.storage.repositories import create_job

    document = Document(
        title="t",
        source_filename="t.txt",
        source_type="text",
        source_hash="test-source-hash",
    )
    session.add(document)
    session.flush()
    job = create_job(session, document_id=document.id, job_type="record_summary", total_steps=0)
    session.flush()
    return document, job


def test_set_job_step_status_skipped_stores_error_code_and_finished_at(db_session: Session) -> None:
    _, job = _make_job(db_session)
    step = create_job_step(
        db_session, job_id=job.id, step_type="record_summary", target_type="record", target_id=1
    )

    set_job_step_status(
        db_session, step, JOB_STATUS_SKIPPED, error_code="job_cancelled", error_message="cancelled"
    )
    db_session.refresh(step)

    assert step.status == JOB_STATUS_SKIPPED
    assert step.error_code == "job_cancelled"
    assert step.error_message == "cancelled"
    assert step.finished_at is not None


def test_refresh_job_progress_counts_skipped_separately(db_session: Session) -> None:
    _, job = _make_job(db_session)
    s1 = create_job_step(db_session, job_id=job.id, step_type="t", target_type="r", target_id=1)
    s2 = create_job_step(db_session, job_id=job.id, step_type="t", target_type="r", target_id=2)
    s3 = create_job_step(db_session, job_id=job.id, step_type="t", target_type="r", target_id=3)
    s4 = create_job_step(db_session, job_id=job.id, step_type="t", target_type="r", target_id=4)

    set_job_step_status(db_session, s1, JOB_STATUS_COMPLETED)
    set_job_step_status(db_session, s2, JOB_STATUS_FAILED, error_code="provider_error")
    set_job_step_status(db_session, s3, JOB_STATUS_SKIPPED, error_code="job_cancelled")
    # s4 stays pending

    refresh_job_progress(db_session, job)
    db_session.refresh(job)

    assert job.total_steps == 4
    assert job.completed_steps == 1
    assert job.failed_steps == 1
    assert job.skipped_steps == 1


def test_set_job_step_status_completed_clears_stale_error_code(db_session: Session) -> None:
    _, job = _make_job(db_session)
    step = create_job_step(db_session, job_id=job.id, step_type="t", target_type="r", target_id=1)

    set_job_step_status(db_session, step, JOB_STATUS_FAILED, error_code="provider_error")
    db_session.refresh(step)
    assert step.error_code == "provider_error"

    # Completed without an explicit error_code must clear the stale value.
    set_job_step_status(db_session, step, JOB_STATUS_COMPLETED)
    db_session.refresh(step)
    assert step.status == JOB_STATUS_COMPLETED
    assert step.error_code is None
    assert step.finished_at is not None


def test_set_job_step_status_pending_running_paused_clear_error_code(db_session: Session) -> None:
    _, job = _make_job(db_session)
    step = create_job_step(db_session, job_id=job.id, step_type="t", target_type="r", target_id=1)

    set_job_step_status(db_session, step, JOB_STATUS_FAILED, error_code="provider_error")
    db_session.refresh(step)
    assert step.error_code == "provider_error"

    for status in (JOB_STATUS_PAUSED, JOB_STATUS_RUNNING, "pending"):
        set_job_step_status(db_session, step, status)
        db_session.refresh(step)
        assert step.error_code is None, f"error_code should be cleared on {status}"
        assert step.finished_at is None, f"finished_at should be cleared on {status}"


def test_jobs_api_output_includes_skipped_steps(client: TestClient, examples_dir: Path) -> None:
    source_path = examples_dir / "simple_manual.txt"
    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    document_id = ingest_response.json()["document"]["id"]
    job_payload = client.post(f"/documents/{document_id}/summaries/run").json()

    response = client.get(f"/jobs/{job_payload['id']}")
    assert response.status_code == 200
    payload = response.json()
    assert "skipped_steps" in payload
    assert payload["skipped_steps"] == 0


def test_jobs_api_step_output_includes_error_code(client: TestClient, examples_dir: Path) -> None:
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
        step = job.steps[0]
        set_job_step_status(
            session, step, JOB_STATUS_SKIPPED, error_code="job_cancelled", error_message="cancelled"
        )
        refresh_job_progress(session, job)
        session.commit()

    steps_response = client.get(f"/jobs/{job_payload['id']}/steps")
    assert steps_response.status_code == 200
    steps = steps_response.json()
    target = [s for s in steps if s["status"] == "skipped"][0]
    assert target["error_code"] == "job_cancelled"
    assert target["error_message"] == "cancelled"
    assert target["finished_at"] is not None

    # Per-job detail also surfaces skipped_steps counter and step error_code.
    detail = client.get(f"/jobs/{job_payload['id']}").json()
    assert detail["skipped_steps"] == 1


def test_set_job_status_rejects_skipped(db_session: Session) -> None:
    _, job = _make_job(db_session)

    with pytest.raises(ValueError, match="Invalid status"):
        set_job_status(db_session, job, JOB_STATUS_SKIPPED)


def test_init_db_migrates_existing_sqlite_jobs_for_skipped_accounting(tmp_path: Path) -> None:
    engine = build_engine(f"sqlite:///{tmp_path / 'legacy_skipped.sqlite3'}")
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
                    finished_at DATETIME,
                    remote_job_id VARCHAR(255),
                    remote_progress_json JSON
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE job_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    step_type VARCHAR(100) NOT NULL,
                    target_type VARCHAR(100) NOT NULL,
                    target_id INTEGER NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    attempt_count INTEGER NOT NULL,
                    error_message TEXT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    finished_at DATETIME
                )
                """
            )
        )

    init_db(engine)

    job_columns = {column["name"] for column in inspect(engine).get_columns("jobs")}
    assert "skipped_steps" in job_columns
    step_columns = {column["name"] for column in inspect(engine).get_columns("job_steps")}
    assert "error_code" in step_columns
    engine.dispose()
