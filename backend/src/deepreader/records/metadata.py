"""Record metadata structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceRecord:
    source_text: str
    record_type: str = "paragraph"
    chapter_index: int | None = None
    section_title: str | None = None
    page_number: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    title: str | None
    records: list[SourceRecord]


def build_record_metadata(record: SourceRecord) -> dict[str, Any]:
    """Build inspectable metadata persisted with a record."""

    metadata = dict(record.metadata)
    metadata["chapter_index"] = record.chapter_index
    metadata["page_number"] = record.page_number
    metadata["section_title"] = record.section_title
    return metadata
