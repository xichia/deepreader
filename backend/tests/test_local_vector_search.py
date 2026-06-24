from deepreader.retrieval.schemas import RetrievalItem
from deepreader.retrieval.vector import search_items_local_vector


def test_local_vector_search_returns_expected_record() -> None:
    items = [
        RetrievalItem(
            document_id=1,
            record_id=1,
            stable_id="doc/para_0001",
            order_index=0,
            source_text="Filter replacement schedule every 1000 hours.",
            source_hash="a",
            metadata={},
        ),
        RetrievalItem(
            document_id=1,
            record_id=2,
            stable_id="doc/para_0002",
            order_index=1,
            source_text="High motor current with vibration can indicate bearing wear.",
            source_hash="b",
            metadata={},
        ),
    ]

    hits = search_items_local_vector(
        "bearing wear",
        items,
        text_selector=lambda item: item.source_text,
        retrieval_method="local_vector_source_text",
        limit=2,
    )

    assert hits[0].record_id == 2
    assert hits[0].retrieval_method == "local_vector_source_text"
    assert hits[0].score > 0
