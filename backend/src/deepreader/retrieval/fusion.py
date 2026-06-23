"""Deterministic retrieval result fusion."""

from __future__ import annotations

from collections import defaultdict

from deepreader.retrieval.schemas import RetrievalResult


def normalise_scores(results: list[RetrievalResult]) -> dict[int, float]:
    if not results:
        return {}
    max_score = max(result.score for result in results)
    if max_score <= 0:
        return {result.record_id: 0.0 for result in results}
    return {result.record_id: result.score / max_score for result in results}


def weighted_score_fusion(
    result_lists: list[list[RetrievalResult]],
    *,
    limit: int = 10,
    retrieval_method: str = "fused",
) -> list[RetrievalResult]:
    by_record: dict[int, RetrievalResult] = {}
    combined_scores: defaultdict[int, float] = defaultdict(float)
    component_scores: defaultdict[int, dict[str, float]] = defaultdict(dict)

    for results in result_lists:
        normalised = normalise_scores(results)
        for result in results:
            current = by_record.get(result.record_id)
            if current is None or result.summary is not None or result.score > current.score:
                by_record[result.record_id] = result
            score = normalised.get(result.record_id, 0.0)
            combined_scores[result.record_id] += score
            component_scores[result.record_id][result.retrieval_method] = score

    fused_results: list[RetrievalResult] = []
    for record_id, base in by_record.items():
        score = combined_scores[record_id]
        fused_results.append(
            RetrievalResult(
                record_id=base.record_id,
                stable_id=base.stable_id,
                score=score,
                retrieval_method=retrieval_method,
                source_text=base.source_text,
                summary=base.summary,
                metadata=dict(base.metadata),
                source_hash=base.source_hash,
                order_index=base.order_index,
                document_id=base.document_id,
                component_scores=dict(sorted(component_scores[record_id].items())),
            )
        )

    fused_results.sort(key=lambda result: (-result.score, result.order_index, result.record_id))
    return fused_results[:limit]
