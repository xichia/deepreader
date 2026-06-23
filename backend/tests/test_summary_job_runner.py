from pathlib import Path

from sqlalchemy.orm import Session

from deepreader.storage.repositories import list_document_records, list_document_summaries
from deepreader.summarise.service import SummaryJobRunner
from helpers import ingest_text_fixture


def test_summary_job_runner_completes_and_updates_progress(
    db_session: Session,
    examples_dir: Path,
) -> None:
    document = ingest_text_fixture(db_session, examples_dir / "simple_manual.txt")
    records = list_document_records(db_session, document.id)

    job = SummaryJobRunner().run_for_document(db_session, document.id)
    summaries = list_document_summaries(db_session, document.id)

    assert job.status == "completed"
    assert job.total_steps == len(records)
    assert job.completed_steps == len(records)
    assert job.failed_steps == 0
    assert job.finished_at is not None
    assert len(job.steps) == len(records)
    assert all(step.status == "completed" for step in job.steps)
    assert all(step.attempt_count == 1 for step in job.steps)
    assert len(summaries) == len(records)
