import asyncio
import time

class QuotaLane:
    def __init__(self, lane_id: str, rpm: int, time_scale: float = 1.0):
        self.lane_id = lane_id
        self.rpm = rpm
        self.interval = (60.0 / rpm) * time_scale if rpm > 0 else 0
        self.last_dispatch_time: float | None = None

    async def wait_for_cooldown(self, get_time=time.monotonic, sleep=asyncio.sleep):
        if self.interval <= 0:
            return

        now = get_time()
        if self.last_dispatch_time is None:
            self.last_dispatch_time = now
            return

        elapsed = now - self.last_dispatch_time
        if elapsed < self.interval:
            await sleep(self.interval - elapsed)
            
        self.last_dispatch_time = get_time()
