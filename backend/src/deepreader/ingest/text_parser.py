"""Plain text ingestion helpers."""

from __future__ import annotations

import re

from deepreader.records.chunker import split_paragraphs
from deepreader.records.metadata import ParsedDocument, SourceRecord

_MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$")


def extract_markdown_heading(paragraph: str) -> str | None:
    """Return a clean heading title when a paragraph is a Markdown heading."""

    match = _MARKDOWN_HEADING_RE.match(paragraph)
    if not match:
        return None
    return match.group(2).strip()


def parse_text_document(text: str, title: str | None = None) -> ParsedDocument:
    """Parse UTF-8 text content into ordered paragraph records."""

    paragraphs = split_paragraphs(text)
    inferred_title = title
    current_section: str | None = None
    records: list[SourceRecord] = []

    for paragraph in paragraphs:
        heading = extract_markdown_heading(paragraph)
        if heading:
            current_section = heading
            if inferred_title is None and paragraph.lstrip().startswith("# "):
                inferred_title = heading

        records.append(
            SourceRecord(
                source_text=paragraph,
                record_type="paragraph",
                section_title=current_section,
            )
        )

    return ParsedDocument(title=inferred_title, records=records)
