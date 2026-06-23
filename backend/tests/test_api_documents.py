from pathlib import Path

from fastapi.testclient import TestClient


def test_document_api_ingests_lists_and_returns_records(client: TestClient, examples_dir: Path) -> None:
    source_path = examples_dir / "simple_manual.txt"

    ingest_response = client.post(
        "/documents/ingest/text",
        files={"file": (source_path.name, source_path.read_bytes(), "text/plain")},
    )
    assert ingest_response.status_code == 201
    document = ingest_response.json()["document"]
    assert document["title"] == "Cooling Pump Maintenance Manual"
    assert document["record_count"] > 15

    list_response = client.get("/documents")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == document["id"]

    detail_response = client.get(f"/documents/{document['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["record_count"] == document["record_count"]

    records_response = client.get(f"/documents/{document['id']}/records")
    assert records_response.status_code == 200
    records = records_response.json()
    assert records[0]["order_index"] == 0
    assert records[0]["metadata"]["section_title"] == "Cooling Pump Maintenance Manual"
    assert any("Alarm A18 indicates high motor current" in record["source_text"] for record in records)
