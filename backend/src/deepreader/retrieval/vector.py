"""Deterministic local vector-style retrieval."""

from __future__ import annotations

import math
from collections import Counter

from deepreader.retrieval.bm25 import tokenize
from deepreader.retrieval.schemas import RetrievalItem, RetrievalResult, TextSelector, result_from_item


def search_items_local_vector(
    query: str,
    items: list[RetrievalItem],
    *,
    text_selector: TextSelector,
    retrieval_method: str,
    limit: int = 10,
) -> list[RetrievalResult]:
    query_tokens = tokenize(query)
    if not query_tokens or not items:
        return []

    document_tokens = [tokenize(text_selector(item)) for item in items]
    idf = _build_idf(document_tokens)
    query_vector = _tf_idf_vector(query_tokens, idf)
    query_norm = _vector_norm(query_vector)
    if query_norm == 0:
        return []

    results: list[RetrievalResult] = []
    for item, tokens in zip(items, document_tokens, strict=True):
        document_vector = _tf_idf_vector(tokens, idf)
        document_norm = _vector_norm(document_vector)
        if document_norm == 0:
            continue

        score = _dot(query_vector, document_vector) / (query_norm * document_norm)
        if score > 0:
            results.append(result_from_item(item, score=score, retrieval_method=retrieval_method))

    results.sort(key=lambda result: (-result.score, result.order_index, result.record_id))
    return results[:limit]


def _build_idf(documents: list[list[str]]) -> dict[str, float]:
    document_count = len(documents)
    document_frequencies: Counter[str] = Counter()
    for tokens in documents:
        document_frequencies.update(set(tokens))
    return {
        term: math.log(1 + (document_count + 1) / (frequency + 1)) + 1
        for term, frequency in document_frequencies.items()
    }


def _tf_idf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    frequencies = Counter(tokens)
    if not frequencies:
        return {}
    total = sum(frequencies.values())
    return {
        term: (frequency / total) * idf.get(term, 0.0)
        for term, frequency in frequencies.items()
    }


def _vector_norm(vector: dict[str, float]) -> float:
    return math.sqrt(sum(value * value for value in vector.values()))


def _dot(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(term, 0.0) for term, value in left.items())
