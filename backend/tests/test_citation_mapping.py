from deepreader.answer.citations import citation_from_evidence, dedupe_citations
from deepreader.answer.evidence import EvidencePacket


def _evidence(record_id: int, stable_id: str) -> EvidencePacket:
    return EvidencePacket(
        stable_id=stable_id,
        record_id=record_id,
        source_text="Alarm A12 indicates low flow.",
        summary="A12 low flow.",
        section_title="Alarm Conditions",
        page_number=None,
        chapter_index=None,
        order_index=record_id,
        retrieval_method="bm25_summary_text",
        score=1.0,
        source_hash="hash",
        metadata={},
        component_scores={},
    )


def test_citation_maps_summary_hit_back_to_original_record() -> None:
    citation = citation_from_evidence(_evidence(12, "doc/para_0012"), "Alarm A12 indicates low flow.")

    assert citation.record_id == 12
    assert citation.stable_id == "doc/para_0012"
    assert citation.quoted_text == "Alarm A12 indicates low flow."
    assert citation.section_title == "Alarm Conditions"


def test_citation_dedupe_preserves_order() -> None:
    first = citation_from_evidence(_evidence(1, "doc/para_0001"))
    duplicate = citation_from_evidence(_evidence(1, "doc/para_0001"))
    second = citation_from_evidence(_evidence(2, "doc/para_0002"))

    assert dedupe_citations([first, duplicate, second]) == [first, second]
