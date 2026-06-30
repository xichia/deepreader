import asyncio
from collections import deque
from contextlib import asynccontextmanager
import random
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
        provider_alias: str | None = None,
        rate_limit_cooldown_seconds: float = 0.0,
        retry_backoff_base_seconds: float = 0.0,
        jitter_ratio: float = 0.2,
        enabled: bool = True,
        adaptive_rpm_enabled: bool = False,
        adaptive_rpm_success_threshold: int = 5,
        adaptive_rpm_max: int | None = None,
        adaptive_rpm_backoff_factor: float = 0.5,
    ):
        self.lane_id = lane_id
        self.provider = provider
        self.provider_alias = provider_alias or lane_id
        self.model = model
        self.credential_env_name = credential_env_name
        self.api_key = api_key
        self.time_scale = time_scale
        self.base_rpm = rpm
        self.current_rpm = rpm
        self.adaptive_rpm_enabled = adaptive_rpm_enabled
        self.adaptive_rpm_success_threshold = max(1, adaptive_rpm_success_threshold)
        self.adaptive_rpm_max = max(1, adaptive_rpm_max or rpm)
        self.adaptive_rpm_backoff_factor = min(1.0, max(0.01, adaptive_rpm_backoff_factor))
        self.success_streak = 0
        self.adaptive_adjustment_count = 0
        self.enabled = enabled
        self._set_current_rpm(rpm)
        self.rate_limit_cooldown_seconds = max(0.0, rate_limit_cooldown_seconds) * time_scale
        self.retry_backoff_base_seconds = max(0.0, retry_backoff_base_seconds) * time_scale
        self.jitter_ratio = max(0.0, jitter_ratio)
        self.window_seconds = 60.0 * self.time_scale
        self.dispatch_history: deque[float] = deque()
        self.last_dispatch_time: float | None = None
        self.stagger_until: float | None = None
        self.cooldown_until: float | None = None
        self.cooldown_reason: str | None = None
        self.rate_limit_streak = 0
        self.max_in_flight = 1
        self._in_flight = asyncio.Semaphore(self.max_in_flight)
        self._reserved = False

    def _set_current_rpm(self, rpm: int) -> None:
        self.current_rpm = max(1, rpm)
        self.rpm = self.current_rpm
        self.interval = (60.0 / self.current_rpm) * self.time_scale if self.current_rpm > 0 else 0

    def record_success(self) -> bool:
        """Record a successful provider call and maybe increase this alias RPM.

        Returns True if RPM changed.
        """
        self.rate_limit_streak = 0
        if not self.adaptive_rpm_enabled:
            return False
        self.success_streak += 1
        if self.success_streak >= self.adaptive_rpm_success_threshold and self.current_rpm < self.adaptive_rpm_max:
            self._set_current_rpm(self.current_rpm + 1)
            self.success_streak = 0
            self.adaptive_adjustment_count += 1
            return True
        return False

    def record_rate_limit_response(self) -> bool:
        """Record a provider 429 and maybe reduce this alias RPM.

        Returns True if RPM changed.
        """
        self.success_streak = 0
        self.rate_limit_streak += 1
        if not self.adaptive_rpm_enabled:
            return False
        new_rpm = max(self.base_rpm, int(self.current_rpm * self.adaptive_rpm_backoff_factor))
        if new_rpm != self.current_rpm:
            self._set_current_rpm(new_rpm)
            self.adaptive_adjustment_count += 1
            return True
        return False

    def __repr__(self) -> str:
        credential_state = "configured" if self.api_key else "not-configured"
        return (
            f"QuotaLane(lane_id={self.lane_id!r}, provider={self.provider!r}, "
            f"provider_alias={self.provider_alias!r}, model={self.model!r}, "
            f"credential={credential_state!r}, rpm={self.rpm!r}, enabled={self.enabled!r})"
        )

    @asynccontextmanager
    async def provider_call_slot(self):
        """Limit a provider identity to one in-flight request."""

        async with self._in_flight:
            self._reserved = False
            yield

    def set_initial_stagger(self, start_time: float, offset_seconds: float) -> None:
        """Delay this lane's first dispatch by a deterministic scheduler offset."""

        offset = max(0.0, offset_seconds)
        self.stagger_until = start_time + offset if offset else None

    def reserve(self, now: float) -> bool:
        """Reserve an available lane until its provider-call slot is entered."""

        if (
            not self.enabled
            or self._reserved
            or self._in_flight.locked()
            or self.get_available_at(now) > now
        ):
            return False
        self._reserved = True
        return True

    def release_reservation(self) -> None:
        self._reserved = False

    def defer_after_rate_limit(
        self,
        attempt_count: int,
        *,
        get_time=time.monotonic,
        random_value=random.random,
    ) -> float:
        """Apply an independent, jittered cooldown to this provider identity."""

        exponent = max(attempt_count - 1, 0)
        base_delay = max(self.interval, self.rate_limit_cooldown_seconds) * (2**exponent)
        jitter = base_delay * self.jitter_ratio * random_value()
        delay = base_delay + jitter
        self.cooldown_until = max(self.cooldown_until or 0.0, get_time() + delay)
        self.cooldown_reason = "provider_rate_limited"
        return delay

    def defer_before_retry(
        self,
        attempt_count: int,
        *,
        get_time=time.monotonic,
        random_value=random.random,
    ) -> float:
        """Spread non-rate-limit retries so failed batches do not synchronize."""

        base_delay = self.retry_backoff_base_seconds * (2 ** max(attempt_count - 1, 0))
        jitter = base_delay * self.jitter_ratio * random_value()
        delay = base_delay + jitter
        self.cooldown_until = max(self.cooldown_until or 0.0, get_time() + delay)
        self.cooldown_reason = "retry_backoff"
        return delay

    def is_rate_limit_cooling_down(self, *, get_time=time.monotonic) -> bool:
        return (
            self.cooldown_reason == "provider_rate_limited"
            and self.cooldown_until is not None
            and self.cooldown_until > get_time()
        )

    def is_in_flight(self) -> bool:
        return self._reserved or self._in_flight.locked()

    def _prune_dispatch_history(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self.dispatch_history and self.dispatch_history[0] <= cutoff:
            self.dispatch_history.popleft()

    def get_request_count_in_window(self, now: float) -> int:
        self._prune_dispatch_history(now)
        return len(self.dispatch_history)

    def _get_rolling_window_available_at(self, now: float) -> float:
        self._prune_dispatch_history(now)
        if len(self.dispatch_history) < self.current_rpm:
            return now

        # If adaptive RPM has fallen below the number of recent attempts, enough
        # of the oldest requests must expire to leave room under the new limit.
        limiting_index = len(self.dispatch_history) - self.current_rpm
        return self.dispatch_history[limiting_index] + self.window_seconds

    def get_available_at(self, now: float) -> float:
        interval_ready_at = (
            self.last_dispatch_time + self.interval
            if self.last_dispatch_time is not None
            else now
        )
        rolling_ready_at = self._get_rolling_window_available_at(now)
        return max(
            interval_ready_at,
            rolling_ready_at,
            self.stagger_until or now,
            self.cooldown_until or now,
        )

    def get_unavailability_reason(self, now: float) -> str:
        if not self.enabled:
            return "disabled"
        if self.is_in_flight():
            return "in_flight"
        if self.cooldown_until is not None and self.cooldown_until > now:
            return "provider_cooldown"
        if self.stagger_until is not None and self.stagger_until > now:
            return "lane_stagger"
        interval_ready_at = (
            self.last_dispatch_time + self.interval
            if self.last_dispatch_time is not None
            else now
        )
        if max(interval_ready_at, self._get_rolling_window_available_at(now)) > now:
            return "rpm_window"
        return "none"

    def get_availability_diagnostic(
        self,
        now: float,
    ) -> dict[str, int | float | str | bool | None]:
        """Return safe, per-alias scheduler state without credential material."""

        reason = self.get_unavailability_reason(now)
        available_at = self.get_available_at(now)
        return {
            "available": reason == "none",
            "reason": reason,
            "available_in_seconds": (
                None if reason == "disabled" else round(max(0.0, available_at - now), 6)
            ),
            "requests_in_rolling_window": self.get_request_count_in_window(now),
            "rolling_window_seconds": self.window_seconds,
            "current_rpm": self.current_rpm,
        }

    async def wait_for_cooldown(self, get_time=time.monotonic, sleep=asyncio.sleep) -> float:
        if not self.enabled:
            raise RuntimeError(f"Quota lane {self.lane_id} is disabled")

        now = get_time()
        ready_at = self.get_available_at(now)
        delay = max(0.0, ready_at - now)
        if delay:
            await sleep(delay)

        self.last_dispatch_time = get_time()
        self.dispatch_history.append(self.last_dispatch_time)
        if self.stagger_until is not None and self.last_dispatch_time >= self.stagger_until:
            self.stagger_until = None
        if self.cooldown_until is not None and self.last_dispatch_time >= self.cooldown_until:
            self.cooldown_until = None
            self.cooldown_reason = None
        return delay
