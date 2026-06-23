from pathlib import Path

from fastapi.testclient import TestClient


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
    assert jobs[0]["steps"] == []

    detail_response = client.get(f"/jobs/{job['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["completed_steps"] == detail["total_steps"]
    assert detail["steps"]


def test_jobs_api_returns_404_for_missing_job(client: TestClient) -> None:
    response = client.get("/jobs/999")

    assert response.status_code == 404
