from deepreader.records.chunker import split_paragraphs


def test_paragraph_chunking_trims_ignores_empty_and_preserves_order() -> None:
    text = "  First paragraph.  \n\n\nSecond line A\nSecond line B\n\n   \nThird paragraph.\r\n"

    assert split_paragraphs(text) == [
        "First paragraph.",
        "Second line A\nSecond line B",
        "Third paragraph.",
    ]
