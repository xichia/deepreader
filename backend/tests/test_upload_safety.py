import asyncio
import hashlib
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from deepreader.api import routes_documents
from deepreader.api.upload_safety import (
    UPLOAD_CHUNK_BYTES,
    stream_upload_to_temp_file_and_hash,
)


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


def test_stream_upload_to_temp_file_hashes_in_chunks() -> None:
    payload = b"a" * (UPLOAD_CHUNK_BYTES * 2 + 17)

    class RecordingUpload:
        def __init__(self) -> None:
            self.offset = 0
            self.read_sizes: list[int] = []

        async def read(self, size: int) -> bytes:
            self.read_sizes.append(size)
            chunk = payload[self.offset : self.offset + size]
            self.offset += len(chunk)
            return chunk

    upload = RecordingUpload()
    temp_path, source_hash = asyncio.run(stream_upload_to_temp_file_and_hash(upload))  # type: ignore[arg-type]

    try:
        assert Path(temp_path).read_bytes() == payload
        assert source_hash == hashlib.sha256(payload).hexdigest()
        assert upload.read_sizes == [UPLOAD_CHUNK_BYTES] * 4
    finally:
        Path(temp_path).unlink(missing_ok=True)


def test_large_pdf_upload_streams_without_app_size_cap(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.add_attachment("padding.bin", b"x" * (10 * 1024 * 1024 + 1))
    pdf_buffer = io.BytesIO()
    writer.write(pdf_buffer)
    pdf_bytes = pdf_buffer.getvalue()
    captured_temp_path: Path | None = None
    stream_upload = routes_documents.stream_upload_to_temp_file_and_hash

    async def capture_temp_path(upload: object) -> tuple[str, str]:
        nonlocal captured_temp_path
        temp_path, source_hash = await stream_upload(upload)  # type: ignore[arg-type]
        captured_temp_path = Path(temp_path)
        return temp_path, source_hash

    monkeypatch.setattr(routes_documents, "stream_upload_to_temp_file_and_hash", capture_temp_path)

    response = client.post(
        "/documents/ingest/pdf",
        files={"file": ("large.pdf", pdf_bytes, "application/pdf")},
    )

    assert len(pdf_bytes) > 10 * 1024 * 1024
    assert response.status_code == 201
    assert response.json()["document"]["source_hash"] == hashlib.sha256(pdf_bytes).hexdigest()
    assert captured_temp_path is not None
    assert not captured_temp_path.exists()
