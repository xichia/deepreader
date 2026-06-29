"""In-memory batch dispatcher for paragraph summary jobs."""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime, timezone
import logging
import os
import re
from typing import Any

from app.config import settings
from app.providers.gemini import GeminiProvider, StructuredOutputParseError
from app.providers.mock import MockProvider
from app.records.schema import InputRecord, SummaryArtifactLine, SummaryRequest
from app.scheduler.lane import QuotaLane
from app.scheduler.token_packer import estimate_batch_input_tokens, pack_batches

LOGGER = logging.getLogger(__name__)

GEMINI_PROMPT_OVERHEAD_TOKENS = 256
MAX_RETRIES = 2

# In-memory storage for the local validation service.
JOBS: dict[str, "JobState"] = {}


class ProviderConfigurationError(ValueError):
    """Raised when an explicitly selected provider is not safe to run."""


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
        self.error: str | None = None
        self.stats: dict[str, Any] = {
            "total_batches": 0,
            "completed_batches": 0,
            "failed_batches": 0,
            "lane_count": settings.summary_lane_count,
            "active_lanes": 0,
            "retry_count": 0,
            "provider_calls_attempted": 0,
            "estimated_input_tokens": 0,
            "provider": settings.summary_service_provider,
            "model": settings.summary_service_model,
        }
        self._provider_call_lock = asyncio.Lock()

    async def claim_provider_call(self, maximum: int | None) -> bool:
        async with self._provider_call_lock:
            attempted = int(self.stats["provider_calls_attempted"])
            if maximum is not None and attempted >= maximum:
                return False
            self.stats["provider_calls_attempted"] = attempted + 1
            return True


def validate_provider_configuration() -> dict[str, str]:
    """Validate provider opt-in and return lane credentials keyed by env name."""

    provider = settings.summary_service_provider.strip().lower()
    if provider not in {"mock", "gemini"}:
        raise ProviderConfigurationError(f"Unsupported summary provider: {provider}")
    if settings.summary_lane_count < 1:
        raise ProviderConfigurationError("SUMMARY_LANE_COUNT must be at least 1")
    if settings.summary_lane_rpm < 1:
        raise ProviderConfigurationError("SUMMARY_LANE_RPM must be at least 1")
    if settings.summary_max_parallel_lanes < 1:
        raise ProviderConfigurationError("SUMMARY_MAX_PARALLEL_LANES must be at least 1")
    if settings.summary_batch_target_tokens < 1 or settings.summary_batch_hard_max_tokens < 1:
        raise ProviderConfigurationError("Summary batch token limits must be positive")
    if settings.summary_batch_target_tokens > settings.summary_batch_hard_max_tokens:
        raise ProviderConfigurationError(
            "SUMMARY_BATCH_TARGET_TOKENS cannot exceed SUMMARY_BATCH_HARD_MAX_TOKENS"
        )

    if provider == "mock":
        return {}

    if not settings.summary_service_enable_provider_calls:
        raise ProviderConfigurationError(
            "Gemini provider calls are disabled; set SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true"
        )
    if settings.summary_batch_reserved_output_tokens < 0:
        raise ProviderConfigurationError("SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS cannot be negative")
    if (
        settings.summary_batch_reserved_output_tokens
        + GEMINI_PROMPT_OVERHEAD_TOKENS
        >= settings.summary_batch_hard_max_tokens
    ):
        raise ProviderConfigurationError(
            "Reserved output and prompt overhead leave no Gemini input token capacity"
        )
    if settings.summary_max_provider_calls_per_job < 1:
        raise ProviderConfigurationError("SUMMARY_MAX_PROVIDER_CALLS_PER_JOB must be at least 1")
    if settings.summary_max_input_tokens_per_job < 1:
        raise ProviderConfigurationError("SUMMARY_MAX_INPUT_TOKENS_PER_JOB must be at least 1")

    credentials: dict[str, str] = {}
    missing_names: list[str] = []
    for env_name in settings.lane_credential_env_names():
        value = os.getenv(env_name, "").strip()
        if value:
            credentials[env_name] = value
        else:
            missing_names.append(env_name)

    if missing_names:
        missing = ", ".join(missing_names)
        raise ProviderConfigurationError(
            f"Gemini requires one configured key per enabled lane; missing: {missing}"
        )
    return credentials


def _build_lanes_and_providers(
    provider_name: str,
    credentials: dict[str, str],
) -> tuple[list[QuotaLane], dict[str, Any]]:
    time_scale = 0.001 if provider_name == "mock" else 1.0
    lanes: list[QuotaLane] = []
    providers: dict[str, Any] = {}

    for lane_number in range(1, settings.summary_lane_count + 1):
        lane_id = f"lane_{lane_number:02d}"
        env_name = f"GEMINI_API_KEY_LANE_{lane_number:02d}" if provider_name == "gemini" else None
        api_key = credentials.get(env_name) if env_name else None
        lane = QuotaLane(
            lane_id,
            settings.summary_lane_rpm,
            time_scale,
            provider=provider_name,
            model=settings.summary_service_model,
            credential_env_name=env_name,
            api_key=api_key,
        )
        lanes.append(lane)
        if provider_name == "gemini":
            providers[lane_id] = GeminiProvider(
                model_name=settings.summary_service_model,
                template_version=settings.summary_template_version,
                api_key=api_key or "",
                lane_id=lane_id,
            )
        else:
            providers[lane_id] = MockProvider(
                settings.summary_service_model,
                settings.summary_template_version,
            )

    return lanes, providers


def _is_reasonable_one_sentence(summary_text: str) -> bool:
    text = summary_text.strip()
    if not text or "\n" in text or re.match(r"^(?:[-*#]|\d+[.)]\s)", text):
        return False
    sentence_starts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", text)
    return len([part for part in sentence_starts if part.strip()]) == 1


def _validate_results(
    job: JobState,
    current_batch: list[InputRecord],
    results: Any,
) -> tuple[list[SummaryArtifactLine], list[InputRecord], dict[str, str]]:
    expected_records = {record.record_id: record for record in current_batch}
    expected_ids = set(expected_records)
    errors: dict[str, str] = {}

    if not isinstance(results, list) or any(not isinstance(item, SummaryArtifactLine) for item in results):
        return [], current_batch, {record.record_id: "provider_exception" for record in current_batch}

    result_ids = [result.record_id for result in results]
    unknown_ids = set(result_ids) - expected_ids
    wrong_documents = [result for result in results if result.document_id != job.document_id]
    if unknown_ids or wrong_documents:
        if unknown_ids:
            LOGGER.warning("Provider returned %s unknown record IDs for job %s", len(unknown_ids), job.job_id)
        if wrong_documents:
            LOGGER.warning("Provider returned a wrong document ID for job %s", job.job_id)
        return [], current_batch, {record.record_id: "unknown_record_id" for record in current_batch}

    counts = Counter(result_ids)
    valid_results: list[SummaryArtifactLine] = []
    retry_records: list[InputRecord] = []
    results_by_id = {result.record_id: result for result in results}

    for record_id, record in expected_records.items():
        if counts[record_id] == 0:
            errors[record_id] = "missing_record"
            retry_records.append(record)
            continue
        if counts[record_id] > 1:
            errors[record_id] = "duplicate_record_id"
            retry_records.append(record)
            continue

        result = results_by_id[record_id]
        if result.source_hash != record.source_hash:
            errors[record_id] = "source_hash_mismatch"
            retry_records.append(record)
            continue
        if result.stable_id != record.stable_id:
            errors[record_id] = "unknown_record_id"
            retry_records.append(record)
            continue
        if result.status not in {"completed", "skipped", "failed"}:
            errors[record_id] = "invalid_status"
            retry_records.append(record)
            continue
        if result.status == "failed":
            errors[record_id] = result.error_code or "provider_exception"
            retry_records.append(record)
            continue
        if result.status == "completed" and not result.summary_text.strip():
            errors[record_id] = "empty_summary"
            retry_records.append(record)
            continue
        if (
            result.status == "completed"
            and result.provider == "gemini"
            and not _is_reasonable_one_sentence(result.summary_text)
        ):
            errors[record_id] = "empty_summary"
            retry_records.append(record)
            continue
        valid_results.append(result)

    return valid_results, retry_records, errors


async def _process_batch(
    job: JobState,
    batch: list[InputRecord],
    provider: Any,
    summary_style: str,
    max_provider_calls: int | None = None,
    lane: QuotaLane | None = None,
) -> None:
    current_batch = batch
    last_errors: dict[str, str] = {}

    for attempt in range(MAX_RETRIES + 1):
        if not current_batch:
            break
        if not await job.claim_provider_call(max_provider_calls):
            last_errors.update(
                {record.record_id: "max_provider_calls_exceeded" for record in current_batch}
            )
            break
        if lane is not None:
            await lane.wait_for_cooldown()

        try:
            results = await provider.summarize_batch(job.document_id, current_batch, summary_style)
        except Exception as exc:
            error_code = (
                "structured_output_parse_error"
                if isinstance(exc, StructuredOutputParseError)
                else "provider_exception"
            )
            LOGGER.error(
                "Provider batch attempt %s failed for job %s (%s)",
                attempt + 1,
                job.job_id,
                type(exc).__name__,
            )
            last_errors.update({record.record_id: error_code for record in current_batch})
            valid_results: list[SummaryArtifactLine] = []
            retry_records = current_batch
            validation_errors: dict[str, str] = {}
        else:
            valid_results, retry_records, validation_errors = _validate_results(
                job, current_batch, results
            )
        job.artifact_lines.extend(valid_results)
        job.completed_records += len(valid_results)
        last_errors.update(validation_errors)
        current_batch = retry_records

        if current_batch and attempt < MAX_RETRIES:
            job.stats["retry_count"] += 1
            LOGGER.info("Retrying %s records in job %s", len(current_batch), job.job_id)

    if current_batch:
        LOGGER.error("Exhausted retries for %s records in job %s", len(current_batch), job.job_id)
        _append_failed_records(
            job,
            current_batch,
            summary_style,
            error_codes=last_errors,
        )
    else:
        job.stats["completed_batches"] += 1


def _append_failed_records(
    job: JobState,
    records: list[InputRecord],
    summary_style: str,
    error_code: str = "exhausted_retries",
    *,
    error_codes: dict[str, str] | None = None,
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
                provider=str(job.stats["provider"]),
                model=str(job.stats["model"]),
                template_version=settings.summary_template_version,
                status="failed",
                error_code=(error_codes or {}).get(record.record_id, error_code),
                created_at=now_str,
            )
        )


def _fail_batches(
    job: JobState,
    batches: list[list[InputRecord]],
    summary_style: str,
    error_code: str,
    message: str,
) -> None:
    job.error = message
    for batch in batches:
        _append_failed_records(job, batch, summary_style, error_code)
    job.status = "failed"


async def _run_job_background(job: JobState, request: SummaryRequest) -> None:
    job.status = "running"
    provider_name = settings.summary_service_provider.strip().lower()
    job.stats["provider"] = provider_name
    job.stats["model"] = settings.summary_service_model

    try:
        credentials = validate_provider_configuration()
    except ProviderConfigurationError as exc:
        job.stats["total_batches"] = 1
        _fail_batches(
            job,
            [request.records],
            request.summary_style,
            "provider_exception",
            str(exc),
        )
        return

    try:
        if provider_name == "gemini":
            batches = pack_batches(
                request.records,
                settings.summary_batch_target_tokens,
                settings.summary_batch_hard_max_tokens,
                wrapper_overhead_tokens=GEMINI_PROMPT_OVERHEAD_TOKENS,
                reserved_output_tokens=settings.summary_batch_reserved_output_tokens,
                include_record_overhead=True,
            )
        else:
            batches = pack_batches(
                request.records,
                settings.summary_batch_target_tokens,
                settings.summary_batch_hard_max_tokens,
            )
    except ValueError as exc:
        job.stats["total_batches"] = 1
        _fail_batches(
            job,
            [request.records],
            request.summary_style,
            "max_input_tokens_exceeded",
            str(exc),
        )
        return

    job.stats["total_batches"] = len(batches)

    if provider_name == "gemini":
        estimated_input_tokens = sum(
            estimate_batch_input_tokens(
                batch,
                wrapper_overhead_tokens=GEMINI_PROMPT_OVERHEAD_TOKENS,
            )
            for batch in batches
        )
        job.stats["estimated_input_tokens"] = estimated_input_tokens
        usable_hard_max = (
            settings.summary_batch_hard_max_tokens
            - settings.summary_batch_reserved_output_tokens
        )
        oversized_batch = any(
            estimate_batch_input_tokens(
                batch,
                wrapper_overhead_tokens=GEMINI_PROMPT_OVERHEAD_TOKENS,
            )
            > usable_hard_max
            for batch in batches
        )
        if oversized_batch or estimated_input_tokens > settings.summary_max_input_tokens_per_job:
            _fail_batches(
                job,
                batches,
                request.summary_style,
                "max_input_tokens_exceeded",
                "Estimated Gemini input exceeds configured token safety caps",
            )
            return
        if len(batches) > settings.summary_max_provider_calls_per_job:
            _fail_batches(
                job,
                batches,
                request.summary_style,
                "max_provider_calls_exceeded",
                "Gemini job requires more provider calls than the configured safety cap",
            )
            return

    try:
        lanes, providers = _build_lanes_and_providers(provider_name, credentials)
    except Exception as exc:
        LOGGER.error("Provider initialization failed (%s)", type(exc).__name__)
        _fail_batches(
            job,
            batches,
            request.summary_style,
            "provider_exception",
            f"{provider_name} provider initialization failed",
        )
        return

    job.stats["lane_count"] = len(lanes)
    lane_queue: asyncio.Queue[QuotaLane] = asyncio.Queue()
    for lane in lanes:
        lane_queue.put_nowait(lane)
    parallelism = min(settings.summary_max_parallel_lanes, len(lanes))
    semaphore = asyncio.Semaphore(parallelism)
    maximum_calls = (
        settings.summary_max_provider_calls_per_job if provider_name == "gemini" else None
    )

    async def worker(batch: list[InputRecord]) -> None:
        async with semaphore:
            lane = await lane_queue.get()
            try:
                job.stats["active_lanes"] += 1
                await _process_batch(
                    job,
                    batch,
                    providers[lane.lane_id],
                    request.summary_style,
                    max_provider_calls=maximum_calls,
                    lane=lane,
                )
            finally:
                job.stats["active_lanes"] -= 1
                lane_queue.put_nowait(lane)

    results = await asyncio.gather(*(worker(batch) for batch in batches), return_exceptions=True)
    for batch, result in zip(batches, results, strict=True):
        if isinstance(result, BaseException):
            LOGGER.error(
                "Unexpected scheduler failure in job %s (%s)",
                job.job_id,
                type(result).__name__,
            )
            job.error = "Unexpected scheduler failure"
            _append_failed_records(job, batch, request.summary_style, "provider_exception")

    processed_records = job.completed_records + job.failed_records
    job.status = (
        "completed"
        if job.failed_records == 0 and processed_records == job.total_records
        else "failed"
    )
    if job.status == "failed" and job.error is None:
        job.error = "One or more provider results failed; inspect artifact error_code values"


def get_job(job_id: str) -> JobState | None:
    return JOBS.get(job_id)
