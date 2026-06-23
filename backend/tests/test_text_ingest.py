from pathlib import Path

from sqlalchemy.orm import Session

from deepreader.ingest.text_parser import parse_text_document
from deepreader.storage.repositories import ingest_parsed_document, list_document_records


def test_text_ingest_stores_ordered_records_with_source_hashes(
    db_session: Session,
    examples_dir: Path,
) -> None:
    source_path = examples_dir / "simple_manual.txt"
    data = source_path.read_bytes()
    parsed = parse_text_document(data.decode("utf-8"))

    document = ingest_parsed_document(
        db_session,
        parsed_document=parsed,
        source_filename=source_path.name,
        source_type="txt",
        source_bytes=data,
    )
    records = list_document_records(db_session, document.id)

    assert document.title == "Cooling Pump Maintenance Manual"
    assert len(records) > 15
    assert [record.order_index for record in records] == list(range(len(records)))
    assert all(record.stable_id.startswith("doc_") for record in records)
    assert all(record.source_hash for record in records)
    assert any("Alarm A12 indicates low flow" in record.source_text for record in records)


def test_text_ingest_reuses_stable_ids_for_same_input(
    db_session: Session,
    examples_dir: Path,
) -> None:
    source_path = examples_dir / "simple_manual.txt"
    data = source_path.read_bytes()
    parsed = parse_text_document(data.decode("utf-8"))

    first = ingest_parsed_document(
        db_session,
        parsed_document=parsed,
        source_filename=source_path.name,
        source_type="txt",
        source_bytes=data,
    )
    second = ingest_parsed_document(
        db_session,
        parsed_document=parsed,
        source_filename=source_path.name,
        source_type="txt",
        source_bytes=data,
    )

    first_ids = [record.stable_id for record in list_document_records(db_session, first.id)]
    second_ids = [record.stable_id for record in list_document_records(db_session, second.id)]
    assert first_ids == second_ids
