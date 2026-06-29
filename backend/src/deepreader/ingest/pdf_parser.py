"""PDF document ingestion helpers."""

from __future__ import annotations

import io
import logging
import re
from statistics import median
from typing import Any

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None  # type: ignore

from deepreader.records.metadata import ParsedDocument, SourceRecord

LOGGER = logging.getLogger(__name__)

_BLANK_LINE_RE = re.compile(r"\n\s*\n+")
_LIST_ITEM_RE = re.compile(r"^(?:[-*•▪◦]|\d+[.)]|[A-Za-z][.)])\s+")
_NUMBERED_HEADING_RE = re.compile(r"^(?:chapter|part|section|appendix)\b", re.IGNORECASE)
_SECTION_NUMBER_RE = re.compile(r"^\d+(?:\.\d+)*\s+\S")
_TOC_HEADING_RE = re.compile(r"^(?:table\s+of\s+)?contents$", re.IGNORECASE)
_TOC_ENTRY_RE = re.compile(
    r"^(?:chapter|unit|part|section|appendix|\d+(?:\.\d+)*)?\s*"
    r".+?(?:\.{2,}|\s{3,})\s*\d+\s*$",
    re.IGNORECASE,
)
_TOC_CHAPTER_ENTRY_RE = re.compile(
    r"^(?:chapter|unit|part|section|appendix)\s+.+\s+\d+\s*$",
    re.IGNORECASE,
)
_BOILERPLATE_RE = re.compile(
    r"^(?:access\s+for\s+free\s+at\s+openstax\.org|openstax(?:\.org)?)$",
    re.IGNORECASE,
)


def parse_pdf_document(file_input: bytes | str, title: str | None = None) -> ParsedDocument:
    """Parse PDF layout text into ordered paragraph records."""

    if PdfReader is None:
        raise RuntimeError("pypdf is not installed. PDF ingestion is disabled.")

    reader = PdfReader(io.BytesIO(file_input)) if isinstance(file_input, bytes) else PdfReader(file_input)
    inferred_title = title
    if inferred_title is None and reader.metadata and reader.metadata.title:
        inferred_title = reader.metadata.title

    records: list[SourceRecord] = []
    for page_index, page in enumerate(reader.pages):
        page_number = page_index + 1
        try:
            page_text = _extract_layout_text(page)
        except Exception as exc:
            LOGGER.warning(
                "Skipping unreadable PDF page page=%s error_type=%s",
                page_number,
                type(exc).__name__,
            )
            continue

        if not page_text.strip():
            LOGGER.info("Skipping empty PDF page page=%s", page_number)
            continue
        if _is_toc_text(page_text):
            LOGGER.info("Skipping table-of-contents PDF page page=%s", page_number)
            continue

        paragraphs = split_pdf_paragraphs(page_text)
        for paragraph_index, paragraph in enumerate(paragraphs, start=1):
            records.append(
                SourceRecord(
                    source_text=paragraph,
                    record_type="paragraph",
                    page_number=page_number,
                    metadata={"paragraph_index": paragraph_index},
                )
            )

    return ParsedDocument(title=inferred_title, records=records)


def _extract_layout_text(page: Any) -> str:
    """Prefer pypdf layout extraction, with compatibility fallback for older releases."""

    try:
        text = page.extract_text(extraction_mode="layout")
    except Exception:
        text = page.extract_text()
    return text if isinstance(text, str) else ""


def split_pdf_paragraphs(text: str) -> list[str]:
    """Split layout-preserving PDF text into blocks and reflow wrapped lines."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[str] = []
    for raw_block in _BLANK_LINE_RE.split(normalized):
        lines = [line.expandtabs(4).rstrip() for line in raw_block.split("\n")]
        lines = [line for line in lines if line.strip() and not _is_boilerplate_line(line)]
        if not lines or _is_toc_text("\n".join(lines)):
            continue
        paragraphs.extend(_split_layout_block(lines))
    return [paragraph for paragraph in paragraphs if paragraph]


def _split_layout_block(lines: list[str]) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    current_indents: list[int] = []
    typical_line_length = median([len(line.strip()) for line in lines])

    def flush() -> None:
        if current:
            paragraph = _reflow_lines(current)
            if paragraph:
                paragraphs.append(paragraph)
            current.clear()
            current_indents.clear()

    for raw_line in lines:
        text = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip(" "))

        if _looks_like_heading(text):
            flush()
            paragraphs.append(text)
            continue

        is_list_item = bool(_LIST_ITEM_RE.match(text))
        current_is_list_item = bool(current and _LIST_ITEM_RE.match(current[0].strip()))
        if current and is_list_item:
            flush()
        elif current and not current_is_list_item:
            minimum_indent = min(current_indents)
            previous = current[-1].rstrip()
            accumulated_chars = sum(len(line) for line in current)
            clear_indent_transition = (
                indent >= minimum_indent + 3
                and previous.endswith((".", "!", "?", ":"))
            )
            short_terminal_line = (
                accumulated_chars >= 80
                and len(previous.strip()) <= typical_line_length * 0.72
                and previous.endswith((".", "!", "?"))
                and text[:1].isupper()
            )
            long_block_boundary = (
                accumulated_chars >= 1200
                and previous.endswith((".", "!", "?"))
                and text[:1].isupper()
            )
            if clear_indent_transition or short_terminal_line or long_block_boundary:
                flush()

        current.append(text)
        current_indents.append(indent)

    flush()
    return paragraphs


def _reflow_lines(lines: list[str]) -> str:
    reflowed = ""
    for line in lines:
        cleaned = re.sub(r"\s+", " ", line).strip()
        if not cleaned:
            continue
        if reflowed.endswith("-") and cleaned[0].islower():
            reflowed = f"{reflowed[:-1]}{cleaned}"
        elif reflowed:
            reflowed = f"{reflowed} {cleaned}"
        else:
            reflowed = cleaned
    return reflowed.strip()


def _looks_like_heading(text: str) -> bool:
    if not text or len(text) > 100 or len(text.split()) > 14:
        return False
    if _NUMBERED_HEADING_RE.match(text) or _SECTION_NUMBER_RE.match(text):
        return True
    letters = [character for character in text if character.isalpha()]
    return bool(letters) and all(character.isupper() for character in letters)


def _is_boilerplate_line(line: str) -> bool:
    stripped = line.strip()
    return bool(_BOILERPLATE_RE.match(stripped) or re.fullmatch(r"\d{1,4}", stripped))


def _is_toc_text(text: str) -> bool:
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False

    cleaned = [line.strip() for line in lines if not _is_boilerplate_line(line)]
    has_heading = any(_TOC_HEADING_RE.match(line) for line in cleaned[:8])
    toc_entries = sum(
        1
        for line in lines
        if _TOC_ENTRY_RE.match(line.strip()) or _TOC_CHAPTER_ENTRY_RE.match(line.strip())
    )
    return (has_heading and toc_entries >= 2) or (
        toc_entries >= 5 and toc_entries >= max(1, len(cleaned) // 2)
    )
