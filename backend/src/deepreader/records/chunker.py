"""Deterministic paragraph chunking."""

from __future__ import annotations

import re

_BLANK_LINE_RE = re.compile(r"\n\s*\n+")


def split_paragraphs(text: str) -> list[str]:
    """Split text into non-empty paragraphs on blank lines and reflow lines."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs: list[str] = []

    for raw_paragraph in _BLANK_LINE_RE.split(normalized):
        lines = [line.strip() for line in raw_paragraph.split("\n")]
        lines = [line for line in lines if line]
        if not lines:
            continue
        joined = " ".join(lines)
        reflowed = re.sub(r"\s+", " ", joined).strip()
        if reflowed:
            paragraphs.append(reflowed)

    return paragraphs
