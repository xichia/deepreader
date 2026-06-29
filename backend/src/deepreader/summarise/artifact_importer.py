import hashlib
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from deepreader.storage.models import DocumentRecord, RecordSummary
from deepreader.storage.repositories import get_document

LOGGER = logging.getLogger(__name__)


def import_summary_artifact(session: Session, document_id: int, artifact_lines: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Validates and imports remote summary artifacts.
    Returns a dict with imported, skipped, failed counts, and error list.
    """
    
    document = get_document(session, document_id)
    if not document:
        raise ValueError(f"Document {document_id} not found")

    records = session.scalars(
        select(DocumentRecord).where(DocumentRecord.document_id == document_id)
    ).all()
    
    # Map by canonical stable_id
    record_map = {r.stable_id: r for r in records}
    
    stats: dict[str, Any] = {
        "imported": 0,
        "skipped": 0,
        "failed": 0,
        "errors": [],
        "imported_record_ids": [],
        "skipped_record_ids": [],
        "failed_record_ids": [],
    }
    seen_record_ids: set[str] = set()
    
    for line in artifact_lines:
        record_id = str(line.get("record_id"))

        if record_id in seen_record_ids:
            msg = f"Artifact contains duplicate record_id {record_id}"
            LOGGER.warning(msg)
            stats["failed"] += 1
            stats["errors"].append(msg)
            stats["failed_record_ids"].append(record_id)
            continue
        seen_record_ids.add(record_id)

        if str(line.get("document_id")) != str(document_id):
            msg = f"Artifact line document_id mismatch: {line.get('document_id')} != {document_id}"
            LOGGER.warning(msg)
            stats["failed"] += 1
            stats["errors"].append(msg)
            stats["failed_record_ids"].append(record_id)
            continue
            
        if record_id not in record_map:
            msg = f"Artifact line canonical record_id {record_id} not found in document {document_id}"
            LOGGER.warning(msg)
            stats["failed"] += 1
            stats["errors"].append(msg)
            continue
            
        record = record_map[record_id]

        if line.get("stable_id") != record.stable_id:
            msg = f"Artifact line stable_id mismatch for record {record_id}"
            LOGGER.warning(msg)
            stats["failed"] += 1
            stats["errors"].append(msg)
            stats["failed_record_ids"].append(record_id)
            continue
        
        if line.get("source_hash") != record.source_hash:
            msg = f"Artifact line source_hash mismatch for record {record_id}"
            LOGGER.warning(msg)
            stats["failed"] += 1
            stats["errors"].append(msg)
            stats["failed_record_ids"].append(record_id)
            continue

        artifact_status = line.get("status")
        if artifact_status == "skipped":
            LOGGER.info("Skipping artifact line for record %s", record_id)
            stats["skipped"] += 1
            stats["skipped_record_ids"].append(record_id)
            continue
        if artifact_status != "completed":
            msg = f"Artifact line for record {record_id} has non-success status {artifact_status!r}"
            LOGGER.warning(msg)
            stats["failed"] += 1
            stats["errors"].append(msg)
            stats["failed_record_ids"].append(record_id)
            continue

        summary_text = line.get("summary_text")
        if not isinstance(summary_text, str) or not summary_text.strip():
            msg = f"Artifact line for record {record_id} has an empty summary"
            LOGGER.warning(msg)
            stats["failed"] += 1
            stats["errors"].append(msg)
            stats["failed_record_ids"].append(record_id)
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
            existing.summary_text = summary_text
            existing.summary_hash = summary_hash
            existing.summary_style = line.get("summary_style")
            existing.provider = line.get("provider")
            existing.model = line.get("model")
            existing.template_version = line.get("template_version")
            existing.status = line.get("status", "completed")
            existing.error_code = line.get("error_code")
            existing.usage_json = line.get("usage", {})
        else:
            new_summary = RecordSummary(
                document_id=document.id,
                record_id=record.id,
                stable_id=record.stable_id,
                summary_text=summary_text,
                summariser_name=summariser_name,
                summary_hash=summary_hash,
                source_hash=record.source_hash,
                summary_style=line.get("summary_style"),
                provider=line.get("provider"),
                model=line.get("model"),
                template_version=line.get("template_version"),
                status=line.get("status", "completed"),
                error_code=line.get("error_code"),
                usage_json=line.get("usage", {})
            )
            session.add(new_summary)
            
        stats["imported"] += 1
        stats["imported_record_ids"].append(record_id)
        
    session.commit()
    return stats
