"""Deterministic local extractive summariser."""

from __future__ import annotations

import re

from deepreader.records.ids import hash_text
from deepreader.summarise.summariser import GeneratedSummary, SummaryInput

LOCAL_SUMMARISER_NAME = "local_extractive_v1"
_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+")


class LocalExtractiveSummariser:
    """Small deterministic summariser used for local v0.2 demos and tests."""

    name = LOCAL_SUMMARISER_NAME

    def __init__(self, max_chars: int = 280) -> None:
        self.max_chars = max_chars

    def summarise(self, item: SummaryInput) -> GeneratedSummary:
        text = normalise_whitespace(item.source_text)
        sentence = first_sentence(text)
        summary_text = truncate_summary(sentence, self.max_chars)
        summary_hash = hash_text(f"{self.name}\n{item.source_hash}\n{summary_text}")
        return GeneratedSummary(
            summary_text=summary_text,
            summariser_name=self.name,
            summary_hash=summary_hash,
        )


def normalise_whitespace(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip()


def first_sentence(text: str) -> str:
    if not text:
        return ""

    parts = _SENTENCE_BOUNDARY_RE.split(text, maxsplit=1)
    return parts[0].strip()


def truncate_summary(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text

    truncated = text[: max_chars - 1].rstrip()
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0].rstrip()
    return f"{truncated}..."
