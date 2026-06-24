from deepreader.answer.evidence import EvidencePacket
from deepreader.answer.extractive_answerer import LocalExtractiveAnswerer


def _evidence(text: str, score: float = 1.0) -> EvidencePacket:
    return EvidencePacket(
        stable_id="doc/para_0001",
        record_id=1,
        source_text=text,
        summary=None,
        section_title="Alarm Conditions",
        page_number=None,
        chapter_index=None,
        order_index=0,
        retrieval_method="bm25_source_text",
        score=score,
        source_hash="hash",
        metadata={},
        component_scores={},
    )


def test_extractive_answerer_selects_relevant_sentences_and_cites() -> None:
    answer = LocalExtractiveAnswerer().answer(
        "What causes low flow?",
        [
            _evidence(
                "Alarm A12 indicates low flow. The most common causes are a blocked filter, closed outlet valve, failed flow sensor, or air trapped in the line."
            )
        ],
    )

    assert "low flow" in answer.answer.lower()
    assert "doc/para_0001" in answer.answer
    assert answer.citations
    assert answer.citations[0].record_id == 1
    assert answer.confidence in {"low", "medium"}


def test_extractive_answerer_refuses_without_evidence() -> None:
    answer = LocalExtractiveAnswerer().answer("What causes low flow?", [])

    assert answer.confidence == "none"
    assert "No answer can be produced" in answer.answer
    assert answer.citations == []


def test_extractive_answerer_caveats_weak_evidence() -> None:
    answer = LocalExtractiveAnswerer().answer("What causes low flow?", [_evidence("Inspect valves monthly.")])

    assert answer.confidence == "low"
    assert answer.answer.startswith("Available evidence is weak")
