import asyncio
import time

import pytest

import app.scheduler.dispatcher as dispatcher_module
from app.records.schema import InputRecord, SummaryRequest
from app.scheduler.dispatcher import (
    JobState,
    _process_batch,
    _record_lane_availability,
    _run_job_background,
    _stagger_lanes_evenly,
)
from app.scheduler.lane import QuotaLane


class MockLowLevelProvider:
    def __init__(self, should_fail_rate_limit=False, should_fail_other=False):
        self.should_fail_rate_limit = should_fail_rate_limit
        self.should_fail_other = should_fail_other
        self.calls = 0

    async def summarize_batch(self, document_id, records, summary_style):
        self.calls += 1
        if self.should_fail_rate_limit:
            raise RuntimeError("API quota exceeded: ResourceExhausted (rate limit reached)")
        if self.should_fail_other:
            raise ValueError("Some internal server error occurred")
        
        from app.records.schema import SummaryArtifactLine
        return [
            SummaryArtifactLine(
                document_id=document_id,
                record_id=r.record_id,
                stable_id=r.stable_id,
                source_hash=r.source_hash,
                summary_text="summarized text",
                summary_style=summary_style,
                provider="mock",
                model="mock-model",
                template_version="v1",
                status="completed",
                created_at="now",
            )
            for r in records
        ]


def test_lanes_are_staggered_evenly_in_stable_alias_order():
    lanes = [
        QuotaLane(f"lane_{index:02d}", rpm=4, provider_alias=f"gemini_{index:02d}")
        for index in range(1, 4)
    ]

    offsets = _stagger_lanes_evenly(lanes, start_time=100.0)

    assert offsets == {
        "gemini_01": 0.0,
        "gemini_02": 5.0,
        "gemini_03": 10.0,
    }
    assert [lane.get_available_at(100.0) for lane in lanes] == [100.0, 105.0, 110.0]


def test_job_reports_safe_availability_by_alias():
    job = JobState("job-diagnostics", "doc-diagnostics", 1)
    lane = QuotaLane(
        "lane_01",
        rpm=2,
        provider_alias="gemini_01",
        api_key="availability-secret-must-not-leak",
    )
    lane.dispatch_history.extend([90.0, 99.0])
    lane.last_dispatch_time = 99.0

    _record_lane_availability(job, [lane], now=100.0)

    assert job.stats["lane_unavailability_reasons"] == {"gemini_01": "rpm_window"}
    assert job.stats["provider_availability_by_alias"]["gemini_01"] == {
        "available": False,
        "reason": "rpm_window",
        "available_in_seconds": 50.0,
        "requests_in_rolling_window": 2,
        "rolling_window_seconds": 60.0,
        "current_rpm": 2,
    }
    assert "availability-secret-must-not-leak" not in repr(job.stats)


@pytest.mark.asyncio
async def test_scheduler_caps_and_counts_rate_limit_requeues(monkeypatch):
    lane = QuotaLane(
        "lane_01",
        rpm=600_000,
        time_scale=0.001,
        provider_alias="mock_01",
        jitter_ratio=0,
    )

    class AlwaysRateLimitedProvider:
        def __init__(self):
            self.calls = 0

        async def summarize_batch(self, document_id, records, summary_style):
            self.calls += 1
            raise RuntimeError("429 provider rate limit")

    provider = AlwaysRateLimitedProvider()
    monkeypatch.setattr(dispatcher_module.settings, "summary_service_provider", "mock")
    monkeypatch.setattr(dispatcher_module.settings, "summary_lane_count", 1)
    monkeypatch.setattr(dispatcher_module.settings, "summary_max_parallel_lanes", 1)
    monkeypatch.setattr(
        dispatcher_module,
        "_build_lanes_and_providers",
        lambda provider_name, credentials: ([lane], {lane.lane_id: provider}),
    )
    request = SummaryRequest(
        document_id="doc-rate-limit-cap",
        records=[InputRecord(record_id="r1", text="safe input", source_hash="h1")],
    )
    job = JobState("job-rate-limit-cap", request.document_id, 1)

    await _run_job_background(job, request)

    assert job.status == "failed"
    assert provider.calls == 3
    assert job.stats["retry_count"] == 2
    assert job.stats["rate_limit_count"] == 3
    assert job.artifact_lines[0].attempt_count == 3


@pytest.mark.asyncio
async def test_lane_unavailability_reasons():
    lane = QuotaLane("lane_01", rpm=60, provider_alias="gemini_01")
    now = time.monotonic()
    assert lane.get_unavailability_reason(now) == "none"

    async with lane.provider_call_slot():
        assert lane.get_unavailability_reason(now) == "in_flight"

    lane.cooldown_until = now + 10.0
    lane.cooldown_reason = "provider_rate_limited"
    assert lane.get_unavailability_reason(now) == "provider_cooldown"

    lane.cooldown_until = None
    lane.cooldown_reason = None
    lane.last_dispatch_time = now - 0.1
    assert lane.get_unavailability_reason(now) == "rpm_window"

@pytest.mark.asyncio
async def test_process_batch_rate_limit_requeue_and_cooldown(monkeypatch):
    async def mock_wait_for_cooldown(self, *args, **kwargs):
        self.cooldown_until = None
        self.cooldown_reason = None
        return 0.0
    monkeypatch.setattr(QuotaLane, "wait_for_cooldown", mock_wait_for_cooldown)

    job = JobState("job_1", "doc_1", 2)
    records = [
        InputRecord(record_id="r1", text="text1", source_hash="h1"),
        InputRecord(record_id="r2", text="text2", source_hash="h2"),
    ]
    lane = QuotaLane("lane_01", rpm=60, provider_alias="gemini_01", rate_limit_cooldown_seconds=10.0)
    provider = MockLowLevelProvider(should_fail_rate_limit=True)

    await _process_batch(
        job,
        records,
        provider,
        "one_sentence",
        max_provider_calls=10,
        lane=lane,
    )

    # In single-lane fallback (lanes=None), rate limits exhaust after MAX_RETRIES + 1 attempts (3 total)
    assert job.failed_records == 2
    assert lane.cooldown_until is not None
    assert lane.is_rate_limit_cooling_down()
    assert job.stats["rate_limit_count"] == 3
    assert job.stats["cooldown_count"] == 1

@pytest.mark.asyncio
async def test_process_batch_other_error_non_rate_limit(monkeypatch):
    async def mock_wait_for_cooldown(self, *args, **kwargs):
        self.cooldown_until = None
        self.cooldown_reason = None
        return 0.0
    monkeypatch.setattr(QuotaLane, "wait_for_cooldown", mock_wait_for_cooldown)

    job = JobState("job_2", "doc_2", 2)
    records = [
        InputRecord(record_id="r1", text="text1", source_hash="h1"),
    ]
    lane = QuotaLane("lane_01", rpm=60, provider_alias="gemini_01")
    provider = MockLowLevelProvider(should_fail_other=True)

    await _process_batch(
        job,
        records,
        provider,
        "one_sentence",
        max_provider_calls=10,
        lane=lane,
    )

    assert job.failed_records == 1
    # Cooldown reason is cleared on the last attempt since wait_for_cooldown executes,
    # and no further defer_before_retry is called when attempt reaches MAX_RETRIES.
    assert lane.cooldown_reason is None
