from pathlib import Path

from fastapi.testclient import TestClient


def test_summary_api_runs_job_and_returns_summaries(client: TestClient, examples_dir: Path) -> None:
    source_path = examples_dir / "simple_manual.txt"
    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    document_id = ingest_response.json()["document"]["id"]

    run_response = client.post(f"/documents/{document_id}/summaries/run")
    assert run_response.status_code == 200
    job = run_response.json()
    assert job["status"] == "completed"
    assert job["total_steps"] == job["completed_steps"]
    assert job["steps"]

    summaries_response = client.get(f"/documents/{document_id}/summaries")
    assert summaries_response.status_code == 200
    summaries = summaries_response.json()
    assert len(summaries) == job["total_steps"]
    assert summaries[0]["record_id"]
    assert summaries[0]["stable_id"].startswith("doc_")
    assert summaries[0]["summariser_name"] == "local_extractive_v1"


def test_summary_api_returns_404_for_missing_document(client: TestClient) -> None:
    response = client.post("/documents/999/summaries/run")

    assert response.status_code == 404
