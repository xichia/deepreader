"""Citation mapping helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from deepreader.answer.evidence import EvidencePacket


@dataclass(frozen=True)
class Citation:
    stable_id: str
    record_id: int
    quoted_text: str
    section_title: str | None
    page_number: int | None
    chapter_index: int | None
    order_index: int
    source_hash: str

    def to_dict(self) -> dict:
        return asdict(self)


def citation_from_evidence(evidence: EvidencePacket, quoted_text: str | None = None) -> Citation:
    """Create a citation tied to the original source record, never summary-only."""

    return Citation(
        stable_id=evidence.stable_id,
        record_id=evidence.record_id,
        quoted_text=(quoted_text or evidence.source_text).strip(),
        section_title=evidence.section_title,
        page_number=evidence.page_number,
        chapter_index=evidence.chapter_index,
        order_index=evidence.order_index,
        source_hash=evidence.source_hash,
    )


def dedupe_citations(citations: list[Citation]) -> list[Citation]:
    seen: set[tuple[int, str]] = set()
    deduped: list[Citation] = []
    for citation in citations:
        key = (citation.record_id, citation.stable_id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)
    return deduped
