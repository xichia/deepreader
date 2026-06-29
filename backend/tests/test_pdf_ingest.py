from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

from pypdf import PdfWriter

import deepreader.ingest.pdf_parser as pdf_parser_module
from deepreader.ingest.pdf_parser import parse_pdf_document
from deepreader.records.ids import hash_bytes, hash_text, stable_record_id


class FakePage:
    def __init__(self, text: str | None) -> None:
        self.text = text
        self.extraction_modes: list[str | None] = []

    def extract_text(self, *, extraction_mode: str | None = None) -> str | None:
        self.extraction_modes.append(extraction_mode)
        return self.text


def parse_fake_pages(monkeypatch, *page_texts: str | None):
    pages = [FakePage(text) for text in page_texts]
    reader = SimpleNamespace(pages=pages, metadata=None)
    monkeypatch.setattr(pdf_parser_module, "PdfReader", lambda _input: reader)
    return parse_pdf_document(b"deterministic-pdf", title="fixture.pdf"), pages


def build_text_pdf(text_commands: list[str]) -> bytes:
    """Build a tiny one-page Helvetica PDF without an extra test dependency."""

    stream = "\n".join(["BT", "/F1 12 Tf", "72 720 Td", *text_commands, "ET"]).encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return bytes(pdf)


def test_empty_pdf_pages_are_not_emitted_as_records() -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    pdf_bytes = io.BytesIO()
    writer.write(pdf_bytes)

    document = parse_pdf_document(pdf_bytes.getvalue(), title="empty.pdf")

    assert document.title == "empty.pdf"
    assert document.records == []


def test_pdf_layout_page_becomes_three_paragraph_records() -> None:
    pdf_bytes = build_text_pdf(
        [
            "(First paragraph wraps across) Tj",
            "0 -14 Td",
            "(multiple extracted lines.) Tj",
            "0 -35 Td",
            "(Second paragraph stays separate.) Tj",
            "0 -35 Td",
            "(Third paragraph is also separate.) Tj",
        ]
    )
    document = parse_pdf_document(pdf_bytes, title="three-paragraphs.pdf")

    assert [record.source_text for record in document.records] == [
        "First paragraph wraps across multiple extracted lines.",
        "Second paragraph stays separate.",
        "Third paragraph is also separate.",
    ]
    assert [record.metadata["paragraph_index"] for record in document.records] == [1, 2, 3]


def test_pdf_wrapped_lines_and_indentation_preserve_paragraphs(monkeypatch) -> None:
    document, _pages = parse_fake_pages(
        monkeypatch,
        "A wrapped paragraph continues\nacross several extracted lines.\n"
        "    A clearly indented paragraph starts here\nand continues on its next line.",
    )

    assert [record.source_text for record in document.records] == [
        "A wrapped paragraph continues across several extracted lines.",
        "A clearly indented paragraph starts here and continues on its next line.",
    ]


def test_pdf_short_terminal_line_starts_next_paragraph_without_blank_line(monkeypatch) -> None:
    document, _pages = parse_fake_pages(
        monkeypatch,
        "The first paragraph has a long opening line that approaches the normal text width\n"
        "and then has a short ending.\n"
        "The next paragraph begins at the margin and has its own wrapped continuation line\n"
        "before reaching its final sentence.",
    )

    assert [record.source_text for record in document.records] == [
        "The first paragraph has a long opening line that approaches the normal text width "
        "and then has a short ending.",
        "The next paragraph begins at the margin and has its own wrapped continuation line "
        "before reaching its final sentence.",
    ]


def test_multiple_pdf_pages_do_not_force_one_record_per_page(monkeypatch) -> None:
    document, _pages = parse_fake_pages(
        monkeypatch,
        "Page one paragraph A.\n\nPage one paragraph B.",
        "Page two paragraph A.\n\nPage two paragraph B.\n\nPage two paragraph C.",
    )

    assert len(document.records) == 5
    assert [record.page_number for record in document.records] == [1, 1, 2, 2, 2]


def test_obvious_toc_and_boilerplate_are_not_summary_records(monkeypatch) -> None:
    document, _pages = parse_fake_pages(
        monkeypatch,
        "CONTENTS\nChapter 1 ........ 3\nChapter 2 ........ 17\nAccess for free at openstax.org",
        "Access for free at openstax.org\n\nBody prose remains available for summaries.",
    )

    assert [record.source_text for record in document.records] == [
        "Body prose remains available for summaries."
    ]
    assert document.records[0].page_number == 2


def test_pdf_record_ids_and_source_hashes_are_deterministic(monkeypatch) -> None:
    first, _pages = parse_fake_pages(monkeypatch, "First paragraph.\n\nSecond paragraph.")
    second, _pages = parse_fake_pages(monkeypatch, "First paragraph.\n\nSecond paragraph.")
    source_hash = hash_bytes(b"deterministic-pdf")

    first_ids = [
        stable_record_id(source_hash, index, page_number=record.page_number)
        for index, record in enumerate(first.records)
    ]
    second_ids = [
        stable_record_id(source_hash, index, page_number=record.page_number)
        for index, record in enumerate(second.records)
    ]

    assert first_ids == second_ids
    assert [hash_text(record.source_text) for record in first.records] == [
        hash_text(record.source_text) for record in second.records
    ]


def test_pdf_parsing_real_text_fixture() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "sample.pdf"
    document = parse_pdf_document(fixture_path.read_bytes(), title="sample.pdf")

    assert document.title == "sample.pdf"
    assert document.records
    text = " ".join(record.source_text for record in document.records)
    assert "sample PDF document" in text or "multiple paragraphs" in text
