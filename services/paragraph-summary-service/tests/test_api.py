import pytest
from fastapi.testclient import TestClient
from app.main import app
import time

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_submit_and_check_job():
    payload = {
        "document_id": "test_doc",
        "records": [
            {"record_id": "r1", "text": "Hello world", "source_hash": "hash1"}
        ]
    }
    
    response = client.post("/paragraph-summaries", json=payload)
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    
    # Wait for background task to complete
    max_wait = 50
    while max_wait > 0:
        res = client.get(f"/jobs/{job_id}")
        assert res.status_code == 200
        if res.json()["status"] in ("completed", "failed"):
            break
        time.sleep(0.1)
        max_wait -= 1
        
    status_res = client.get(f"/jobs/{job_id}")
    assert status_res.json()["status"] == "completed"
    assert status_res.json()["completed_records"] == 1
    
    artifact_res = client.get(f"/jobs/{job_id}/artifact")
    assert artifact_res.status_code == 200
    artifact = artifact_res.json()
    assert len(artifact) == 1
    assert artifact[0]["record_id"] == "r1"
    assert artifact[0]["status"] == "completed"


def test_submit_rejects_duplicate_record_ids():
    response = client.post(
        "/paragraph-summaries",
        json={
            "document_id": "test_doc",
            "records": [
                {"record_id": "r1", "text": "First", "source_hash": "hash1"},
                {"record_id": "r1", "text": "Duplicate", "source_hash": "hash2"},
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Duplicate record_id values are not allowed"
