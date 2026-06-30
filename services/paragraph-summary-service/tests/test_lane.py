import pytest
from app.scheduler.lane import QuotaLane


def test_rolling_rpm_window_uses_recent_request_attempts():
    lane = QuotaLane("lane_01", rpm=2, provider_alias="gemini_01")
    lane.dispatch_history.extend([0.0, 0.1])
    lane.last_dispatch_time = 0.1

    assert lane.get_request_count_in_window(1.0) == 2
    assert lane.get_available_at(1.0) == pytest.approx(60.0)
    assert lane.get_unavailability_reason(1.0) == "rpm_window"

    # The boundary is rolling from each attempt, not a wall-clock minute.
    assert lane.get_request_count_in_window(60.0) == 1
    assert lane.get_available_at(60.0) == pytest.approx(60.0)


def test_rolling_window_respects_an_adaptive_rpm_reduction():
    lane = QuotaLane("lane_01", rpm=2)
    lane.dispatch_history.extend([1.0, 2.0, 3.0, 4.0])
    lane.last_dispatch_time = 4.0

    # Two old attempts must expire before another request fits under RPM 2.
    assert lane.get_available_at(10.0) == pytest.approx(63.0)


def test_lane_availability_diagnostic_is_safe_and_deterministic():
    secret = "diagnostic-secret-must-not-leak"
    lane = QuotaLane(
        "lane_02",
        rpm=4,
        provider_alias="gemini_02",
        api_key=secret,
    )
    lane.set_initial_stagger(100.0, 5.0)

    diagnostic = lane.get_availability_diagnostic(101.0)

    assert diagnostic == {
        "available": False,
        "reason": "lane_stagger",
        "available_in_seconds": 4.0,
        "requests_in_rolling_window": 0,
        "rolling_window_seconds": 60.0,
        "current_rpm": 4,
    }
    assert secret not in repr(diagnostic)


def test_lane_reservation_prevents_duplicate_scheduler_assignment():
    lane = QuotaLane("lane_01", rpm=60)

    assert lane.reserve(10.0)
    assert not lane.reserve(10.0)
    assert lane.get_unavailability_reason(10.0) == "in_flight"

    lane.release_reservation()
    assert lane.get_unavailability_reason(10.0) == "none"


@pytest.mark.asyncio
async def test_quota_lane_cooldown():
    lane = QuotaLane("test", rpm=60, time_scale=1.0)
    current_time = 0.0

    def mock_time():
        return current_time

    sleep_calls = []

    async def mock_sleep(delay):
        nonlocal current_time
        sleep_calls.append(delay)
        current_time += delay

    await lane.wait_for_cooldown(get_time=mock_time, sleep=mock_sleep)
    assert lane.last_dispatch_time == 0.0
    assert sleep_calls == []

    await lane.wait_for_cooldown(get_time=mock_time, sleep=mock_sleep)

    assert sleep_calls == [1.0]
    assert lane.last_dispatch_time == 1.0
    assert list(lane.dispatch_history) == [0.0, 1.0]


@pytest.mark.asyncio
async def test_rate_limit_cooldown_is_scoped_to_one_provider_identity():
    lane_one = QuotaLane(
        "lane_01",
        rpm=60,
        provider_alias="gemini_01",
        rate_limit_cooldown_seconds=10,
        jitter_ratio=0,
    )
    lane_two = QuotaLane(
        "lane_02",
        rpm=60,
        provider_alias="gemini_02",
        rate_limit_cooldown_seconds=10,
        jitter_ratio=0,
    )
    current_time = 5.0

    def mock_time():
        return current_time

    lane_one.defer_after_rate_limit(1, get_time=mock_time, random_value=lambda: 0)

    assert lane_one.is_rate_limit_cooling_down(get_time=mock_time)
    assert not lane_two.is_rate_limit_cooling_down(get_time=mock_time)
    assert lane_one.cooldown_until == 15.0
    assert lane_two.cooldown_until is None


def test_quota_lane_adaptive_rpm_disabled_without_flag():
    lane = QuotaLane("test", rpm=10)
    assert not lane.adaptive_rpm_enabled
    # record multiple successes
    for _ in range(10):
        lane.record_success()
    assert lane.current_rpm == 10
    assert lane.success_streak == 0
    assert lane.adaptive_adjustment_count == 0


def test_adaptive_rpm_increases_after_threshold():
    lane = QuotaLane(
        "test",
        rpm=10,
        adaptive_rpm_enabled=True,
        adaptive_rpm_success_threshold=3,
        adaptive_rpm_max=12,
    )
    assert lane.adaptive_rpm_enabled
    assert lane.current_rpm == 10

    # 1st success
    changed = lane.record_success()
    assert not changed
    assert lane.success_streak == 1
    assert lane.current_rpm == 10

    # 2nd success
    changed = lane.record_success()
    assert not changed
    assert lane.success_streak == 2

    # 3rd success -> threshold met, should increment RPM
    changed = lane.record_success()
    assert changed
    assert lane.success_streak == 0
    assert lane.current_rpm == 11
    assert lane.adaptive_adjustment_count == 1

    # 4th success
    lane.record_success()
    # 5th success
    lane.record_success()
    # 6th success -> threshold met again, should increment RPM to max (12)
    changed = lane.record_success()
    assert changed
    assert lane.current_rpm == 12

    # 7th-9th successes -> max RPM reached, should not increase further
    lane.record_success()
    lane.record_success()
    changed = lane.record_success()
    assert not changed
    assert lane.current_rpm == 12


def test_adaptive_rpm_rate_limit_backoff():
    lane = QuotaLane(
        "test",
        rpm=5,
        adaptive_rpm_enabled=True,
        adaptive_rpm_max=15,
        adaptive_rpm_backoff_factor=0.5,
    )
    # Scale up to 14
    lane.current_rpm = 14
    lane.rpm = 14
    lane.success_streak = 2

    # Rate limit hit -> streak resets, RPM backs off
    changed = lane.record_rate_limit_response()
    assert changed
    assert lane.success_streak == 0
    assert lane.current_rpm == 7  # 14 * 0.5
    assert lane.adaptive_adjustment_count == 1

    # Rate limit hit again -> backs off to base RPM (5) since 7 * 0.5 = 3 which is below base 5
    changed = lane.record_rate_limit_response()
    assert changed
    assert lane.current_rpm == 5


@pytest.mark.asyncio
async def test_adaptive_cooldown_respects_adapted_rpm():
    lane = QuotaLane(
        "test",
        rpm=10,
        time_scale=1.0,
        adaptive_rpm_enabled=True,
        adaptive_rpm_success_threshold=1,
        adaptive_rpm_max=20,
    )
    current_time = 0.0

    def mock_time():
        return current_time

    sleep_calls = []

    async def mock_sleep(delay):
        nonlocal current_time
        sleep_calls.append(delay)
        current_time += delay

    # Base RPM is 10 -> interval is 6.0s
    await lane.wait_for_cooldown(get_time=mock_time, sleep=mock_sleep)
    assert lane.last_dispatch_time == 0.0

    # Adapts to RPM 11 -> interval is 60/11 = 5.4545...s
    lane.record_success()
    assert lane.current_rpm == 11

    await lane.wait_for_cooldown(get_time=mock_time, sleep=mock_sleep)
    assert len(sleep_calls) == 1
    assert abs(sleep_calls[0] - (60.0 / 11.0)) < 1e-4
