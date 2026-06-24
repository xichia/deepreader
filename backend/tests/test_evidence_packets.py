from deepreader.answer.evidence import evidence_from_result
from deepreader.retrieval.schemas import RetrievalResult


def test_evidence_packet_preserves_stable_source_fields() -> None:
    result = RetrievalResult(
        record_id=7,
        stable_id="doc_x/para_0007",
        score=1.25,
        retrieval_method="bm25_summary_text",
        source_text="Original source text.",
        summary="Summary text.",
        metadata={"section_title": "Alarm Conditions", "page_number": None, "chapter_index": 2},
        source_hash="abc",
        order_index=6,
        document_id=1,
        component_scores={"bm25_summary_text": 1.0},
    )

    packet = evidence_from_result(result)

    assert packet.stable_id == "doc_x/para_0007"
    assert packet.record_id == 7
    assert packet.source_text == "Original source text."
    assert packet.summary == "Summary text."
    assert packet.section_title == "Alarm Conditions"
    assert packet.chapter_index == 2
    assert packet.source_hash == "abc"
