import io
import os
import tempfile
from pathlib import Path
import pytest
from ebooklib import epub

from deepreader.ingest.epub_parser import parse_epub_document
from deepreader.ingest.pdf_parser import parse_pdf_document
from deepreader.records.chunker import split_paragraphs
from deepreader.records.ids import hash_bytes, hash_text, stable_record_id


def test_epub_sentences_and_paragraphs_granularity() -> None:
    # An EPUB paragraph containing three sentences becomes exactly one record.
    # Two EPUB <p> elements become two records.
    # EPUB nav/toc boilerplate is not emitted.
    book = epub.EpubBook()
    book.set_identifier("test-granularity-epub")
    book.set_title("Granularity Test")
    book.set_language("en")

    # Front-matter / TOC document
    toc_html = epub.EpubHtml(title="TOC", file_name="toc.xhtml", lang="en")
    toc_html.content = """
    <html><body>
      <h1>Table of Contents</h1>
      <p>Begin Reading</p>
      <p>Chapter 1</p>
    </body></html>
    """

    chapter_one = epub.EpubHtml(title="Chapter 1", file_name="chapter_1.xhtml", lang="en")
    chapter_one.content = """
    <html><body>
      <h1>Chapter 1</h1>
      <p>First sentence. Second sentence. Third sentence is here.</p>
      <p>This is the second paragraph.</p>
    </body></html>
    """

    book.add_item(toc_html)
    book.add_item(chapter_one)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", toc_html, chapter_one]
    book.toc = (toc_html, chapter_one)

    with tempfile.TemporaryDirectory() as tmp_dir:
        epub_path = Path(tmp_dir) / "test.epub"
        epub.write_epub(str(epub_path), book)
        data = epub_path.read_bytes()

    parsed = parse_epub_document(data)

    assert parsed.title == "Granularity Test"
    records = parsed.records
    
    texts = [r.source_text for r in records]
    
    # Boilerplate check
    assert "Table of Contents" not in texts
    assert "Begin Reading" not in texts
    
    # Granularity check
    assert len(records) == 3
    assert records[0].source_text == "Chapter 1"
    assert records[1].source_text == "First sentence. Second sentence. Third sentence is here."
    assert records[2].source_text == "This is the second paragraph."


def test_pdf_reflow_and_paragraph_boundaries() -> None:
    # A PDF-style text sample with line-wrapped paragraph text is reflowed into one paragraph record.
    # A PDF-style text sample with blank-line-separated paragraphs becomes multiple paragraph records.
    text_sample = (
        "This is a line-wrapped\n"
        "paragraph of text that belongs\n"
        "to a single block.\n"
        "\n"
        "This is the second paragraph\n"
        "separated by blank lines."
    )

    paragraphs = split_paragraphs(text_sample)

    assert len(paragraphs) == 2
    assert paragraphs[0] == "This is a line-wrapped paragraph of text that belongs to a single block."
    assert paragraphs[1] == "This is the second paragraph separated by blank lines."


def test_stable_ids_and_hashes_are_deterministic() -> None:
    source_bytes = b"pdf-source-bytes-demo"
    source_hash = hash_bytes(source_bytes)
    
    id1 = stable_record_id(source_hash, 0, page_number=1)
    id2 = stable_record_id(source_hash, 0, page_number=1)
    assert id1 == id2
    
    h1 = hash_text("some text block")
    h2 = hash_text("some text block")
    assert h1 == h2


def test_epub_nested_readable_elements_deduplicated() -> None:
    # EPUB nested readable elements: e.g. <p> inside <li>
    # Should only emit the top-level block and avoid duplicate inner content records
    html = """
    <html><body>
      <li>
        <p>List item paragraph text block.</p>
      </li>
    </body></html>
    """
    from deepreader.ingest.epub_parser import _extract_records_from_html
    records = _extract_records_from_html(html, chapter_index=0)
    
    # Nested <p> element is skipped. Only 1 record from <li> is emitted.
    assert len(records) == 1
    assert records[0].source_text == "List item paragraph text block."
