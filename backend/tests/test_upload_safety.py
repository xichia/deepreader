from pathlib import Path

from fastapi.testclient import TestClient


def test_text_upload_rejects_path_traversal_filename(
    client: TestClient,
    examples_dir: Path,
) -> None:
    source_path = examples_dir / "simple_manual.txt"

    response = client.post(
        "/documents/ingest/text",
        files={"file": ("../../evil.txt", source_path.read_bytes(), "text/plain")},
    )

    assert response.status_code == 400


def test_text_upload_rejects_suspicious_filename(client: TestClient) -> None:
    response = client.post(
        "/documents/ingest/text",
        files={"file": ("manual;rm.txt", b"safe text body", "text/plain")},
    )

    assert response.status_code == 400


def test_epub_upload_rejects_text_extension(client: TestClient) -> None:
    response = client.post(
        "/documents/ingest/epub",
        files={"file": ("manual.txt", b"not an epub", "text/plain")},
    )

    assert response.status_code == 400


def test_text_upload_rejects_wrong_extension(client: TestClient) -> None:
    response = client.post(
        "/documents/ingest/text",
        files={"file": ("manual.pdf", b"not a text upload", "application/pdf")},
    )

    assert response.status_code == 400


def test_upload_size_limit_is_enforced(small_upload_client: TestClient) -> None:
    response = small_upload_client.post(
        "/documents/ingest/text",
        files={"file": ("manual.txt", b"x" * 21, "text/plain")},
    )

    assert response.status_code == 413
