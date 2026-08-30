"""A circuit breaker: three states, and exactly one job.

Its job is not to stop calls. Its job is to turn a **slow** failure into a
**fast** one, because fast failure is the only kind a caller can do anything
about.

The failure people design for is a refused connection, which returns in
microseconds and is nearly harmless. The failure that actually takes systems
down is a dependency that has gone *slow*: it still accepts connections, it
still eventually answers, it just takes eight seconds instead of eight
milliseconds. Every caller thread now sits blocked on a socket. The thread pool
fills. Requests that never needed that dependency start queuing behind the ones
that do. The caller falls over -- while its own code is fine and its own
dependency is technically still up. That is how one degraded service takes down
everything upstream of it.

A caller that fails in twenty microseconds can serve a stale cache entry,
degrade the feature, return a partial response, or shed the request. A caller
blocked for thirty seconds can do none of those; it can only run out of
threads. bench.py measures that conversion directly, and it is a factor of
several hundred.

    CLOSED     calls pass through; consecutive failures are counted
    OPEN       calls are rejected WITHOUT being made; a cooldown runs
    HALF_OPEN  after the cooldown, ONE trial call is admitted
               success -> CLOSED; failure -> OPEN, cooldown restarts

Half-open is the whole design. Without it there are only two options and both
are bad: stay open forever and never recover automatically, or slam the
recovering dependency with full production traffic the instant the timer fires
and knock it straight back over. Half-open asks the cheapest possible question
-- one request -- and lets the answer decide.

A slow *success* is counted as a failure (`slow_call_threshold_s`). Without
that rule a degraded dependency never trips the breaker at all: it never
returns an error, it just takes eight seconds, forever, while every caller
blocks. This is the mechanism by which the breaker sees a brownout.

Every state-machine method takes `now=` so tests can cross a cooldown boundary
without sleeping. Stdlib only, single process, thread-safe via one lock.
Distributed state, real timeout enforcement, and rolling-window error rates are
deliberately absent; see README.md.
"""

from __future__ import annotations

import enum
import threading
import time
from typing import Any, Callable


class State(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised instead of calling through. Carries `retry_after`.

    Modelled on the rate limiter's `retry_after` for the same reason: a
    component that says "no" without saying "when" guarantees the caller
    retries immediately, and a retry storm against a struggling dependency is
    the exact outcome the breaker exists to prevent.
    """

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"circuit is open; retry in {retry_after:.3f}s")
        self.retry_after = retry_after


class CircuitBreaker:
    """Three-state breaker over a single dependency.

    One breaker per dependency, never one per process: a breaker shared across
    two dependencies opens for a healthy one because an unhealthy one failed,
    which is a self-inflicted outage.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        reset_timeout_s: float = 30.0,
        success_threshold: int = 1,
        half_open_max_calls: int = 1,
        slow_call_threshold_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be at least 1")
        if reset_timeout_s <= 0:
            raise ValueError("reset_timeout_s must be positive")
        if success_threshold < 1:
            raise ValueError("success_threshold must be at least 1")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be at least 1")

        self.failure_threshold = failure_threshold
        self.reset_timeout_s = reset_timeout_s
        self.success_threshold = success_threshold
        self.half_open_max_calls = half_open_max_calls
        self.slow_call_threshold_s = slow_call_threshold_s
        self._clock = clock

        self._state = State.CLOSED
        self._failures = 0          # consecutive, in CLOSED
        self._successes = 0         # consecutive, in HALF_OPEN
        self._opened_at = 0.0
        self._trials_in_flight = 0
        self._lock = threading.RLock()

        self.allowed = 0
        self.rejected = 0
        self.failures_total = 0
        self.successes_total = 0
        self.slow_calls = 0
        self.trips = 0

    def _t(self, now: float | None) -> float:
        return self._clock() if now is None else now

    # ----------------------------------------------------------- transitions

    def _advance(self, now: float) -> State:
        """Apply any transition that time alone has made due.

        A breaker's state is partly a function of the clock, not only of
        events: OPEN becomes HALF_OPEN because a cooldown elapsed, and no call
        arrives to make that happen. Evaluating it on read is what avoids a
        timer thread per breaker -- and a service with three hundred
        dependencies has three hundred breakers.
        """
        if self._state is State.OPEN and now - self._opened_at >= self.reset_timeout_s:
            self._state = State.HALF_OPEN
            self._successes = 0
            self._trials_in_flight = 0
        return self._state

    def _open(self, now: float) -> None:
        self._state = State.OPEN
        self._opened_at = now
        self._failures = 0
        self._successes = 0
        self._trials_in_flight = 0
        self.trips += 1

    def _close(self) -> None:
        self._state = State.CLOSED
        self._failures = 0
        self._successes = 0
        self._trials_in_flight = 0

    # ------------------------------------------------------------ primitives

    def state(self, now: float | None = None) -> State:
        """Current state, evaluated against the clock. May transition."""
        with self._lock:
            return self._advance(self._t(now))

    def allow(self, now: float | None = None) -> bool:
        """Ask permission. Consumes a half-open trial slot if one is granted.

        This is where the fast failure happens: returning False costs a lock, a
        comparison and a counter. Nothing is dialled, nothing is waited on.
        """
        with self._lock:
            t = self._t(now)
            state = self._advance(t)

            if state is State.CLOSED:
                self.allowed += 1
                return True

            if state is State.OPEN:
                self.rejected += 1
                return False

            # HALF_OPEN: admit a strictly bounded number of probes and reject
            # everything else. The point of half-open is to ask the dependency
            # one question -- resuming traffic to find out how it is doing is
            # how you knock over something that was halfway back up.
            if self._trials_in_flight < self.half_open_max_calls:
                self._trials_in_flight += 1
                self.allowed += 1
                return True
            self.rejected += 1
            return False

    def record_success(
        self,
        now: float | None = None,
        duration_s: float | None = None,
    ) -> None:
        """Report that a call returned. A slow return is reported as a failure."""
        with self._lock:
            t = self._t(now)

            if (
                self.slow_call_threshold_s is not None
                and duration_s is not None
                and duration_s >= self.slow_call_threshold_s
            ):
                # The brownout case. It returned a 200 and it took eight
                # seconds; from upstream that is indistinguishable from being
                # down, and worse, because it holds a thread while it happens.
                self.slow_calls += 1
                self._record_failure_locked(t)
                return

            self.successes_total += 1

            if self._state is State.OPEN:
                # A call that started while the breaker was closed can return
                # after it has tripped. Its result is stale evidence about a
                # dependency we have already judged, so it must not close the
                # breaker behind the cooldown's back.
                return

            if self._state is State.HALF_OPEN:
                self._trials_in_flight = max(0, self._trials_in_flight - 1)
                self._successes += 1
                if self._successes >= self.success_threshold:
                    self._close()
            else:
                # Consecutive, not cumulative: one success means the dependency
                # is answering, and a count that never resets would trip the
                # breaker on five failures spread across a month.
                self._failures = 0

    def record_failure(self, now: float | None = None) -> None:
        with self._lock:
            self._record_failure_locked(self._t(now))

    def _record_failure_locked(self, now: float) -> None:
        self.failures_total += 1

        if self._state is State.HALF_OPEN:
            # One failed probe is enough. The dependency answered the question
            # and the answer was no; waiting for a second probe just means one
            # more caller blocked on a dependency we already know is unwell.
            self._trials_in_flight = max(0, self._trials_in_flight - 1)
            self._open(now)
            return

        if self._state is State.OPEN:
            return  # late result from a call already in flight when we tripped

        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._open(now)

    def retry_after(self, now: float | None = None) -> float:
        """Seconds until the next probe is admitted. 0.0 if calls pass now."""
        with self._lock:
            t = self._t(now)
            if self._advance(t) is not State.OPEN:
                return 0.0
            return max(0.0, self._opened_at + self.reset_timeout_s - t)

    # ------------------------------------------------------------ convenience

    def call(self, fn: Callable[..., Any], *args: Any, now: float | None = None, **kwargs: Any) -> Any:
        """Run `fn` through the breaker, or raise `CircuitOpenError` without calling.

        `now` is consumed by the breaker and never forwarded. If your callee
        genuinely takes a `now` keyword, drive the primitives (`allow`,
        `record_success`, `record_failure`) directly -- they are the real API
        and this is only a wrapper over them.
        """
        t = self._t(now)
        if not self.allow(now=t):
            raise CircuitOpenError(self.retry_after(now=t))

        started = self._clock()
        try:
            result = fn(*args, **kwargs)
        except Exception:
            # Any exception counts as a failure, which is the wrong default for
            # production and the right one for a teaching implementation. A 404
            # from the dependency means YOUR request was wrong, not that the
            # dependency is unhealthy -- counting it will trip the breaker on a
            # bug in your own code and take out a service that is perfectly
            # fine. Real deployments classify.
            self.record_failure(now=t)
            raise

        self.record_success(now=t, duration_s=self._clock() - started)
        return result

    # ------------------------------------------------------------ inspection

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "state": self._state.value,
                "allowed": self.allowed,
                "rejected": self.rejected,
                "failures": self.failures_total,
                "successes": self.successes_total,
                "slow_calls": self.slow_calls,
                "trips": self.trips,
                "consecutive_failures": self._failures,
            }

    def reset(self) -> None:
        """Force closed. For an operator override, not for the state machine."""
        with self._lock:
            self._close()

    def __repr__(self) -> str:
        return (
            f"CircuitBreaker(state={self._state.value}, trips={self.trips}, "
            f"allowed={self.allowed}, rejected={self.rejected})"
        )
