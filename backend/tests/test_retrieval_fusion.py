from deepreader.retrieval.fusion import weighted_score_fusion
from deepreader.retrieval.schemas import RetrievalResult


def _result(record_id: int, method: str, score: float) -> RetrievalResult:
    return RetrievalResult(
        record_id=record_id,
        stable_id=f"doc/para_{record_id:04d}",
        score=score,
        retrieval_method=method,
        source_text=f"source {record_id}",
        summary=None,
        metadata={},
        source_hash=str(record_id),
        order_index=record_id,
        document_id=1,
        component_scores={method: score},
    )


def test_weighted_score_fusion_combines_methods_deterministically() -> None:
    fused = weighted_score_fusion(
        [
            [_result(1, "bm25_source_text", 10.0), _result(2, "bm25_source_text", 5.0)],
            [_result(2, "local_vector_source_text", 1.0), _result(3, "local_vector_source_text", 0.5)],
        ],
        limit=3,
    )

    assert [result.record_id for result in fused] == [2, 1, 3]
    assert fused[0].retrieval_method == "fused"
    assert fused[0].component_scores == {
        "bm25_source_text": 0.5,
        "local_vector_source_text": 1.0,
    }
