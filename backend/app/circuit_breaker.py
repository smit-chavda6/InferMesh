"""Per-provider circuit breaker.

The dashboard already *detects* three-consecutive failures for its health view;
this makes the same signal *act* on routing. When a provider trips, the router
skips it (falling through to the rest of the chain) until a cooldown elapses,
then lets a single probe through (``half_open``). Success closes the circuit; a
failed probe re-opens it.

State is process-local and best-effort — a fresh process starts all circuits
closed. That's fine: the breaker is a fast-failover optimisation, not a
correctness mechanism.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from app import metrics
from app.logging_config import get_logger

log = get_logger(__name__)

State = Literal["closed", "open", "half_open"]


@dataclass(slots=True)
class _Circuit:
    state: State = "closed"
    consecutive_failures: int = 0
    opened_at: float = 0.0


@dataclass(slots=True)
class CircuitBreaker:
    failure_threshold: int = 5
    reset_seconds: float = 30.0
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)
    _circuits: dict[str, _Circuit] = field(default_factory=dict, repr=False)

    def _c(self, provider: str) -> _Circuit:
        return self._circuits.setdefault(provider, _Circuit())

    def _clock(self) -> float:
        return self.clock()

    def _transition(self, provider: str, c: _Circuit, state: State) -> None:
        if c.state != state:
            log.info("circuit.transition", provider=provider, to=state, was=c.state)
        c.state = state
        metrics.set_circuit_state(provider, state)

    def allow(self, provider: str) -> bool:
        """True if a call to ``provider`` should be attempted right now."""
        c = self._c(provider)
        if c.state == "open":
            if self._clock() - c.opened_at >= self.reset_seconds:
                self._transition(provider, c, "half_open")
                return True
            return False
        return True  # closed or half_open both allow a call

    def record_success(self, provider: str) -> None:
        c = self._c(provider)
        c.consecutive_failures = 0
        if c.state != "closed":
            self._transition(provider, c, "closed")

    def record_failure(self, provider: str) -> None:
        c = self._c(provider)
        c.consecutive_failures += 1
        if c.state == "half_open" or c.consecutive_failures >= self.failure_threshold:
            c.opened_at = self._clock()
            self._transition(provider, c, "open")

    def state_of(self, provider: str) -> State:
        return self._c(provider).state

    def snapshot(self) -> dict[str, dict[str, object]]:
        return {
            p: {
                "state": c.state,
                "consecutive_failures": c.consecutive_failures,
                "retry_in_seconds": (
                    round(max(self.reset_seconds - (self._clock() - c.opened_at), 0.0), 1)
                    if c.state == "open"
                    else 0.0
                ),
            }
            for p, c in self._circuits.items()
        }
