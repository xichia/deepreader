import logging

from fastapi.testclient import TestClient


def test_ingest_logs_do_not_include_uploaded_source_text(client: TestClient, caplog) -> None:
    source_text = b"UNIQUE_SECRETISH_MANUAL_BODY should never appear in logs."

    with caplog.at_level(logging.INFO):
        response = client.post(
            "/documents/ingest/text",
            files={"file": ("manual.txt", source_text, "text/plain")},
        )

    assert response.status_code == 201
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "manual.txt" in logged
    assert "UNIQUE_SECRETISH_MANUAL_BODY" not in logged
