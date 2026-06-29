"""PDF document ingestion helpers."""

from __future__ import annotations

import io
import logging

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore

from deepreader.records.chunker import split_paragraphs
from deepreader.records.metadata import ParsedDocument, SourceRecord

LOGGER = logging.getLogger(__name__)


def parse_pdf_document(file_input: bytes | str, title: str | None = None) -> ParsedDocument:
    """Parse PDF content into ordered paragraph records."""

    if PdfReader is None:
        raise RuntimeError("pypdf is not installed. PDF ingestion is disabled.")

    records: list[SourceRecord] = []
    inferred_title = title

    try:
        if isinstance(file_input, bytes):
            reader = PdfReader(io.BytesIO(file_input))
        else:
            reader = PdfReader(file_input)
        
        if inferred_title is None and reader.metadata and reader.metadata.title:
            inferred_title = reader.metadata.title

        for page_index, page in enumerate(reader.pages):
            page_number = page_index + 1
            text = page.extract_text()
            
            if not text or not text.strip():
                # Preserve an empty/skipped page marker if no text
                records.append(
                    SourceRecord(
                        source_text="[Empty or unreadable page]",
                        record_type="paragraph",
                        page_number=page_number,
                        metadata={"status": "empty_or_skipped"},
                    )
                )
                continue

            paragraphs = split_paragraphs(text)
            for paragraph in paragraphs:
                records.append(
                    SourceRecord(
                        source_text=paragraph,
                        record_type="paragraph",
                        page_number=page_number,
                    )
                )
                
    except Exception as exc:
        LOGGER.error("Failed to parse PDF document: %s", exc)
        raise

    return ParsedDocument(title=inferred_title, records=records)
