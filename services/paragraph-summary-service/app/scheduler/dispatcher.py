import asyncio
import logging
from datetime import datetime, timezone

from app.config import settings
from app.records.schema import InputRecord, SummaryArtifactLine, SummaryRequest
from app.scheduler.token_packer import pack_batches
from app.providers.mock import MockProvider

LOGGER = logging.getLogger(__name__)

# In-memory storage for local demo
JOBS = {}

class JobState:
    def __init__(self, job_id: str, document_id: str, total_records: int):
        self.job_id = job_id
        self.document_id = document_id
        self.total_records = total_records
        self.completed_records = 0
        self.failed_records = 0
        self.status = "pending"
        self.artifact_lines: list[SummaryArtifactLine] = []
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.error = None
        self.stats = {
            "total_batches": 0,
            "completed_batches": 0,
            "failed_batches": 0,
            "lane_count": settings.summary_lane_count,
            "active_lanes": 0,
            "retry_count": 0,
        }

async def _process_batch(job: JobState, batch: list[InputRecord], provider, summary_style: str):
    max_retries = 2
    current_batch = batch
    
    for attempt in range(max_retries + 1):
        if not current_batch:
            break
            
        try:
            results = await provider.summarize_batch(job.document_id, current_batch, summary_style)
        except Exception as exc:
            LOGGER.error("Batch failed on attempt %s: %s", attempt, exc)
            results = []
            
        # Validation
        expected_records = {record.record_id: record for record in current_batch}
        expected_ids = set(expected_records)
        valid_results = []
        seen_ids = set()
        
        for res in results:
            # Reject unknown IDs
            if res.record_id not in expected_ids:
                LOGGER.warning("Provider returned unknown record_id: %s", res.record_id)
                continue

            if res.document_id != job.document_id:
                LOGGER.warning("Provider returned wrong document_id for record %s", res.record_id)
                continue

            if res.source_hash != expected_records[res.record_id].source_hash:
                LOGGER.warning("Provider returned wrong source_hash for record %s", res.record_id)
                continue
            
            # Reject duplicates
            if res.record_id in seen_ids:
                LOGGER.warning("Provider returned duplicate record_id: %s", res.record_id)
                continue
                
            if res.status not in {"completed", "skipped"}:
                LOGGER.warning("Provider returned non-success status for %s: %s", res.record_id, res.status)
                continue

            # Reject malformed completed summaries.
            if res.status == "completed" and not res.summary_text:
                LOGGER.warning("Provider returned empty summary text for %s", res.record_id)
                continue
                
            seen_ids.add(res.record_id)
            valid_results.append(res)
            
        job.artifact_lines.extend(valid_results)
        job.completed_records += len(valid_results)
        
        missing_ids = expected_ids - seen_ids
        
        # Retry missing
        current_batch = [r for r in current_batch if r.record_id in missing_ids]
        if not current_batch:
            break
            
        job.stats["retry_count"] += 1
        LOGGER.info("Retrying %s missing records in job %s", len(current_batch), job.job_id)
            
    # Exhausted retries, emit failed lines
    if current_batch:
        LOGGER.error("Exhausted retries for %s records in job %s", len(current_batch), job.job_id)
        _append_failed_records(job, current_batch, summary_style, "exhausted_retries")
    else:
        job.stats["completed_batches"] += 1


def _append_failed_records(
    job: JobState,
    records: list[InputRecord],
    summary_style: str,
    error_code: str,
) -> None:
    artifact_record_ids = {line.record_id for line in job.artifact_lines}
    failed_records = [record for record in records if record.record_id not in artifact_record_ids]
    if not failed_records:
        return

    job.failed_records += len(failed_records)
    job.stats["failed_batches"] += 1
    now_str = datetime.now(timezone.utc).isoformat()
    for record in failed_records:
        job.artifact_lines.append(
            SummaryArtifactLine(
                document_id=job.document_id,
                record_id=record.record_id,
                stable_id=record.stable_id,
                source_hash=record.source_hash,
                summary_text="",
                summary_style=summary_style,
                provider="error",
                model="error",
                template_version="error",
                status="failed",
                error_code=error_code,
                created_at=now_str,
            )
        )

async def _run_job_background(job: JobState, request: SummaryRequest):
    job.status = "running"
    
    # 1. Pack batches
    batches = pack_batches(
        request.records, 
        settings.summary_batch_target_tokens, 
        settings.summary_batch_hard_max_tokens
    )
    job.stats["total_batches"] = len(batches)
    
    # 2. Provider init. Only the deterministic mock provider is implemented.
    if settings.summary_service_provider != "mock":
        job.error = f"Unsupported summary provider: {settings.summary_service_provider}"
        for batch in batches:
            _append_failed_records(job, batch, request.summary_style, "unsupported_provider")
        job.status = "failed"
        return
    provider = MockProvider(settings.summary_service_model, settings.summary_template_version)

    # 3. Dispatch through quota lanes.
    from app.scheduler.lane import QuotaLane
    
    # We use a time_scale for tests/demos if configured, else 1.0 (real time)
    # The default setting in settings is real RPM. 
    # For demo mock purposes, we will use a small time scale if provider is mock to keep tests fast.
    time_scale = 0.001 if settings.summary_service_provider == "mock" else 1.0

    if settings.summary_lane_count < 1:
        job.error = "SUMMARY_LANE_COUNT must be at least 1"
        for batch in batches:
            _append_failed_records(job, batch, request.summary_style, "invalid_lane_count")
        job.status = "failed"
        return
    
    lanes = [QuotaLane(f"lane_{i}", settings.summary_lane_rpm, time_scale) for i in range(settings.summary_lane_count)]
    lane_queue = asyncio.Queue()
    for lane in lanes:
        lane_queue.put_nowait(lane)

    async def worker(batch):
        lane = await lane_queue.get()
        try:
            job.stats["active_lanes"] += 1
            await lane.wait_for_cooldown()
            await _process_batch(job, batch, provider, request.summary_style)
        finally:
            job.stats["active_lanes"] -= 1
            lane_queue.put_nowait(lane)

    results = await asyncio.gather(*(worker(batch) for batch in batches), return_exceptions=True)
    for batch, result in zip(batches, results, strict=True):
        if isinstance(result, BaseException):
            LOGGER.error(
                "Unexpected scheduler failure in job %s: %s",
                job.job_id,
                result,
                exc_info=(type(result), result, result.__traceback__),
            )
            job.error = str(result)
            _append_failed_records(job, batch, request.summary_style, "scheduler_error")

    processed_records = job.completed_records + job.failed_records
    job.status = "completed" if job.failed_records == 0 and processed_records == job.total_records else "failed"

def get_job(job_id: str) -> JobState | None:
    return JOBS.get(job_id)
