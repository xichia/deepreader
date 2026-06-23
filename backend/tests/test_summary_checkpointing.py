from pathlib import Path

from sqlalchemy.orm import Session

from deepreader.records.ids import hash_text
from deepreader.storage.repositories import list_document_records, list_document_summaries
from deepreader.summarise.service import SummaryJobRunner
from helpers import ingest_text_fixture


def test_summary_job_skips_existing_unchanged_summaries(
    db_session: Session,
    examples_dir: Path,
) -> None:
    document = ingest_text_fixture(db_session, examples_dir / "troubleshooting_log.txt")
    first_job = SummaryJobRunner().run_for_document(db_session, document.id)
    first_summary_ids = [summary.id for summary in list_document_summaries(db_session, document.id)]

    second_job = SummaryJobRunner().run_for_document(db_session, document.id)
    second_summary_ids = [summary.id for summary in list_document_summaries(db_session, document.id)]

    assert first_job.status == "completed"
    assert second_job.status == "completed"
    assert second_job.completed_steps == second_job.total_steps
    assert second_summary_ids == first_summary_ids


def test_changed_source_hash_creates_new_current_summary(
    db_session: Session,
    examples_dir: Path,
) -> None:
    document = ingest_text_fixture(db_session, examples_dir / "troubleshooting_log.txt")
    SummaryJobRunner().run_for_document(db_session, document.id)
    records = list_document_records(db_session, document.id)
    original_current_count = len(list_document_summaries(db_session, document.id))

    changed_record = records[0]
    changed_record.source_text = "Updated incident heading with a deterministic changed source."
    changed_record.source_hash = hash_text(changed_record.source_text)
    db_session.add(changed_record)
    db_session.commit()

    SummaryJobRunner().run_for_document(db_session, document.id)
    current_summaries = list_document_summaries(db_session, document.id)
    changed_summaries = [
        summary
        for summary in current_summaries
        if summary.record_id == changed_record.id and summary.source_hash == changed_record.source_hash
    ]

    assert len(current_summaries) == original_current_count
    assert len(changed_summaries) == 1
    assert changed_summaries[0].summary_text == "Updated incident heading with a deterministic changed source."
