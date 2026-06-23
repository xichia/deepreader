"""Deterministic paragraph chunking."""

from __future__ import annotations

import re

_BLANK_LINE_RE = re.compile(r"\n\s*\n+")


def split_paragraphs(text: str) -> list[str]:
    """Split text into non-empty paragraphs on blank lines."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[str] = []

    for raw_paragraph in _BLANK_LINE_RE.split(normalized):
        paragraph = raw_paragraph.strip()
        if paragraph:
            paragraphs.append(paragraph)

    return paragraphs
