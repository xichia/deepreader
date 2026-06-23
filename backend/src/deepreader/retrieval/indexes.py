"""Retrieval corpus builders and orchestration."""

from __future__ import annotations

from deepreader.retrieval.fusion import weighted_score_fusion
from deepreader.retrieval.lexical import search_items_bm25
from deepreader.retrieval.schemas import RetrievalItem, RetrievalResult
from deepreader.retrieval.vector import search_items_local_vector
from deepreader.storage.models import DocumentRecord, RecordSummary


def item_from_record(record: DocumentRecord) -> RetrievalItem:
    return RetrievalItem(
        document_id=record.document_id,
        record_id=record.id,
        stable_id=record.stable_id,
        order_index=record.order_index,
        source_text=record.source_text,
        source_hash=record.source_hash,
        metadata=dict(record.metadata_json),
        summary=None,
    )


def item_from_summary(summary: RecordSummary) -> RetrievalItem:
    record = summary.record
    metadata = dict(record.metadata_json)
    metadata.update(
        {
            "summary_id": summary.id,
            "summariser_name": summary.summariser_name,
            "summary_hash": summary.summary_hash,
            "summary_source_hash": summary.source_hash,
        }
    )
    return RetrievalItem(
        document_id=record.document_id,
        record_id=record.id,
        stable_id=record.stable_id,
        order_index=record.order_index,
        source_text=record.source_text,
        source_hash=record.source_hash,
        metadata=metadata,
        summary=summary.summary_text,
    )


def items_from_records(records: list[DocumentRecord]) -> list[RetrievalItem]:
    return [item_from_record(record) for record in records]


def items_from_summaries(summaries: list[RecordSummary]) -> list[RetrievalItem]:
    return [item_from_summary(summary) for summary in summaries]


def retrieve(
    query: str,
    *,
    source_items: list[RetrievalItem],
    summary_items: list[RetrievalItem],
    limit: int = 10,
    use_source_text: bool = True,
    use_summaries: bool = False,
    use_bm25: bool = True,
    use_local_vector: bool = False,
    use_fusion: bool = False,
) -> list[RetrievalResult]:
    result_lists: list[list[RetrievalResult]] = []

    if use_source_text and use_bm25:
        result_lists.append(
            search_items_bm25(
                query,
                source_items,
                text_selector=lambda item: item.source_text,
                retrieval_method="bm25_source_text",
                limit=limit,
            )
        )

    if use_summaries and use_bm25:
        result_lists.append(
            search_items_bm25(
                query,
                summary_items,
                text_selector=lambda item: item.summary or "",
                retrieval_method="bm25_summary_text",
                limit=limit,
            )
        )

    if use_source_text and use_local_vector:
        result_lists.append(
            search_items_local_vector(
                query,
                source_items,
                text_selector=lambda item: item.source_text,
                retrieval_method="local_vector_source_text",
                limit=limit,
            )
        )

    if use_summaries and use_local_vector:
        result_lists.append(
            search_items_local_vector(
                query,
                summary_items,
                text_selector=lambda item: item.summary or "",
                retrieval_method="local_vector_summary_text",
                limit=limit,
            )
        )

    result_lists = [results for results in result_lists if results]
    if not result_lists:
        return []

    if use_fusion and len(result_lists) > 1:
        return weighted_score_fusion(result_lists, limit=limit)

    combined = [result for results in result_lists for result in results]
    combined.sort(key=lambda result: (-result.score, result.order_index, result.record_id, result.retrieval_method))
    return combined[:limit]
