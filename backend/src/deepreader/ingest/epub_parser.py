"""EPUB ingestion helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from deepreader.records.metadata import ParsedDocument, SourceRecord

_READABLE_TAGS = ("h1", "h2", "h3", "h4", "p", "li")


def parse_epub_document(data: bytes) -> ParsedDocument:
    """Extract ordered readable paragraph records from EPUB bytes."""

    with tempfile.NamedTemporaryFile(suffix=".epub", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        book = epub.read_epub(tmp.name)

    title = _first_metadata_value(book, "DC", "title")
    records: list[SourceRecord] = []

    for chapter_index, item in enumerate(_ordered_document_items(book)):
        html = item.get_content().decode("utf-8", errors="replace")
        chapter_records = _extract_records_from_html(html, chapter_index)
        records.extend(chapter_records)

    return ParsedDocument(title=title, records=records)


def _first_metadata_value(book: epub.EpubBook, namespace: str, name: str) -> str | None:
    values = book.get_metadata(namespace, name)
    if not values:
        return None
    value = values[0][0]
    return value.strip() if isinstance(value, str) and value.strip() else None


def _ordered_document_items(book: epub.EpubBook) -> list[ebooklib.epub.EpubHtml]:
    by_id = {
        item.get_id(): item
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
        if not _is_navigation_item(item)
    }
    ordered: list[ebooklib.epub.EpubHtml] = []

    for spine_entry in book.spine:
        item_id = spine_entry[0] if isinstance(spine_entry, tuple) else spine_entry
        item = by_id.get(item_id)
        if item is not None:
            ordered.append(item)

    if ordered:
        return ordered
    return [
        item
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT)
        if not _is_navigation_item(item)
    ]


def _is_navigation_item(item: ebooklib.epub.EpubHtml) -> bool:
    item_id = (item.get_id() or "").lower()
    item_name = (item.get_name() or "").lower()

    nav_keywords = {"nav", "toc", "ncx", "landmark", "cover", "titlepage", "title_page", "title-page"}
    if any(kw in item_id for kw in nav_keywords):
        return True
    if any(kw in item_name for kw in nav_keywords):
        return True
    return False


def _extract_records_from_html(html: str, chapter_index: int) -> list[SourceRecord]:
    soup = BeautifulSoup(html, "html.parser")
    records: list[SourceRecord] = []
    current_section: str | None = None

    for element in soup.find_all(_READABLE_TAGS):
        # Prevent nested tags double extraction
        has_readable_parent = False
        parent = element.parent
        while parent is not None:
            if parent.name in _READABLE_TAGS:
                has_readable_parent = True
                break
            parent = parent.parent
        if has_readable_parent:
            continue

        text = element.get_text(" ", strip=True)
        if not text:
            continue

        # Skip standard front-matter and navigation boilerplate records
        if text.lower() in {
            "begin reading",
            "table of contents",
            "about the author",
            "copyright page",
            "cover",
            "title page",
            "landmarks",
            "navigation",
        }:
            continue

        if element.name in {"h1", "h2", "h3", "h4"}:
            current_section = text

        records.append(
            SourceRecord(
                source_text=text,
                record_type="paragraph",
                chapter_index=chapter_index,
                section_title=current_section,
            )
        )

    return records
