"""Answer formatting helpers."""

from __future__ import annotations


def citation_marker(stable_id: str) -> str:
    return f"[{stable_id}]"


def sentence_with_citation(sentence: str, stable_id: str) -> str:
    clean_sentence = sentence.strip()
    if not clean_sentence:
        return citation_marker(stable_id)
    return f"{clean_sentence} {citation_marker(stable_id)}"
