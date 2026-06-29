"""Upload validation helpers."""

from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,254}$")
UPLOAD_CHUNK_BYTES = 1024 * 1024


def validate_upload_filename(filename: str | None, allowed_extensions: set[str]) -> str:
    if not filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload filename is required.")

    if "\x00" in filename or "/" in filename or "\\" in filename or ":" in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsafe upload filename.")

    if filename in {".", ".."} or ".." in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsafe upload filename.")

    if Path(filename).name != filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsafe upload filename.")

    if not SAFE_FILENAME_RE.match(filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Suspicious upload filename.")

    extension = Path(filename).suffix.lower()
    if extension not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported upload type. Allowed extensions: {allowed}.",
        )

    return filename


async def stream_upload_to_temp_file_and_hash(upload: UploadFile) -> tuple[str, str]:
    """Stream an upload to disk while calculating its SHA-256 digest."""

    sha256 = hashlib.sha256()
    temp_file = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    temp_path = temp_file.name
    try:
        with temp_file:
            while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                temp_file.write(chunk)
                sha256.update(chunk)
    except Exception:
        Path(temp_path).unlink(missing_ok=True)
        raise
    return temp_path, sha256.hexdigest()
