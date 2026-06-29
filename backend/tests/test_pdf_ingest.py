import pytest
from deepreader.ingest.pdf_parser import parse_pdf_document

def test_pdf_parsing():
    try:
        from pypdf import PdfWriter
    except ImportError:
        pytest.skip("pypdf not installed")

    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    # Actually pypdf doesn't easily create text PDFs from scratch like this for testing.
    # We will just verify the parser handles an empty PDF properly.
    import io
    pdf_bytes = io.BytesIO()
    writer.write(pdf_bytes)
    
    doc = parse_pdf_document(pdf_bytes.getvalue(), title="empty.pdf")
    assert doc.title == "empty.pdf"
    assert len(doc.records) > 0
    assert doc.records[0].metadata["status"] == "empty_or_skipped"
    assert doc.records[0].page_number == 1

def test_pdf_parsing_real_text():
    import os
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample.pdf")
    if not os.path.exists(fixture_path):
        pytest.skip("sample.pdf fixture not found")
        
    with open(fixture_path, "rb") as f:
        pdf_bytes = f.read()
        
    doc = parse_pdf_document(pdf_bytes, title="sample.pdf")
    
    assert doc.title == "sample.pdf"
    assert len(doc.records) > 0
    # The first record should contain text from page 1
    text = doc.records[0].source_text
    assert "sample PDF document" in text or "multiple paragraphs" in text
