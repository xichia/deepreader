"""Deterministic local extractive answerer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from deepreader.answer.citations import Citation, citation_from_evidence, dedupe_citations
from deepreader.answer.evidence import EvidencePacket
from deepreader.answer.formatter import sentence_with_citation
from deepreader.retrieval.bm25 import tokenize

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class ExtractiveAnswer:
    question: str
    answer: str
    confidence: str
    citations: list[Citation]
    used_evidence: list[EvidencePacket]
    unused_evidence: list[EvidencePacket]

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "confidence": self.confidence,
            "citations": [citation.to_dict() for citation in self.citations],
            "used_evidence": [evidence.to_dict() for evidence in self.used_evidence],
            "unused_evidence": [evidence.to_dict() for evidence in self.unused_evidence],
        }


@dataclass(frozen=True)
class _SentenceCandidate:
    sentence: str
    evidence: EvidencePacket
    score: float
    overlap: int


class LocalExtractiveAnswerer:
    name = "local_extractive_answerer_v1"

    def __init__(self, max_sentences: int = 3) -> None:
        self.max_sentences = max_sentences

    def answer(self, question: str, evidence: list[EvidencePacket]) -> ExtractiveAnswer:
        if not evidence:
            return ExtractiveAnswer(
                question=question,
                answer="No answer can be produced because no supporting evidence was retrieved.",
                confidence="none",
                citations=[],
                used_evidence=[],
                unused_evidence=[],
            )

        question_terms = set(tokenize(question))
        candidates = _rank_sentence_candidates(question_terms, evidence)
        positive = [candidate for candidate in candidates if candidate.overlap > 0]

        if positive:
            selected = _dedupe_sentences(positive)[: self.max_sentences]
            confidence = "medium" if len(selected) > 1 else "low"
            answer_text = " ".join(
                sentence_with_citation(candidate.sentence, candidate.evidence.stable_id)
                for candidate in selected
            )
        else:
            selected = [_top_sentence_from_evidence(evidence[0])]
            confidence = "low"
            answer_text = (
                "Available evidence is weak, but the top retrieved source says: "
                f"{sentence_with_citation(selected[0].sentence, selected[0].evidence.stable_id)}"
            )

        used_evidence = _dedupe_evidence([candidate.evidence for candidate in selected])
        unused_evidence = [item for item in evidence if item.record_id not in {used.record_id for used in used_evidence}]
        citations = dedupe_citations(
            [citation_from_evidence(candidate.evidence, candidate.sentence) for candidate in selected]
        )

        return ExtractiveAnswer(
            question=question,
            answer=answer_text,
            confidence=confidence,
            citations=citations,
            used_evidence=used_evidence,
            unused_evidence=unused_evidence,
        )


def _rank_sentence_candidates(question_terms: set[str], evidence: list[EvidencePacket]) -> list[_SentenceCandidate]:
    candidates: list[_SentenceCandidate] = []
    for evidence_index, packet in enumerate(evidence):
        for sentence_index, sentence in enumerate(_sentences(packet.source_text)):
            sentence_terms = set(tokenize(sentence))
            overlap = len(question_terms & sentence_terms)
            score = overlap + (packet.score * 0.01) - (evidence_index * 0.001) - (sentence_index * 0.0001)
            candidates.append(_SentenceCandidate(sentence=sentence, evidence=packet, score=score, overlap=overlap))
    candidates.sort(key=lambda candidate: (-candidate.score, candidate.evidence.order_index, candidate.sentence))
    return candidates


def _sentences(text: str) -> list[str]:
    parts = [part.strip() for part in _SENTENCE_RE.split(text.strip()) if part.strip()]
    return parts or [text.strip()]


def _dedupe_sentences(candidates: list[_SentenceCandidate]) -> list[_SentenceCandidate]:
    seen: set[str] = set()
    deduped: list[_SentenceCandidate] = []
    for candidate in candidates:
        key = candidate.sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _top_sentence_from_evidence(evidence: EvidencePacket) -> _SentenceCandidate:
    return _SentenceCandidate(sentence=_sentences(evidence.source_text)[0], evidence=evidence, score=0.0, overlap=0)


def _dedupe_evidence(evidence: list[EvidencePacket]) -> list[EvidencePacket]:
    seen: set[int] = set()
    deduped: list[EvidencePacket] = []
    for packet in evidence:
        if packet.record_id in seen:
            continue
        seen.add(packet.record_id)
        deduped.append(packet)
    return deduped
