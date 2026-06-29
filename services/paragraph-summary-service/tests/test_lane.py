import pytest
from app.scheduler.lane import QuotaLane

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
