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
