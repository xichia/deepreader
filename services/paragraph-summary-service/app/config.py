"""Environment-backed paragraph summary service settings."""

from __future__ import annotations

import os

from pydantic import BaseModel, Field


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings(BaseModel):
    summary_service_provider: str = Field(
        default_factory=lambda: os.getenv("SUMMARY_SERVICE_PROVIDER", "mock").strip().lower()
    )
    summary_service_enable_provider_calls: bool = Field(
        default_factory=lambda: _env_bool("SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS")
    )
    summary_service_model: str = Field(
        default_factory=lambda: os.getenv("SUMMARY_SERVICE_MODEL", "gemini-2.5-flash").strip()
    )
    summary_template_version: str = Field(
        default_factory=lambda: os.getenv(
            "SUMMARY_TEMPLATE_VERSION", "paragraph_one_sentence_v1"
        ).strip()
    )

    summary_lane_count: int = Field(
        default_factory=lambda: int(os.getenv("SUMMARY_LANE_COUNT", "10"))
    )
    summary_lane_rpm: int = Field(
        default_factory=lambda: int(os.getenv("SUMMARY_LANE_RPM", "4"))
    )
    summary_max_parallel_lanes: int = Field(
        default_factory=lambda: int(os.getenv("SUMMARY_MAX_PARALLEL_LANES", "10"))
    )

    summary_batch_target_tokens: int = Field(
        default_factory=lambda: int(os.getenv("SUMMARY_BATCH_TARGET_TOKENS", "50000"))
    )
    summary_batch_hard_max_tokens: int = Field(
        default_factory=lambda: int(os.getenv("SUMMARY_BATCH_HARD_MAX_TOKENS", "75000"))
    )
    summary_batch_reserved_output_tokens: int = Field(
        default_factory=lambda: int(os.getenv("SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS", "25000"))
    )
    summary_batch_max_records: int = Field(
        default_factory=lambda: int(os.getenv("SUMMARY_BATCH_MAX_RECORDS", "10"))
    )
    summary_max_provider_calls_per_job: int = Field(
        default_factory=lambda: int(os.getenv("SUMMARY_MAX_PROVIDER_CALLS_PER_JOB", "1000"))
    )
    summary_max_input_tokens_per_job: int = Field(
        default_factory=lambda: int(os.getenv("SUMMARY_MAX_INPUT_TOKENS_PER_JOB") or "0")
    )
    summary_provider_rate_limit_cooldown_seconds: float = Field(
        default_factory=lambda: float(
            os.getenv("SUMMARY_PROVIDER_RATE_LIMIT_COOLDOWN_SECONDS", "60")
        )
    )
    summary_retry_backoff_base_seconds: float = Field(
        default_factory=lambda: float(os.getenv("SUMMARY_RETRY_BACKOFF_BASE_SECONDS", "1"))
    )
    summary_adaptive_rpm_enabled: bool = Field(
        default_factory=lambda: _env_bool("SUMMARY_ADAPTIVE_RPM_ENABLED", True)
    )
    summary_adaptive_rpm_success_threshold: int = Field(
        default_factory=lambda: int(os.getenv("SUMMARY_ADAPTIVE_RPM_SUCCESS_THRESHOLD", "5"))
    )
    summary_adaptive_rpm_max: int = Field(
        default_factory=lambda: int(os.getenv("SUMMARY_ADAPTIVE_RPM_MAX", "3"))
    )
    summary_adaptive_rpm_backoff_factor: float = Field(
        default_factory=lambda: float(os.getenv("SUMMARY_ADAPTIVE_RPM_BACKOFF_FACTOR", "0.5"))
    )

    def lane_credential_env_names(self) -> list[str]:
        """Return the configured lane variable names without reading key values."""

        return [f"GEMINI_API_KEY_LANE_{index:02d}" for index in range(1, self.summary_lane_count + 1)]

    def safe_summary(self) -> dict[str, str | int | float | bool]:
        """Return non-secret settings suitable for diagnostics."""

        return {
            "provider": self.summary_service_provider,
            "provider_calls_enabled": self.summary_service_enable_provider_calls,
            "model": self.summary_service_model,
            "lane_count": self.summary_lane_count,
            "lane_rpm": self.summary_lane_rpm,
            "max_parallel_lanes": self.summary_max_parallel_lanes,
            "batch_target_tokens": self.summary_batch_target_tokens,
            "batch_hard_max_tokens": self.summary_batch_hard_max_tokens,
            "batch_reserved_output_tokens": self.summary_batch_reserved_output_tokens,
            "batch_max_records": self.summary_batch_max_records,
            "max_provider_calls_per_job": self.summary_max_provider_calls_per_job,
            "max_input_tokens_per_job": self.summary_max_input_tokens_per_job,
            "provider_rate_limit_cooldown_seconds": (
                self.summary_provider_rate_limit_cooldown_seconds
            ),
            "retry_backoff_base_seconds": self.summary_retry_backoff_base_seconds,
            "adaptive_rpm_enabled": self.summary_adaptive_rpm_enabled,
            "adaptive_rpm_success_threshold": self.summary_adaptive_rpm_success_threshold,
            "adaptive_rpm_max": self.summary_adaptive_rpm_max,
            "adaptive_rpm_backoff_factor": self.summary_adaptive_rpm_backoff_factor,
        }


settings = Settings()
