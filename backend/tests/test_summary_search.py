from pathlib import Path

from fastapi.testclient import TestClient


def test_summary_search_returns_summary_results_and_preserves_source_search(
    client: TestClient,
    examples_dir: Path,
) -> None:
    source_path = examples_dir / "troubleshooting_log.txt"
    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    document_id = ingest_response.json()["document"]["id"]
    client.post(f"/documents/{document_id}/summaries/run")

    source_response = client.post(
        "/search",
        json={"query": "bearing wear", "document_id": document_id, "limit": 3},
    )
    assert source_response.status_code == 200
    source_results = source_response.json()["results"]
    assert source_results
    assert source_results[0]["retrieval_method"] == "bm25_source_text"
    assert source_results[0]["summary"] is None

    summary_response = client.post(
        "/search",
        json={
            "query": "bearing wear",
            "document_id": document_id,
            "limit": 5,
            "search_source_text": False,
            "search_summaries": True,
        },
    )
    assert summary_response.status_code == 200
    summary_results = summary_response.json()["results"]
    assert summary_results
    assert summary_results[0]["retrieval_method"] == "bm25_summary_text"
    assert "bearing wear" in summary_results[0]["summary"].lower()
    assert "bearing wear" in summary_results[0]["source_text"].lower()
    assert summary_results[0]["metadata"]["summariser_name"] == "local_extractive_v1"


def test_search_rejects_empty_search_targets(client: TestClient) -> None:
    response = client.post(
        "/search",
        json={"query": "low flow", "search_source_text": False, "search_summaries": False},
    )

    assert response.status_code == 400
