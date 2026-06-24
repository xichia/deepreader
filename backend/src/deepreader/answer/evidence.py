"""Evidence packet construction."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from deepreader.retrieval.schemas import RetrievalResult


@dataclass(frozen=True)
class EvidencePacket:
    stable_id: str
    record_id: int
    source_text: str
    summary: str | None
    section_title: str | None
    page_number: int | None
    chapter_index: int | None
    order_index: int
    retrieval_method: str
    score: float
    source_hash: str
    metadata: dict[str, Any]
    component_scores: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evidence_from_result(result: RetrievalResult) -> EvidencePacket:
    return EvidencePacket(
        stable_id=result.stable_id,
        record_id=result.record_id,
        source_text=result.source_text,
        summary=result.summary,
        section_title=_optional_str(result.metadata.get("section_title")),
        page_number=_optional_int(result.metadata.get("page_number")),
        chapter_index=_optional_int(result.metadata.get("chapter_index")),
        order_index=result.order_index,
        retrieval_method=result.retrieval_method,
        score=result.score,
        source_hash=result.source_hash,
        metadata=dict(result.metadata),
        component_scores=dict(result.component_scores),
    )


def evidence_packets_from_results(results: list[RetrievalResult]) -> list[EvidencePacket]:
    return [evidence_from_result(result) for result in results]


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: object) -> int | None:
    return value if isinstance(value, int) else None
