from pathlib import Path

from ebooklib import epub
from sqlalchemy.orm import Session

from deepreader.ingest.epub_parser import parse_epub_document
from deepreader.storage.repositories import ingest_parsed_document, list_document_records


def _write_synthetic_epub(path: Path) -> bytes:
    book = epub.EpubBook()
    book.set_identifier("deepreader-test-epub")
    book.set_title("Synthetic Pump EPUB")
    book.set_language("en")

    chapter_one = epub.EpubHtml(title="Low Flow", file_name="chapter_1.xhtml", lang="en")
    chapter_one.content = """
    <html><body>
      <h1>Low Flow</h1>
      <p>Alarm A12 low flow can be caused by a blocked filter.</p>
      <p>Inspect the outlet valve before replacing components.</p>
    </body></html>
    """

    chapter_two = epub.EpubHtml(title="Bearing Wear", file_name="chapter_2.xhtml", lang="en")
    chapter_two.content = """
    <html><body>
      <h1>Bearing Wear</h1>
      <p>High motor current with vibration may indicate bearing wear.</p>
    </body></html>
    """

    book.add_item(chapter_one)
    book.add_item(chapter_two)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter_one, chapter_two]
    book.toc = (chapter_one, chapter_two)

    epub.write_epub(str(path), book)
    return path.read_bytes()


def test_epub_ingest_extracts_ordered_chapter_records(db_session: Session, tmp_path: Path) -> None:
    data = _write_synthetic_epub(tmp_path / "pump.epub")
    parsed = parse_epub_document(data)

    document = ingest_parsed_document(
        db_session,
        parsed_document=parsed,
        source_filename="pump.epub",
        source_type="epub",
        source_bytes=data,
    )
    records = list_document_records(db_session, document.id)

    assert document.title == "Synthetic Pump EPUB"
    assert [record.chapter_index for record in records] == [0, 0, 0, 1, 1]
    assert records[0].source_text == "Low Flow"
    assert "blocked filter" in records[1].source_text
    assert records[-1].metadata_json["section_title"] == "Bearing Wear"
