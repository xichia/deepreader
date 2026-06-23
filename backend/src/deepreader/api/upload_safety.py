"""Upload validation helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,254}$")


def get_max_upload_bytes() -> int:
    raw_value = os.getenv("DEEPREADER_MAX_UPLOAD_BYTES")
    if raw_value is None:
        return DEFAULT_MAX_UPLOAD_BYTES
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("DEEPREADER_MAX_UPLOAD_BYTES must be an integer") from exc
    if value <= 0:
        raise RuntimeError("DEEPREADER_MAX_UPLOAD_BYTES must be positive")
    return value


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


async def read_upload_bytes(upload: UploadFile, max_bytes: int) -> bytes:
    data = await upload.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail="Upload exceeds configured size limit.",
        )
    return data
