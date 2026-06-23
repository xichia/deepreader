"""Lexical retrieval helpers."""

from __future__ import annotations

from deepreader.retrieval.bm25 import BM25Index
from deepreader.retrieval.schemas import RetrievalItem, RetrievalResult, TextSelector, result_from_item


def search_items_bm25(
    query: str,
    items: list[RetrievalItem],
    *,
    text_selector: TextSelector,
    retrieval_method: str,
    limit: int = 10,
) -> list[RetrievalResult]:
    texts = [text_selector(item) for item in items]
    index = BM25Index(texts)
    scores = index.scores(query)
    results = [
        result_from_item(item, score=score, retrieval_method=retrieval_method)
        for item, score in zip(items, scores, strict=True)
        if score > 0
    ]
    results.sort(key=lambda result: (-result.score, result.order_index, result.record_id))
    return results[:limit]
