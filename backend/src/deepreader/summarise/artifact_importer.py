"""Validation and persistence for remote summary artifacts."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepreader.security import sanitize_diagnostic_text
from deepreader.storage.models import DocumentRecord, RecordSummary
from deepreader.storage.repositories import get_document

LOGGER = logging.getLogger(__name__)
MAX_FAILURE_EXAMPLES = 5


def import_summary_artifact(
    session: Session,
    document_id: int,
    artifact_lines: list[dict[str, Any]],
    *,
    remote_job_id: str | None = None,
) -> dict[str, Any]:
    """Validate an artifact, import successes, and compactly summarize failures."""

    document = get_document(session, document_id)
    if not document:
        raise ValueError(f"Document {document_id} not found")

    records = session.scalars(
        select(DocumentRecord).where(DocumentRecord.document_id == document_id)
    ).all()
    record_map = {record.stable_id: record for record in records}
    error_code_counts: Counter[str] = Counter()
    stats: dict[str, Any] = {
        "imported": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "imported_record_ids": [],
        "skipped_record_ids": [],
        "failed_record_ids": [],
        "error_code_counts": {},
        "failed_examples": [],
        "failed_details_by_record": {},
        "failure_summary": None,
    }
    seen_record_ids: set[str] = set()

    def record_failure(
        record_id: str,
        line: dict[str, Any],
        error_code: str,
        message: str,
    ) -> None:
        error_code = sanitize_diagnostic_text(error_code)[:100] or "remote_result_failed"
        detail = sanitize_diagnostic_text(message)
        stats["failed"] += 1
        stats["failed_record_ids"].append(record_id)
        stats["failed_details_by_record"].setdefault(
            record_id,
            f"{error_code}: {detail}",
        )
        error_code_counts[error_code] += 1
        if len(stats["failed_examples"]) < MAX_FAILURE_EXAMPLES:
            stats["failed_examples"].append(
                {
                    "record_id": record_id,
                    "stable_id": line.get("stable_id"),
                    "error_code": error_code,
                    "message": detail,
                    "error": sanitize_diagnostic_text(line.get("error")) if line.get("error") else None,
                    "provider": (
                        sanitize_diagnostic_text(line["provider"])
                        if isinstance(line.get("provider"), str)
                        else None
                    ),
                    "model": (
                        sanitize_diagnostic_text(line["model"])
                        if isinstance(line.get("model"), str)
                        else None
                    ),
                }
            )

    for line in artifact_lines:
        record_id = str(line.get("record_id"))

        if record_id in seen_record_ids:
            record_failure(
                record_id,
                line,
                "duplicate_record_id",
                f"Artifact contains duplicate record_id {record_id}",
            )
            continue
        seen_record_ids.add(record_id)

        if str(line.get("document_id")) != str(document_id):
            record_failure(
                record_id,
                line,
                "document_id_mismatch",
                f"Artifact document_id does not match document {document_id}",
            )
            continue

        if record_id not in record_map:
            record_failure(
                record_id,
                line,
                "unknown_record_id",
                f"Artifact record_id was not found in document {document_id}",
            )
            continue

        record = record_map[record_id]
        if line.get("stable_id") != record.stable_id:
            record_failure(
                record_id,
                line,
                "stable_id_mismatch",
                "Artifact stable_id does not match the backend record",
            )
            continue

        if line.get("source_hash") != record.source_hash:
            record_failure(
                record_id,
                line,
                "source_hash_mismatch",
                "Artifact source_hash does not match the backend record",
            )
            continue

        artifact_status = line.get("status")
        if artifact_status == "skipped":
            stats["skipped"] += 1
            stats["skipped_record_ids"].append(record_id)
            continue
        if artifact_status != "completed":
            error_code = str(line.get("error_code") or "remote_result_failed")
            message = line.get("message") or line.get("error") or (
                f"Remote artifact reported status {artifact_status!r}"
            )
            record_failure(record_id, line, error_code, str(message))
            continue

        summary_text = line.get("summary_text")
        if not isinstance(summary_text, str) or not summary_text.strip():
            record_failure(
                record_id,
                line,
                "empty_summary",
                "Completed artifact result contained an empty summary",
            )
            continue

        summariser_name = line.get("provider") or "remote"
        summary_hash = hashlib.sha256(summary_text.encode("utf-8")).hexdigest()
        existing = session.scalars(
            select(RecordSummary)
            .where(RecordSummary.record_id == record.id)
            .where(RecordSummary.summariser_name == summariser_name)
            .where(RecordSummary.source_hash == record.source_hash)
        ).first()

        if existing:
            summary = existing
            summary.summary_text = summary_text
            summary.summary_hash = summary_hash
        else:
            summary = RecordSummary(
                document_id=document.id,
                record_id=record.id,
                stable_id=record.stable_id,
                summary_text=summary_text,
                summariser_name=summariser_name,
                summary_hash=summary_hash,
                source_hash=record.source_hash,
            )
            session.add(summary)

        summary.summary_style = line.get("summary_style")
        summary.provider = line.get("provider")
        summary.model = line.get("model")
        summary.template_version = line.get("template_version")
        summary.status = line.get("status", "completed")
        summary.error_code = line.get("error_code")
        summary.usage_json = line.get("usage", {})
        stats["imported"] += 1
        stats["imported_record_ids"].append(record_id)

    if stats["failed"]:
        stats["error_code_counts"] = dict(sorted(error_code_counts.items()))
        counts = ", ".join(
            f"{code}={count}" for code, count in stats["error_code_counts"].items()
        )
        examples = json.dumps(stats["failed_examples"], sort_keys=True)
        job_label = remote_job_id or "unknown"
        stats["failure_summary"] = (
            f"Remote job {job_label} had {stats['failed']} failed artifact line(s); "
            f"error codes: {counts}; first {len(stats['failed_examples'])} failed lines: {examples}"
        )
        stats["errors"] = [stats["failure_summary"]]
        LOGGER.warning("%s", stats["failure_summary"])

    session.commit()
    return stats
