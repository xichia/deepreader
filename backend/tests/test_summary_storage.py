from pathlib import Path

from sqlalchemy.orm import Session

from deepreader.summarise.local import LocalExtractiveSummariser
from deepreader.summarise.summariser import SummaryInput
from deepreader.storage.repositories import create_record_summary, list_document_records, list_document_summaries
from helpers import ingest_text_fixture


def test_summary_storage_maps_to_record_id_and_stable_id(
    db_session: Session,
    examples_dir: Path,
) -> None:
    document = ingest_text_fixture(db_session, examples_dir / "simple_manual.txt")
    record = list_document_records(db_session, document.id)[0]
    summariser = LocalExtractiveSummariser()
    generated = summariser.summarise(
        SummaryInput(
            stable_id=record.stable_id,
            source_text=record.source_text,
            source_hash=record.source_hash,
            metadata=record.metadata_json,
        )
    )

    summary = create_record_summary(
        db_session,
        record=record,
        summary_text=generated.summary_text,
        summariser_name=generated.summariser_name,
        summary_hash=generated.summary_hash,
    )
    db_session.commit()

    summaries = list_document_summaries(db_session, document.id)
    assert summaries == [summary]
    assert summaries[0].record_id == record.id
    assert summaries[0].stable_id == record.stable_id
    assert summaries[0].source_hash == record.source_hash
    assert summaries[0].summary_text
