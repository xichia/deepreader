import json
import logging
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
    monkeypatch.setattr(settings, "summary_service_provider", "gemini")
    monkeypatch.setattr(settings, "summary_service_enable_provider_calls", True)
    monkeypatch.setattr(settings, "summary_service_model", "gemini-2.5-flash")
    monkeypatch.setattr(settings, "summary_lane_count", 1)
    monkeypatch.setattr(settings, "summary_lane_rpm", 1)
    monkeypatch.setattr(settings, "summary_max_parallel_lanes", 1)
    monkeypatch.setattr(settings, "summary_batch_target_tokens", 1000)
    monkeypatch.setattr(settings, "summary_batch_hard_max_tokens", 3000)
    monkeypatch.setattr(settings, "summary_batch_reserved_output_tokens", 1000)
    monkeypatch.setattr(settings, "summary_max_provider_calls_per_job", 3)
    monkeypatch.setattr(settings, "summary_max_input_tokens_per_job", 3000)
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
async def test_dispatcher_fails_closed_when_max_provider_calls_exceeded(monkeypatch):
    _configure_one_gemini_lane(monkeypatch)
    monkeypatch.setattr(settings, "summary_batch_target_tokens", 300)
    monkeypatch.setattr(settings, "summary_max_provider_calls_per_job", 1)
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
    assert job.stats["provider_calls_attempted"] == 0
    assert {line.error_code for line in job.artifact_lines} == {"max_provider_calls_exceeded"}


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
        "SUMMARY_MAX_PROVIDER_CALLS_PER_JOB",
        "SUMMARY_MAX_INPUT_TOKENS_PER_JOB",
    ):
        monkeypatch.delenv(name, raising=False)

    fresh_settings = Settings()

    assert fresh_settings.summary_lane_count == 10
    assert fresh_settings.summary_lane_rpm == 4
    assert fresh_settings.summary_max_parallel_lanes == 10
    assert fresh_settings.summary_batch_target_tokens == 50_000
    assert fresh_settings.summary_batch_hard_max_tokens == 75_000
    assert fresh_settings.summary_batch_reserved_output_tokens == 25_000
    assert fresh_settings.summary_max_provider_calls_per_job == 1_000
    assert fresh_settings.summary_max_input_tokens_per_job == 0


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
            from app.scheduler.dispatcher import SummaryArtifactLine
            return []

    monkeypatch.setattr(dispatcher_module, "GeminiProvider", MockGeminiProvider)

    await _run_job_background(job, request)

    assert job.status == "failed"
    assert len(dispatch_calls) == 0
    assert job.artifact_lines[0].error_code == "max_input_tokens_exceeded"
