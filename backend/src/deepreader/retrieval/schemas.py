"""Shared retrieval result schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class RetrievalItem:
    document_id: int
    record_id: int
    stable_id: str
    order_index: int
    source_text: str
    source_hash: str
    metadata: dict[str, Any]
    summary: str | None = None


@dataclass(frozen=True)
class RetrievalResult:
    record_id: int
    stable_id: str
    score: float
    retrieval_method: str
    source_text: str
    summary: str | None
    metadata: dict[str, Any]
    source_hash: str
    order_index: int
    document_id: int
    component_scores: dict[str, float] = field(default_factory=dict)


TextSelector = Callable[[RetrievalItem], str]


def result_from_item(item: RetrievalItem, *, score: float, retrieval_method: str) -> RetrievalResult:
    return RetrievalResult(
        record_id=item.record_id,
        stable_id=item.stable_id,
        score=score,
        retrieval_method=retrieval_method,
        source_text=item.source_text,
        summary=item.summary,
        metadata=dict(item.metadata),
        source_hash=item.source_hash,
        order_index=item.order_index,
        document_id=item.document_id,
        component_scores={retrieval_method: score},
    )
