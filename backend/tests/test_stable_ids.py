from deepreader.records.ids import hash_text, stable_record_id


def test_stable_ids_are_deterministic_for_same_source_and_order() -> None:
    source_hash = hash_text("same source document")

    first = stable_record_id(source_hash, 3, chapter_index=2)
    second = stable_record_id(source_hash, 3, chapter_index=2)

    assert first == second
    assert first.startswith("doc_")
    assert first.endswith("/ch_003/p_0004")


def test_stable_ids_change_when_document_content_changes() -> None:
    first_hash = hash_text("same source document")
    second_hash = hash_text("changed source document")

    assert stable_record_id(first_hash, 0) != stable_record_id(second_hash, 0)
