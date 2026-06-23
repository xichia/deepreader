"""Small inspectable BM25 implementation over source text."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_TOKEN_NORMALIZATIONS = {
    "replace": "replace",
    "replaced": "replace",
    "replacement": "replace",
    "replacements": "replace",
    "replaces": "replace",
    "replacing": "replace",
}


class SearchableRecord(Protocol):
    id: int
    order_index: int
    source_text: str


@dataclass(frozen=True)
class SearchHit:
    record: SearchableRecord
    score: float


def tokenize(text: str) -> list[str]:
    return [_TOKEN_NORMALIZATIONS.get(token, token) for token in _TOKEN_RE.findall(text.lower())]


class BM25Index:
    def __init__(self, documents: list[str], *, k1: float = 1.5, b: float = 0.75) -> None:
        self.documents = documents
        self.k1 = k1
        self.b = b
        self.tokenized_documents = [tokenize(document) for document in documents]
        self.document_count = len(self.tokenized_documents)
        self.document_lengths = [len(tokens) for tokens in self.tokenized_documents]
        self.average_document_length = (
            sum(self.document_lengths) / self.document_count if self.document_count else 0.0
        )
        self.term_frequencies = [Counter(tokens) for tokens in self.tokenized_documents]
        self.idf = self._build_idf()

    def _build_idf(self) -> dict[str, float]:
        document_frequencies: Counter[str] = Counter()
        for tokens in self.tokenized_documents:
            document_frequencies.update(set(tokens))

        return {
            term: math.log(1 + (self.document_count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequencies.items()
        }

    def scores(self, query: str) -> list[float]:
        query_terms = tokenize(query)
        if not query_terms or not self.document_count:
            return [0.0 for _ in self.documents]

        scores: list[float] = []
        for index, frequencies in enumerate(self.term_frequencies):
            document_length = self.document_lengths[index]
            score = 0.0
            for term in query_terms:
                term_frequency = frequencies.get(term, 0)
                if term_frequency == 0:
                    continue

                idf = self.idf.get(term, 0.0)
                denominator = term_frequency + self.k1 * (
                    1 - self.b + self.b * document_length / (self.average_document_length or 1.0)
                )
                score += idf * (term_frequency * (self.k1 + 1)) / denominator
            scores.append(score)

        return scores


def search_records(query: str, records: list[SearchableRecord], *, limit: int = 10) -> list[SearchHit]:
    index = BM25Index([record.source_text for record in records])
    scores = index.scores(query)
    hits = [
        SearchHit(record=record, score=score)
        for record, score in zip(records, scores, strict=True)
        if score > 0
    ]
    hits.sort(key=lambda hit: (-hit.score, hit.record.order_index, hit.record.id))
    return hits[:limit]
