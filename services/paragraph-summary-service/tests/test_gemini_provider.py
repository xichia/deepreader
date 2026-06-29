import json
import logging
import os
from types import SimpleNamespace

import pytest

from app.config import Settings, settings
from app.providers.gemini import GeminiProvider, StructuredOutputParseError
from app.records.schema import InputRecord, SummaryRequest
import app.scheduler.dispatcher as dispatcher_module
from app.scheduler.dispatcher import (
    JobState,
    ProviderConfigurationError,
    _build_lanes_and_providers,
    _run_job_background,
    validate_provider_configuration,
)


class FakeModels:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeClient:
    def __init__(self, response):
        self.models = FakeModels(response)
        self.aio = SimpleNamespace(models=self.models)


def _configure_one_gemini_lane(monkeypatch, *, api_key="test-lane-key"):
    for name in tuple(os.environ):
        if name.startswith("GEMINI_API_KEY_LANE_"):
            monkeypatch.delenv(name)
    monkeypatch.setattr(settings, "summary_service_provider", "gemini")
    monkeypatch.setattr(settings, "summary_service_enable_provider_calls", True)
    monkeypatch.setattr(settings, "summary_service_model", "gemini-2.5-flash")
    monkeypatch.setattr(settings, "summary_lane_count", 1)
    monkeypatch.setattr(settings, "summary_lane_rpm", 1)
    monkeypatch.setattr(settings, "summary_max_parallel_lanes", 1)
    monkeypatch.setattr(settings, "summary_batch_target_tokens", 1000)
    monkeypatch.setattr(settings, "summary_batch_hard_max_tokens", 3000)
    monkeypatch.setattr(settings, "summary_batch_reserved_output_tokens", 1000)
    monkeypatch.setattr(settings, "summary_batch_max_records", 10)
    monkeypatch.setattr(settings, "summary_max_provider_calls_per_job", 3)
    monkeypatch.setattr(settings, "summary_max_input_tokens_per_job", 3000)
    monkeypatch.setattr(settings, "summary_provider_rate_limit_cooldown_seconds", 0)
    monkeypatch.setattr(settings, "summary_retry_backoff_base_seconds", 0)
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY_LANE_01", api_key)


def test_gemini_provider_disabled_fails(monkeypatch):
    _configure_one_gemini_lane(monkeypatch)
    monkeypatch.setattr(settings, "summary_service_enable_provider_calls", False)

    with pytest.raises(ProviderConfigurationError, match="disabled"):
        validate_provider_configuration()


def test_gemini_provider_missing_keys_fails(monkeypatch):
    _configure_one_gemini_lane(monkeypatch)
    monkeypatch.delenv("GEMINI_API_KEY_LANE_01")

    with pytest.raises(ProviderConfigurationError, match="GEMINI_API_KEY_LANE_01"):
        validate_provider_configuration()


def test_gemini_provider_uses_lane_specific_key_without_logging_it(monkeypatch, caplog):
    secret = "lane-secret-must-not-leak"
    _configure_one_gemini_lane(monkeypatch, api_key=secret)
    received_keys = []

    class CapturingProvider:
        def __init__(self, model_name, template_version, api_key, lane_id):
            received_keys.append((lane_id, api_key))

    monkeypatch.setattr(dispatcher_module, "GeminiProvider", CapturingProvider)
    caplog.set_level(logging.DEBUG)
    credentials = validate_provider_configuration()
    lanes, _providers = _build_lanes_and_providers("gemini", credentials)
    logging.getLogger("test").debug("lane=%r", lanes[0])

    assert received_keys == [("lane_01", secret)]
    assert lanes[0].credential_env_name == "GEMINI_API_KEY_LANE_01"
    assert secret not in caplog.text
    assert secret not in repr(lanes[0])


def test_multi_key_config_creates_distinct_aliased_clients(monkeypatch):
    _configure_one_gemini_lane(monkeypatch, api_key="project-key-one")
    monkeypatch.setattr(settings, "summary_lane_count", 3)
    monkeypatch.setattr(settings, "summary_max_parallel_lanes", 3)
    monkeypatch.setenv("GEMINI_API_KEY_LANE_03", "project-key-two")
    received = []

    class CapturingProvider:
        def __init__(self, model_name, template_version, api_key, lane_id):
            received.append((lane_id, api_key))

    monkeypatch.setattr(dispatcher_module, "GeminiProvider", CapturingProvider)

    credentials = validate_provider_configuration()
    lanes, _ = _build_lanes_and_providers("gemini", credentials)

    assert list(credentials) == ["GEMINI_API_KEY_LANE_01", "GEMINI_API_KEY_LANE_03"]
    assert received == [
        ("lane_01", "project-key-one"),
        ("lane_02", "project-key-two"),
    ]
    assert [lane.provider_alias for lane in lanes] == ["gemini_01", "gemini_02"]
    assert len({id(lane._in_flight) for lane in lanes}) == 2


def test_single_standard_key_is_backwards_compatible(monkeypatch):
    _configure_one_gemini_lane(monkeypatch)
    monkeypatch.setattr(settings, "summary_lane_count", 10)
    monkeypatch.delenv("GEMINI_API_KEY_LANE_01")
    monkeypatch.setenv("GEMINI_API_KEY", "single-project-key")

    credentials = validate_provider_configuration()
    lanes, _ = _build_lanes_and_providers("gemini", credentials)

    assert credentials == {"GEMINI_API_KEY": "single-project-key"}
    assert len(lanes) == 1
    assert lanes[0].provider_alias == "gemini_01"
    assert lanes[0].credential_env_name == "GEMINI_API_KEY"


def test_pooled_keys_are_deduplicated_and_capped(monkeypatch):
    _configure_one_gemini_lane(monkeypatch)
    monkeypatch.setattr(settings, "summary_lane_count", 2)
    monkeypatch.delenv("GEMINI_API_KEY_LANE_01")
    monkeypatch.setenv("GEMINI_API_KEYS", "key-one, key-one\nkey-two;key-three")

    credentials = validate_provider_configuration()

    assert list(credentials.values()) == ["key-one", "key-two"]


@pytest.mark.asyncio
async def test_rate_limit_on_one_alias_does_not_poison_other_alias(monkeypatch, caplog):
    first_secret = "first-project-secret"
    second_secret = "second-project-secret"
    _configure_one_gemini_lane(monkeypatch, api_key=first_secret)
    monkeypatch.setattr(settings, "summary_lane_count", 2)
    monkeypatch.setattr(settings, "summary_lane_rpm", 600_000)
    monkeypatch.setattr(settings, "summary_max_parallel_lanes", 2)
    monkeypatch.setattr(settings, "summary_batch_max_records", 1)
    monkeypatch.setattr(settings, "summary_max_provider_calls_per_job", 10)
    monkeypatch.setattr(settings, "summary_max_input_tokens_per_job", 0)
    monkeypatch.setenv("GEMINI_API_KEY_LANE_02", second_secret)
    attempts_by_key = {first_secret: 0, second_secret: 0}

    class IndependentlyLimitedProvider:
        def __init__(self, model_name, template_version, api_key, lane_id):
            self.model_name = model_name
            self.template_version = template_version
            self.api_key = api_key

        async def summarize_batch(self, document_id, batch, summary_style):
            attempts_by_key[self.api_key] += 1
            if self.api_key == first_secret and attempts_by_key[self.api_key] == 1:
                raise RuntimeError(f"429 project quota for credential {self.api_key}")
            return [
                dispatcher_module.SummaryArtifactLine(
                    document_id=document_id,
                    record_id=record.record_id,
                    stable_id=record.stable_id,
                    source_hash=record.source_hash,
                    summary_text="A safe summary.",
                    summary_style=summary_style,
                    provider="gemini",
                    model=self.model_name,
                    template_version=self.template_version,
                    status="completed",
                    created_at="2026-06-29T12:00:00Z",
                )
                for record in batch
            ]

    monkeypatch.setattr(dispatcher_module, "GeminiProvider", IndependentlyLimitedProvider)
    caplog.set_level(logging.INFO)
    request = SummaryRequest(
        document_id="doc-two-projects",
        records=[
            InputRecord(record_id="r1", stable_id="r1", text="First.", source_hash="h1"),
            InputRecord(record_id="r2", stable_id="r2", text="Second.", source_hash="h2"),
        ],
    )
    job = JobState("job-two-projects", request.document_id, len(request.records))

    await _run_job_background(job, request)

    assert job.status == "completed"
    assert job.stats["provider_identity_count"] == 2
    assert job.stats["scheduler_parallelism"] == 2
    assert job.stats["provider_calls_by_alias"] == {"gemini_01": 2, "gemini_02": 1}
    assert job.stats["rate_limit_count_by_alias"] == {"gemini_01": 1, "gemini_02": 0}
    assert attempts_by_key == {first_secret: 2, second_secret: 1}
    assert {line.provider_alias for line in job.artifact_lines} == {"gemini_01", "gemini_02"}
    diagnostics = caplog.text + repr(job.stats)
    assert first_secret not in diagnostics
    assert second_secret not in diagnostics


@pytest.mark.asyncio
async def test_gemini_provider_parses_structured_response():
    response = SimpleNamespace(
        text=json.dumps(
            {
                "summaries": [
                    {
                        "record_id": "stable-1",
                        "source_hash": "hash-1",
                        "summary_text": "The pump requires steady inlet flow.",
                        "status": "completed",
                    }
                ]
            }
        ),
        usage_metadata=SimpleNamespace(
            prompt_token_count=42,
            candidates_token_count=9,
            total_token_count=51,
        ),
    )
    client = FakeClient(response)
    provider = GeminiProvider(
        model_name="gemini-2.5-flash",
        template_version="paragraph_one_sentence_v1",
        api_key="not-a-real-key",
        lane_id="lane_01",
        client=client,
    )
    record = InputRecord(
        record_id="stable-1",
        stable_id="stable-1",
        text="The pump requires steady inlet flow.",
        source_hash="hash-1",
    )

    results = await provider.summarize_batch("doc-1", [record], "one_sentence")

    assert len(results) == 1
    assert results[0].record_id == record.record_id
    assert results[0].stable_id == record.stable_id
    assert results[0].source_hash == record.source_hash
    assert results[0].provider == "gemini"
    assert results[0].model == "gemini-2.5-flash"
    assert results[0].usage["total_tokens"] == 51
    assert client.models.calls[0]["config"]["response_mime_type"] == "application/json"
    assert "The pump requires steady inlet flow." in client.models.calls[0]["contents"]


@pytest.mark.asyncio
async def test_gemini_provider_rejects_malformed_response():
    provider = GeminiProvider(
        model_name="gemini-2.5-flash",
        template_version="paragraph_one_sentence_v1",
        api_key="not-a-real-key",
        lane_id="lane_01",
        client=FakeClient(SimpleNamespace(text="not-json", usage_metadata=None)),
    )
    record = InputRecord(record_id="r1", stable_id="r1", text="Source.", source_hash="h1")

    with pytest.raises(StructuredOutputParseError):
        await provider.summarize_batch("doc-1", [record], "one_sentence")


@pytest.mark.asyncio
async def test_dispatcher_fails_closed_when_max_input_tokens_exceeded(monkeypatch):
    _configure_one_gemini_lane(monkeypatch)
    monkeypatch.setattr(settings, "summary_max_input_tokens_per_job", 1)
    request = SummaryRequest(
        document_id="doc-1",
        records=[InputRecord(record_id="r1", stable_id="r1", text="A source paragraph.", source_hash="h1")],
    )
    job = JobState("job-1", request.document_id, 1)

    await _run_job_background(job, request)

    assert job.status == "failed"
    assert job.stats["provider_calls_attempted"] == 0
    assert job.artifact_lines[0].error_code == "max_input_tokens_exceeded"


@pytest.mark.asyncio
async def test_dispatcher_stops_at_max_provider_calls(monkeypatch):
    _configure_one_gemini_lane(monkeypatch)
    monkeypatch.setattr(settings, "summary_lane_rpm", 600_000)
    monkeypatch.setattr(settings, "summary_batch_target_tokens", 300)
    monkeypatch.setattr(settings, "summary_max_provider_calls_per_job", 1)

    class SuccessfulProvider:
        def __init__(self, model_name, template_version, api_key, lane_id):
            self.model_name = model_name
            self.template_version = template_version

        async def summarize_batch(self, document_id, batch, summary_style):
            return [
                dispatcher_module.SummaryArtifactLine(
                    document_id=document_id,
                    record_id=record.record_id,
                    stable_id=record.stable_id,
                    source_hash=record.source_hash,
                    summary_text="A capped provider summary.",
                    summary_style=summary_style,
                    provider="gemini",
                    model=self.model_name,
                    template_version=self.template_version,
                    status="completed",
                    created_at="2026-06-29T12:00:00Z",
                )
                for record in batch
            ]

    monkeypatch.setattr(dispatcher_module, "GeminiProvider", SuccessfulProvider)
    records = [
        InputRecord(
            record_id=f"r{index}",
            stable_id=f"r{index}",
            text="x" * 240,
            source_hash=f"h{index}",
        )
        for index in range(2)
    ]
    request = SummaryRequest(document_id="doc-1", records=records)
    job = JobState("job-1", request.document_id, len(records))

    await _run_job_background(job, request)

    assert job.status == "failed"
    assert job.stats["total_batches"] == 2
    assert job.stats["provider_calls_attempted"] == 1
    assert job.completed_records == 1
    assert job.failed_records == 1
    assert {line.error_code for line in job.artifact_lines if line.status == "failed"} == {
        "max_provider_calls_exceeded"
    }


def test_mock_provider_still_default(monkeypatch):
    monkeypatch.delenv("SUMMARY_SERVICE_PROVIDER", raising=False)
    monkeypatch.delenv("SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS", raising=False)

    fresh_settings = Settings()

    assert fresh_settings.summary_service_provider == "mock"
    assert fresh_settings.summary_service_enable_provider_calls is False


def test_provider_safe_local_defaults(monkeypatch):
    for name in (
        "SUMMARY_LANE_COUNT",
        "SUMMARY_LANE_RPM",
        "SUMMARY_MAX_PARALLEL_LANES",
        "SUMMARY_BATCH_TARGET_TOKENS",
        "SUMMARY_BATCH_HARD_MAX_TOKENS",
        "SUMMARY_BATCH_RESERVED_OUTPUT_TOKENS",
        "SUMMARY_BATCH_MAX_RECORDS",
        "SUMMARY_MAX_PROVIDER_CALLS_PER_JOB",
        "SUMMARY_MAX_INPUT_TOKENS_PER_JOB",
        "SUMMARY_PROVIDER_RATE_LIMIT_COOLDOWN_SECONDS",
        "SUMMARY_RETRY_BACKOFF_BASE_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    fresh_settings = Settings()

    assert fresh_settings.summary_lane_count == 10
    assert fresh_settings.summary_lane_rpm == 4
    assert fresh_settings.summary_max_parallel_lanes == 10
    assert fresh_settings.summary_batch_target_tokens == 50_000
    assert fresh_settings.summary_batch_hard_max_tokens == 75_000
    assert fresh_settings.summary_batch_reserved_output_tokens == 25_000
    assert fresh_settings.summary_batch_max_records == 10
    assert fresh_settings.summary_max_provider_calls_per_job == 1_000
    assert fresh_settings.summary_max_input_tokens_per_job == 0
    assert fresh_settings.summary_provider_rate_limit_cooldown_seconds == 60
    assert fresh_settings.summary_retry_backoff_base_seconds == 1


@pytest.mark.asyncio
async def test_scheduler_effective_config_reflects_env_overrides(monkeypatch):
    monkeypatch.setenv("SUMMARY_MAX_PARALLEL_LANES", "2")
    monkeypatch.setenv("SUMMARY_LANE_RPM", "7")
    monkeypatch.setenv("SUMMARY_BATCH_MAX_RECORDS", "3")
    fresh_settings = Settings()
    monkeypatch.setattr(settings, "summary_service_provider", "mock")
    monkeypatch.setattr(settings, "summary_max_parallel_lanes", fresh_settings.summary_max_parallel_lanes)
    monkeypatch.setattr(settings, "summary_lane_rpm", fresh_settings.summary_lane_rpm)
    monkeypatch.setattr(settings, "summary_batch_max_records", fresh_settings.summary_batch_max_records)
    request = SummaryRequest(
        document_id="doc-config",
        records=[InputRecord(record_id="r1", text="local", source_hash="h1")],
    )
    job = JobState("job-config", request.document_id, 1)

    await _run_job_background(job, request)

    assert job.stats["effective_config"]["max_parallel_lanes"] == 2
    assert job.stats["effective_config"]["lane_rpm"] == 7
    assert job.stats["effective_config"]["batch_max_records"] == 3
    assert job.stats["batch_max_records"] == 3


@pytest.mark.asyncio
async def test_mock_service_api_still_passes(monkeypatch):
    monkeypatch.setattr(settings, "summary_service_provider", "mock")
    request = SummaryRequest(
        document_id="doc-1",
        records=[InputRecord(record_id="r1", text="A local mock record.", source_hash="h1")],
    )
    job = JobState("job-1", request.document_id, 1)

    await _run_job_background(job, request)

    assert job.status == "completed"
    assert job.artifact_lines[0].provider == "mock"
    assert job.stats["provider_calls_attempted"] == 1


def test_validation_allows_unset_and_zero_input_cap(monkeypatch):
    # env var unset (defaults to 0)
    monkeypatch.delenv("SUMMARY_MAX_INPUT_TOKENS_PER_JOB", raising=False)
    fresh_settings = Settings()
    assert fresh_settings.summary_max_input_tokens_per_job == 0

    monkeypatch.setattr(settings, "summary_max_input_tokens_per_job", 0)
    monkeypatch.setattr(settings, "summary_service_provider", "gemini")
    monkeypatch.setattr(settings, "summary_service_enable_provider_calls", True)
    monkeypatch.setenv("GEMINI_API_KEY_LANE_01", "test-key")
    monkeypatch.setattr(settings, "summary_lane_count", 1)

    validate_provider_configuration()  # Should not raise

    # env var "0"
    monkeypatch.setenv("SUMMARY_MAX_INPUT_TOKENS_PER_JOB", "0")
    fresh_settings_0 = Settings()
    assert fresh_settings_0.summary_max_input_tokens_per_job == 0

    # env var positive
    monkeypatch.setenv("SUMMARY_MAX_INPUT_TOKENS_PER_JOB", "150")
    fresh_settings_pos = Settings()
    assert fresh_settings_pos.summary_max_input_tokens_per_job == 150


@pytest.mark.asyncio
async def test_large_input_proceeds_to_dispatch_when_cap_disabled(monkeypatch):
    _configure_one_gemini_lane(monkeypatch)
    monkeypatch.setattr(settings, "summary_lane_rpm", 6000)
    monkeypatch.setattr(settings, "summary_batch_hard_max_tokens", 10000)
    monkeypatch.setattr(settings, "summary_max_input_tokens_per_job", 0)

    records = [
        InputRecord(
            record_id="r1",
            stable_id="r1",
            text="hello " * 2000,
            source_hash="h1",
        )
    ]
    request = SummaryRequest(document_id="doc-1", records=records)
    job = JobState("job-1", request.document_id, len(records))

    dispatch_calls = []
    class MockGeminiProvider:
        def __init__(self, model_name, template_version, api_key, lane_id):
            self.model_name = model_name
            self.template_version = template_version
            self.api_key = api_key
            self.lane_id = lane_id

        async def summarize_batch(self, document_id, batch, summary_style):
            dispatch_calls.append((document_id, batch, summary_style))
            from app.scheduler.dispatcher import SummaryArtifactLine
            return [
                SummaryArtifactLine(
                    document_id=document_id,
                    record_id=r.record_id,
                    stable_id=r.stable_id,
                    source_hash=r.source_hash,
                    summary_text="Mock summary.",
                    summary_style=summary_style,
                    provider="gemini",
                    model="mock-model",
                    template_version="paragraph_one_sentence_v1",
                    status="completed",
                    created_at="2026-06-29T12:00:00Z",
                )
                for r in batch
            ]

    monkeypatch.setattr(dispatcher_module, "GeminiProvider", MockGeminiProvider)

    await _run_job_background(job, request)

    assert job.status == "completed"
    assert len(dispatch_calls) == 1
    assert job.stats["provider_calls_attempted"] == 1


@pytest.mark.asyncio
async def test_large_input_blocked_when_cap_enabled(monkeypatch):
    _configure_one_gemini_lane(monkeypatch)
    monkeypatch.setattr(settings, "summary_lane_rpm", 6000)
    monkeypatch.setattr(settings, "summary_batch_hard_max_tokens", 10000)
    monkeypatch.setattr(settings, "summary_max_input_tokens_per_job", 500)

    records = [
        InputRecord(
            record_id="r1",
            stable_id="r1",
            text="hello " * 1000,
            source_hash="h1",
        )
    ]
    request = SummaryRequest(document_id="doc-1", records=records)
    job = JobState("job-1", request.document_id, len(records))

    dispatch_calls = []
    class MockGeminiProvider:
        def __init__(self, model_name, template_version, api_key, lane_id):
            pass

        async def summarize_batch(self, document_id, batch, summary_style):
            dispatch_calls.append((document_id, batch, summary_style))
            return []

    monkeypatch.setattr(dispatcher_module, "GeminiProvider", MockGeminiProvider)

    await _run_job_background(job, request)

    assert job.status == "failed"
    assert len(dispatch_calls) == 0
    assert job.artifact_lines[0].error_code == "max_input_tokens_exceeded"
