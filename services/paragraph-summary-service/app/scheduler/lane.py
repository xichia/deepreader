import asyncio
import time


class QuotaLane:
    """A rate-limited provider lane with an in-memory credential."""

    def __init__(
        self,
        lane_id: str,
        rpm: int,
        time_scale: float = 1.0,
        *,
        provider: str = "mock",
        model: str = "mock-deterministic-v1",
        credential_env_name: str | None = None,
        api_key: str | None = None,
        enabled: bool = True,
    ):
        self.lane_id = lane_id
        self.provider = provider
        self.model = model
        self.credential_env_name = credential_env_name
        self.api_key = api_key
        self.rpm = rpm
        self.enabled = enabled
        self.interval = (60.0 / rpm) * time_scale if rpm > 0 else 0
        self.last_dispatch_time: float | None = None

    def __repr__(self) -> str:
        credential_state = "configured" if self.api_key else "not-configured"
        return (
            f"QuotaLane(lane_id={self.lane_id!r}, provider={self.provider!r}, "
            f"model={self.model!r}, credential={credential_state!r}, rpm={self.rpm!r}, "
            f"enabled={self.enabled!r})"
        )

    async def wait_for_cooldown(self, get_time=time.monotonic, sleep=asyncio.sleep):
        if not self.enabled:
            raise RuntimeError(f"Quota lane {self.lane_id} is disabled")
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
