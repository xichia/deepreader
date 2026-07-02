from pathlib import Path

from fastapi.testclient import TestClient


def test_search_api_returns_inspectable_bm25_results(client: TestClient, examples_dir: Path) -> None:
    source_path = examples_dir / "troubleshooting_log.txt"
    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    document_id = ingest_response.json()["document"]["id"]

    response = client.post(
        "/search",
        json={"query": "bearing wear", "document_id": document_id, "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "bearing wear"
    assert payload["results"]
    assert payload["results"][0]["retrieval_method"] == "bm25_source_text"
    assert payload["results"][0]["component_scores"] == {
        "bm25_source_text": payload["results"][0]["score"]
    }
    assert payload["results"][0]["summary"] is None
    assert "bearing wear" in payload["results"][0]["source_text"].lower()
    assert payload["results"][0]["stable_id"].startswith("doc_")
    assert payload["results"][0]["metadata"]["section_title"]


def test_search_api_can_search_across_documents(client: TestClient, examples_dir: Path) -> None:
    for filename in ("simple_manual.txt", "troubleshooting_log.txt"):
        source_path = examples_dir / filename
        response = client.post(
            "/documents/ingest/text",
            files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
        )
        assert response.status_code == 201

    expectations = {
        "low flow": lambda text: "low-flow" in text or "low flow" in text,
        "bearing wear": lambda text: "bearing wear" in text,
        "heat exchanger fouling": lambda text: "heat exchanger fouling" in text,
        "filter replacement": lambda text: "filter" in text and ("replace" in text or "replaced" in text),
    }

    for query, expectation in expectations.items():
        response = client.post("/search", json={"query": query, "limit": 3})
        assert response.status_code == 200
        results = response.json()["results"]
        assert results
        assert expectation(results[0]["source_text"].lower())
