from pathlib import Path

from fastapi.testclient import TestClient


def test_answers_are_persisted_with_citations(client: TestClient, examples_dir: Path) -> None:
    source_path = examples_dir / "troubleshooting_log.txt"
    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    document_id = ingest_response.json()["document"]["id"]

    ask_response = client.post(
        "/qa/ask",
        json={"question": "Which incident involved bearing wear?", "document_id": document_id, "limit": 5},
    )
    answer_id = ask_response.json()["answer_id"]

    list_response = client.get("/answers")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == answer_id

    detail_response = client.get(f"/answers/{answer_id}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["id"] == answer_id
    assert detail["document_id"] == document_id
    assert detail["citations"]
    assert detail["evidence"]
    assert all(citation["record_id"] for citation in detail["citations"])


def test_answers_api_returns_404_for_missing_answer(client: TestClient) -> None:
    response = client.get("/answers/999")

    assert response.status_code == 404
