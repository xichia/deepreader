from pathlib import Path

from fastapi.testclient import TestClient


def test_qa_api_returns_answer_citations_and_evidence(client: TestClient, examples_dir: Path) -> None:
    source_path = examples_dir / "simple_manual.txt"
    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    document_id = ingest_response.json()["document"]["id"]
    client.post(f"/documents/{document_id}/summaries/run")

    response = client.post(
        "/qa/ask",
        json={
            "question": "What causes low flow?",
            "document_id": document_id,
            "limit": 8,
            "use_source_text": True,
            "use_summaries": True,
            "use_local_vector": True,
            "use_fusion": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer_id"]
    assert payload["question"] == "What causes low flow?"
    assert payload["answer"]
    assert payload["citations"]
    assert payload["evidence"]
    assert payload["retrieval_settings"]["use_local_vector"] is True
    assert all(citation["stable_id"] for citation in payload["citations"])
    assert all("quoted_text" in citation for citation in payload["citations"])

    used_record_ids = {evidence["record_id"] for evidence in payload["used_evidence"]}
    unused_record_ids = {evidence["record_id"] for evidence in payload["unused_evidence"]}
    all_record_ids = {evidence["record_id"] for evidence in payload["evidence"]}
    assert used_record_ids
    assert used_record_ids.isdisjoint(unused_record_ids)
    assert used_record_ids | unused_record_ids == all_record_ids

    for evidence in payload["evidence"]:
        assert evidence["source_text"]
        assert evidence["retrieval_method"] == "fused"
        assert evidence["component_scores"]
        assert all(isinstance(score, float) for score in evidence["component_scores"].values())

    for evidence in payload["used_evidence"] + payload["unused_evidence"]:
        assert evidence["retrieval_method"]
        assert isinstance(evidence["component_scores"], dict)


def test_qa_api_rejects_disabled_retrieval_targets(client: TestClient) -> None:
    response = client.post(
        "/qa/ask",
        json={"question": "What causes low flow?", "use_source_text": False, "use_summaries": False},
    )

    assert response.status_code == 400
