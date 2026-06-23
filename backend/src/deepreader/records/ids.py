"""Stable hashes and record identifiers."""

from __future__ import annotations

import hashlib


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    return hash_bytes(text.encode("utf-8"))


def document_key(source_hash: str) -> str:
    """Create a deterministic document key from a content hash."""

    return f"doc_{source_hash[:12]}"


def stable_record_id(
    document_source_hash: str,
    order_index: int,
    *,
    chapter_index: int | None = None,
    page_number: int | None = None,
) -> str:
    """Create a deterministic stable ID for a source record."""

    base = document_key(document_source_hash)

    if chapter_index is not None:
        return f"{base}/ch_{chapter_index + 1:03d}/p_{order_index + 1:04d}"
    if page_number is not None:
        return f"{base}/page_{page_number:04d}/para_{order_index + 1:04d}"
    return f"{base}/para_{order_index + 1:04d}"
