"""Summary checkpoint helpers."""

from __future__ import annotations

from sqlalchemy.orm import Session

from deepreader.storage.models import DocumentRecord, RecordSummary
from deepreader.storage.repositories import get_record_summary_checkpoint


def find_existing_summary_checkpoint(
    session: Session,
    *,
    record: DocumentRecord,
    summariser_name: str,
) -> RecordSummary | None:
    """Return the current summary checkpoint for an unchanged record, if present."""

    return get_record_summary_checkpoint(
        session,
        record_id=record.id,
        summariser_name=summariser_name,
        source_hash=record.source_hash,
    )


def summary_checkpoint_exists(
    session: Session,
    *,
    record: DocumentRecord,
    summariser_name: str,
) -> bool:
    return find_existing_summary_checkpoint(
        session,
        record=record,
        summariser_name=summariser_name,
    ) is not None
