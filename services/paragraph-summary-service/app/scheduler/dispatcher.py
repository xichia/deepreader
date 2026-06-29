"""In-memory batch dispatcher for paragraph summary jobs."""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
import os
import re
from typing import Any

from app.config import settings
from app.providers.gemini import (
    GeminiProvider,
    ResponseParseError,
    SchemaValidationError,
)
from app.providers.mock import MockProvider
from app.records.schema import InputRecord, SummaryArtifactLine, SummaryRequest
from app.scheduler.lane import QuotaLane
from app.scheduler.token_packer import estimate_batch_input_tokens, pack_batches

LOGGER = logging.getLogger(__name__)

GEMINI_PROMPT_OVERHEAD_TOKENS = 256
MAX_RETRIES = 2
MAX_DIAGNOSTIC_CHARS = 500
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|authorization|credential|password|secret|token|x-goog-api-key)"
    r"\s*[:=]\s*(?:bearer\s+)?[^\s,;]+"
)
_GOOGLE_API_KEY_RE = re.compile(r"AIza[0-9A-Za-z_-]{16,}")
_GEMINI_LANE_KEY_RE = re.compile(r"^GEMINI_API_KEY_LANE_(\d+)$")

# In-memory storage for the local validation service.
JOBS: dict[str, "JobState"] = {}


class ProviderConfigurationError(ValueError):
    """Raised when an explicitly selected provider is not safe to run."""


@dataclass(frozen=True)
class FailureDetail:
    error_code: str
    message: str
    lane_id: str | None = None
    provider_alias: str | None = None
    attempt_count: int | None = None
    retry_count: int | None = None
    usage: dict[str, Any] = field(default_factory=dict)


def _sanitize_diagnostic_text(value: object, *, secret_values: tuple[str, ...] = ()) -> str:
    """Return compact provider diagnostics without credentials or request bodies."""

    text = re.sub(r"\s+", " ", str(value)).strip()
    for secret in secret_values:
        if secret:
            text = text.replace(secret, "[redacted]")
    text = _GOOGLE_API_KEY_RE.sub("[redacted]", text)
    text = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=[redacted]", text)
    text = re.sub(
        r"(?i)\b(input records|prompt|request body|contents)\s*[:=].*$",
        lambda match: f"{match.group(1)}=[omitted]",
        text,
    )
    if not text:
        return "Provider request failed without an error message"
    if len(text) > MAX_DIAGNOSTIC_CHARS:
        return f"{text[: MAX_DIAGNOSTIC_CHARS - 3]}..."
    return text


def _provider_error_code(exc: Exception) -> str:
    if isinstance(exc, ResponseParseError):
        return "response_parse_failed"
    if isinstance(exc, SchemaValidationError):
        return "schema_validation_failed"
    if isinstance(exc, TimeoutError) or "timeout" in type(exc).__name__.lower():
        return "provider_timeout"

    status_code = getattr(exc, "status_code", None)
    if status_code is None:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code is None:
        status_code = getattr(exc, "code", None)
    error_text = f"{type(exc).__name__} {exc}".lower()
    if status_code == 429 or any(
        term in error_text
        for term in ("rate limit", "resourceexhausted", "resource_exhausted", "quota")
    ):
        return "provider_rate_limited"
    if status_code in {401, 403} or any(
        term in error_text
        for term in (
            "unauthenticated",
            "permissiondenied",
            "permission_denied",
            "invalid api key",
            "api key not valid",
        )
    ):
        return "provider_auth_error"
    if status_code == 404 or ("model" in error_text and "not found" in error_text):
        return "provider_model_not_found"
    return "provider_exception"


def _exception_usage(exc: Exception) -> dict[str, int]:
    usage_source = getattr(exc, "usage", None) or getattr(exc, "usage_metadata", None)
    if usage_source is None:
        return {}

    field_names = {
        "prompt_tokens": ("prompt_tokens", "prompt_token_count"),
        "completion_tokens": ("completion_tokens", "candidates_token_count"),
        "total_tokens": ("total_tokens", "total_token_count"),
    }
    usage: dict[str, int] = {}
    for output_name, candidates in field_names.items():
        for candidate in candidates:
            value = (
                usage_source.get(candidate)
                if isinstance(usage_source, dict)
                else getattr(usage_source, candidate, None)
            )
            if isinstance(value, int):
                usage[output_name] = value
                break
    return usage


def _exception_failure(
    exc: Exception,
    *,
    lane: QuotaLane | None,
    attempt_count: int,
) -> FailureDetail:
    secret_values = (lane.api_key,) if lane is not None and lane.api_key else ()
    message = _sanitize_diagnostic_text(
        f"{type(exc).__name__}: {exc}",
        secret_values=secret_values,
    )
    return FailureDetail(
        error_code=_provider_error_code(exc),
        message=message,
        lane_id=lane.lane_id if lane is not None else None,
        provider_alias=lane.provider_alias if lane is not None else None,
        attempt_count=attempt_count,
        retry_count=max(attempt_count - 1, 0),
        usage=_exception_usage(exc),
    )


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
        self.updated_at = self.created_at
        self.error: str | None = None
        self.stats: dict[str, Any] = {
            "total_batches": 0,
            "completed_batches": 0,
            "failed_batches": 0,
            "configured_lane_count": settings.summary_lane_count,
            "lane_count": settings.summary_lane_count,
            "active_lanes": 0,
            "scheduler_parallelism": 0,
            "provider_identity_count": 0,
            "configured_provider_identity_count": 0,
            "provider_aliases": [],
            "active_provider_aliases": [],
            "active_batches_by_alias": {},
            "provider_calls_by_alias": {},
            "rate_limit_count": 0,
            "rate_limit_count_by_alias": {},
            "cooldown_aliases": [],
            "cooldown_count": 0,
            "retry_count": 0,
            "provider_calls_attempted": 0,
            "estimated_input_tokens": 0,
            "batch_max_records": settings.summary_batch_max_records,
            "provider": settings.summary_service_provider,
            "model": settings.summary_service_model,
            "effective_config": settings.safe_summary(),
        }
        self._provider_call_lock = asyncio.Lock()

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()

    async def claim_provider_call(
        self,
        maximum: int | None,
        provider_alias: str | None = None,
    ) -> bool:
        async with self._provider_call_lock:
            attempted = int(self.stats["provider_calls_attempted"])
            if maximum is not None and attempted >= maximum:
                return False
            self.stats["provider_calls_attempted"] = attempted + 1
            if provider_alias:
                calls_by_alias = self.stats["provider_calls_by_alias"]
                calls_by_alias[provider_alias] = calls_by_alias.get(provider_alias, 0) + 1
            self.touch()
            return True

    def provider_batch_started(self, provider_alias: str) -> None:
        active = self.stats["active_batches_by_alias"]
        active[provider_alias] = active.get(provider_alias, 0) + 1
        self.stats["active_lanes"] = sum(1 for count in active.values() if count > 0)
        self.stats["active_provider_aliases"] = sorted(
            alias for alias, count in active.items() if count > 0
        )
        self.touch()

    def provider_batch_finished(self, provider_alias: str) -> None:
        active = self.stats["active_batches_by_alias"]
        active[provider_alias] = max(0, active.get(provider_alias, 0) - 1)
        self.stats["active_lanes"] = sum(1 for count in active.values() if count > 0)
        self.stats["active_provider_aliases"] = sorted(
            alias for alias, count in active.items() if count > 0
        )
        self.touch()

    def record_rate_limit(self, provider_alias: str, *, cooling_down: bool) -> None:
        counts = self.stats["rate_limit_count_by_alias"]
        counts[provider_alias] = counts.get(provider_alias, 0) + 1
        self.stats["rate_limit_count"] = int(self.stats["rate_limit_count"]) + 1
        self.set_provider_cooldown(provider_alias, cooling_down)

    def set_provider_cooldown(self, provider_alias: str, cooling_down: bool) -> None:
        aliases = set(self.stats["cooldown_aliases"])
        if cooling_down:
            aliases.add(provider_alias)
        else:
            aliases.discard(provider_alias)
        self.stats["cooldown_aliases"] = sorted(aliases)
        self.stats["cooldown_count"] = len(aliases)
        self.touch()


def _configured_gemini_credentials() -> dict[str, str]:
    """Load unique Gemini identities without ever deriving aliases from key values."""

    candidates: list[tuple[str, str]] = []
    numbered_names = sorted(
        (
            (int(match.group(1)), name)
            for name in os.environ
            if (match := _GEMINI_LANE_KEY_RE.match(name)) is not None
            and int(match.group(1)) <= settings.summary_lane_count
        ),
        key=lambda item: item[0],
    )
    for _, env_name in numbered_names:
        value = os.getenv(env_name, "").strip()
        if value:
            candidates.append((env_name, value))

    pooled_value = os.getenv("GEMINI_API_KEYS", "")
    for index, value in enumerate(re.split(r"[,;\n]", pooled_value), start=1):
        if value.strip():
            candidates.append((f"GEMINI_API_KEYS[{index}]", value.strip()))

    single_value = os.getenv("GEMINI_API_KEY", "").strip()
    if single_value:
        candidates.append(("GEMINI_API_KEY", single_value))

    credentials: dict[str, str] = {}
    seen_values: set[str] = set()
    for source_name, value in candidates:
        if value in seen_values:
            continue
        credentials[source_name] = value
        seen_values.add(value)
        if len(credentials) >= settings.summary_lane_count:
            break
    return credentials


def validate_provider_configuration() -> dict[str, str]:
    """Validate provider opt-in and return unique credentials keyed by safe source name."""

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
    if settings.summary_batch_max_records < 1:
        raise ProviderConfigurationError("SUMMARY_BATCH_MAX_RECORDS must be at least 1")
    if settings.summary_provider_rate_limit_cooldown_seconds < 0:
        raise ProviderConfigurationError(
            "SUMMARY_PROVIDER_RATE_LIMIT_COOLDOWN_SECONDS cannot be negative"
        )
    if settings.summary_retry_backoff_base_seconds < 0:
        raise ProviderConfigurationError("SUMMARY_RETRY_BACKOFF_BASE_SECONDS cannot be negative")

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
    if settings.summary_max_input_tokens_per_job < 0:
        raise ProviderConfigurationError("SUMMARY_MAX_INPUT_TOKENS_PER_JOB cannot be negative")

    credentials = _configured_gemini_credentials()
    if not credentials:
        raise ProviderConfigurationError(
            "Gemini requires at least one credential; configure GEMINI_API_KEY_LANE_01, "
            "GEMINI_API_KEYS, or GEMINI_API_KEY"
        )
    return credentials


def _build_lanes_and_providers(
    provider_name: str,
    credentials: dict[str, str],
) -> tuple[list[QuotaLane], dict[str, Any]]:
    time_scale = 0.001 if provider_name == "mock" else 1.0
    lanes: list[QuotaLane] = []
    providers: dict[str, Any] = {}

    identity_items: list[tuple[str | None, str | None]]
    if provider_name == "gemini":
        identity_items = list(credentials.items())[: settings.summary_lane_count]
    else:
        identity_items = [(None, None)] * settings.summary_lane_count

    for lane_number, (env_name, api_key) in enumerate(identity_items, start=1):
        lane_id = f"lane_{lane_number:02d}"
        provider_alias = f"{provider_name}_{lane_number:02d}"
        lane = QuotaLane(
            lane_id,
            settings.summary_lane_rpm,
            time_scale,
            provider=provider_name,
            model=settings.summary_service_model,
            credential_env_name=env_name,
            api_key=api_key,
            provider_alias=provider_alias,
            rate_limit_cooldown_seconds=(
                settings.summary_provider_rate_limit_cooldown_seconds
            ),
            retry_backoff_base_seconds=settings.summary_retry_backoff_base_seconds,
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
    *,
    lane: QuotaLane | None = None,
    attempt_count: int | None = None,
) -> tuple[list[SummaryArtifactLine], list[InputRecord], dict[str, FailureDetail]]:
    expected_records = {record.record_id: record for record in current_batch}
    expected_ids = set(expected_records)
    errors: dict[str, FailureDetail] = {}

    def failure(error_code: str, message: str) -> FailureDetail:
        return FailureDetail(
            error_code=error_code,
            message=message,
            lane_id=lane.lane_id if lane is not None else None,
            provider_alias=lane.provider_alias if lane is not None else None,
            attempt_count=attempt_count,
            retry_count=max((attempt_count or 1) - 1, 0),
        )

    if not isinstance(results, list) or any(not isinstance(item, SummaryArtifactLine) for item in results):
        detail = failure("schema_validation_failed", "Provider returned an invalid result collection")
        return [], current_batch, {record.record_id: detail for record in current_batch}

    result_ids = [result.record_id for result in results]
    unknown_ids = set(result_ids) - expected_ids
    wrong_documents = [result for result in results if result.document_id != job.document_id]
    if unknown_ids or wrong_documents:
        if unknown_ids:
            LOGGER.warning("Provider returned %s unknown record IDs for job %s", len(unknown_ids), job.job_id)
        if wrong_documents:
            LOGGER.warning("Provider returned a wrong document ID for job %s", job.job_id)
        detail = failure("unknown_record_id", "Provider returned unknown record or document identifiers")
        return [], current_batch, {record.record_id: detail for record in current_batch}

    counts = Counter(result_ids)
    valid_results: list[SummaryArtifactLine] = []
    retry_records: list[InputRecord] = []
    results_by_id = {result.record_id: result for result in results}

    for record_id, record in expected_records.items():
        if counts[record_id] == 0:
            errors[record_id] = failure("missing_record", "Provider response omitted this record")
            retry_records.append(record)
            continue
        if counts[record_id] > 1:
            errors[record_id] = failure("duplicate_record_id", "Provider returned this record more than once")
            retry_records.append(record)
            continue

        result = results_by_id[record_id]
        if result.source_hash != record.source_hash:
            errors[record_id] = failure("source_hash_mismatch", "Provider returned a mismatched source hash")
            retry_records.append(record)
            continue
        if result.stable_id != record.stable_id:
            errors[record_id] = failure("unknown_record_id", "Provider returned a mismatched stable ID")
            retry_records.append(record)
            continue
        if result.status not in {"completed", "skipped", "failed"}:
            errors[record_id] = failure("schema_validation_failed", "Provider returned an invalid result status")
            retry_records.append(record)
            continue
        if result.status == "failed":
            result_message = result.message or result.error or "Provider returned a failed result"
            errors[record_id] = FailureDetail(
                error_code=result.error_code or "provider_exception",
                message=_sanitize_diagnostic_text(
                    result_message,
                    secret_values=(
                        (lane.api_key,)
                        if lane is not None and lane.api_key
                        else ()
                    ),
                ),
                lane_id=result.lane_id or (lane.lane_id if lane is not None else None),
                provider_alias=(
                    result.provider_alias
                    or (lane.provider_alias if lane is not None else None)
                ),
                attempt_count=result.attempt_count or attempt_count,
                retry_count=(
                    result.retry_count
                    if result.retry_count is not None
                    else max((attempt_count or 1) - 1, 0)
                ),
                usage=result.usage,
            )
            retry_records.append(record)
            continue
        if result.status == "completed" and not result.summary_text.strip():
            errors[record_id] = failure("schema_validation_failed", "Provider returned an empty summary")
            retry_records.append(record)
            continue
        if (
            result.status == "completed"
            and result.provider == "gemini"
            and not _is_reasonable_one_sentence(result.summary_text)
        ):
            errors[record_id] = failure(
                "schema_validation_failed",
                "Provider summary did not satisfy the one-sentence schema",
            )
            retry_records.append(record)
            continue
        if lane is not None:
            result.lane_id = result.lane_id or lane.lane_id
            result.provider_alias = result.provider_alias or lane.provider_alias
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
    last_failures: dict[str, FailureDetail] = {}

    for attempt in range(MAX_RETRIES + 1):
        if not current_batch:
            break
        provider_alias = lane.provider_alias if lane is not None else None
        if not await job.claim_provider_call(max_provider_calls, provider_alias):
            detail = FailureDetail(
                error_code="max_provider_calls_exceeded",
                message="Configured provider call limit was exhausted before this batch could run",
                lane_id=lane.lane_id if lane is not None else None,
                provider_alias=provider_alias,
                attempt_count=attempt,
                retry_count=max(attempt - 1, 0),
            )
            last_failures.update({record.record_id: detail for record in current_batch})
            break

        try:
            if lane is not None:
                if lane.is_rate_limit_cooling_down():
                    job.set_provider_cooldown(lane.provider_alias, True)
                async with lane.provider_call_slot():
                    await lane.wait_for_cooldown()
                    job.set_provider_cooldown(lane.provider_alias, False)
                    LOGGER.info(
                        "Provider call job_id=%s lane_id=%s provider_alias=%s model=%s "
                        "batch_records=%s input_tokens_est=%s attempt=%s",
                        job.job_id,
                        lane.lane_id,
                        lane.provider_alias,
                        lane.model,
                        len(current_batch),
                        estimate_batch_input_tokens(
                            current_batch,
                            wrapper_overhead_tokens=(
                                GEMINI_PROMPT_OVERHEAD_TOKENS
                                if lane.provider == "gemini"
                                else 0
                            ),
                        ),
                        attempt + 1,
                    )
                    results = await provider.summarize_batch(
                        job.document_id,
                        current_batch,
                        summary_style,
                    )
            else:
                results = await provider.summarize_batch(
                    job.document_id,
                    current_batch,
                    summary_style,
                )
        except Exception as exc:
            detail = _exception_failure(exc, lane=lane, attempt_count=attempt + 1)
            if lane is not None and detail.error_code == "provider_rate_limited":
                delay = lane.defer_after_rate_limit(attempt + 1)
                job.record_rate_limit(lane.provider_alias, cooling_down=True)
                LOGGER.warning(
                    "Provider rate limited lane_id=%s provider_alias=%s model=%s "
                    "attempt=%s cooldown_seconds=%.2f",
                    lane.lane_id,
                    lane.provider_alias,
                    lane.model,
                    attempt + 1,
                    delay,
                )
            else:
                if lane is not None and attempt < MAX_RETRIES:
                    lane.defer_before_retry(attempt + 1)
                LOGGER.error(
                    "Provider batch attempt %s failed for job %s "
                    "lane_id=%s provider_alias=%s (%s, code=%s)",
                    attempt + 1,
                    job.job_id,
                    lane.lane_id if lane is not None else None,
                    provider_alias,
                    type(exc).__name__,
                    detail.error_code,
                )
            last_failures.update({record.record_id: detail for record in current_batch})
            valid_results: list[SummaryArtifactLine] = []
            retry_records = current_batch
            validation_errors: dict[str, FailureDetail] = {}
        else:
            valid_results, retry_records, validation_errors = _validate_results(
                job,
                current_batch,
                results,
                lane=lane,
                attempt_count=attempt + 1,
            )
            if lane is not None and retry_records:
                rate_limited = any(
                    failure.error_code == "provider_rate_limited"
                    for failure in validation_errors.values()
                )
                if rate_limited:
                    delay = lane.defer_after_rate_limit(attempt + 1)
                    job.record_rate_limit(lane.provider_alias, cooling_down=True)
                    LOGGER.warning(
                        "Provider result rate limited lane_id=%s provider_alias=%s "
                        "model=%s attempt=%s cooldown_seconds=%.2f",
                        lane.lane_id,
                        lane.provider_alias,
                        lane.model,
                        attempt + 1,
                        delay,
                    )
                elif attempt < MAX_RETRIES:
                    lane.defer_before_retry(attempt + 1)
        job.artifact_lines.extend(valid_results)
        job.completed_records += len(valid_results)
        last_failures.update(validation_errors)
        current_batch = retry_records
        job.touch()

        if current_batch and attempt < MAX_RETRIES:
            job.stats["retry_count"] += 1
            job.touch()
            LOGGER.info(
                "Retrying %s records in job %s provider_alias=%s",
                len(current_batch),
                job.job_id,
                provider_alias,
            )

    if current_batch:
        LOGGER.error("Exhausted retries for %s records in job %s", len(current_batch), job.job_id)
        _append_failed_records(
            job,
            current_batch,
            summary_style,
            failures=last_failures,
        )
    else:
        job.stats["completed_batches"] += 1
        job.touch()


def _append_failed_records(
    job: JobState,
    records: list[InputRecord],
    summary_style: str,
    error_code: str = "exhausted_retries",
    *,
    message: str | None = None,
    failures: dict[str, FailureDetail] | None = None,
) -> None:
    artifact_record_ids = {line.record_id for line in job.artifact_lines}
    failed_records = [record for record in records if record.record_id not in artifact_record_ids]
    if not failed_records:
        return

    job.failed_records += len(failed_records)
    job.stats["failed_batches"] += 1
    now_str = datetime.now(timezone.utc).isoformat()
    for record in failed_records:
        failure = (failures or {}).get(record.record_id) or FailureDetail(
            error_code=error_code,
            message=message or error_code.replace("_", " "),
        )
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
                error_code=failure.error_code,
                message=failure.message,
                lane_id=failure.lane_id,
                provider_alias=failure.provider_alias,
                attempt_count=failure.attempt_count,
                retry_count=failure.retry_count,
                usage=failure.usage,
                created_at=now_str,
            )
        )
    job.touch()


def _fail_batches(
    job: JobState,
    batches: list[list[InputRecord]],
    summary_style: str,
    error_code: str,
    message: str,
) -> None:
    job.error = message
    for batch in batches:
        _append_failed_records(job, batch, summary_style, error_code, message=message)
    job.status = "failed"
    job.touch()


async def _run_job_background(job: JobState, request: SummaryRequest) -> None:
    job.status = "running"
    job.touch()
    provider_name = settings.summary_service_provider.strip().lower()
    job.stats["provider"] = provider_name
    job.stats["model"] = settings.summary_service_model
    job.stats["configured_lane_count"] = settings.summary_lane_count
    job.stats["batch_max_records"] = settings.summary_batch_max_records
    job.stats["effective_config"] = settings.safe_summary()

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
                max_records=settings.summary_batch_max_records,
            )
        else:
            batches = pack_batches(
                request.records,
                settings.summary_batch_target_tokens,
                settings.summary_batch_hard_max_tokens,
                max_records=settings.summary_batch_max_records,
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
        if oversized_batch or (
            settings.summary_max_input_tokens_per_job > 0
            and estimated_input_tokens > settings.summary_max_input_tokens_per_job
        ):
            _fail_batches(
                job,
                batches,
                request.summary_style,
                "max_input_tokens_exceeded",
                "Estimated Gemini input exceeds configured token safety caps",
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
    provider_aliases = [lane.provider_alias for lane in lanes]
    job.stats["provider_identity_count"] = len(lanes)
    job.stats["configured_provider_identity_count"] = len(lanes)
    job.stats["provider_aliases"] = provider_aliases
    job.stats["active_batches_by_alias"] = {alias: 0 for alias in provider_aliases}
    job.stats["provider_calls_by_alias"] = {alias: 0 for alias in provider_aliases}
    job.stats["rate_limit_count_by_alias"] = {alias: 0 for alias in provider_aliases}
    lane_queue: asyncio.Queue[QuotaLane] = asyncio.Queue()
    for lane in lanes:
        lane_queue.put_nowait(lane)
    parallelism = min(settings.summary_max_parallel_lanes, len(lanes))
    job.stats["scheduler_parallelism"] = parallelism
    LOGGER.info(
        "Summary scheduler job_id=%s provider=%s configured_lanes=%s "
        "provider_identities=%s parallelism=%s provider_aliases=%s "
        "total_batches=%s batch_max_records=%s",
        job.job_id,
        provider_name,
        settings.summary_lane_count,
        len(lanes),
        parallelism,
        ",".join(provider_aliases),
        len(batches),
        settings.summary_batch_max_records,
    )
    semaphore = asyncio.Semaphore(parallelism)
    maximum_calls = (
        settings.summary_max_provider_calls_per_job if provider_name == "gemini" else None
    )

    async def worker(batch: list[InputRecord]) -> None:
        async with semaphore:
            lane = await lane_queue.get()
            try:
                job.provider_batch_started(lane.provider_alias)
                await _process_batch(
                    job,
                    batch,
                    providers[lane.lane_id],
                    request.summary_style,
                    max_provider_calls=maximum_calls,
                    lane=lane,
                )
            finally:
                job.provider_batch_finished(lane.provider_alias)
                lane_queue.put_nowait(lane)

    results = await asyncio.gather(*(worker(batch) for batch in batches), return_exceptions=True)
    for batch, result in zip(batches, results, strict=True):
        if isinstance(result, BaseException):
            LOGGER.error(
                "Unexpected scheduler failure in job %s (%s)",
                job.job_id,
                type(result).__name__,
            )
            message = _sanitize_diagnostic_text(
                f"{type(result).__name__}: {result}"
            )
            job.error = f"Unexpected scheduler failure: {message}"
            failure = FailureDetail(error_code="provider_exception", message=message)
            _append_failed_records(
                job,
                batch,
                request.summary_style,
                failures={record.record_id: failure for record in batch},
            )

    processed_records = job.completed_records + job.failed_records
    job.status = (
        "completed"
        if job.failed_records == 0 and processed_records == job.total_records
        else "failed"
    )
    if job.status == "failed" and job.error is None:
        first_failure = next(
            (line for line in job.artifact_lines if line.status == "failed"),
            None,
        )
        if first_failure is not None:
            job.error = (
                "One or more provider results failed; first failure: "
                f"{first_failure.error_code}: {first_failure.message or first_failure.error or 'no detail'}"
            )
        else:
            job.error = "One or more provider results failed"
    job.touch()


def get_job(job_id: str) -> JobState | None:
    return JOBS.get(job_id)
