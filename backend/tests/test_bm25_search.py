from types import SimpleNamespace

from deepreader.retrieval.bm25 import search_records


def test_bm25_ranks_matching_records_highest() -> None:
    records = [
        SimpleNamespace(id=1, order_index=0, source_text="Filter replacement schedule every 1000 hours."),
        SimpleNamespace(
            id=2,
            order_index=1,
            source_text="Alarm A12 low flow usually means a blocked filter or closed outlet valve.",
        ),
        SimpleNamespace(
            id=3,
            order_index=2,
            source_text="High motor current with vibration can indicate bearing wear.",
        ),
    ]

    hits = search_records("low flow blocked filter", records, limit=2)

    assert hits[0].record.id == 2
    assert hits[0].score > hits[1].score
