"""Two rate limiters, written to make the difference between them visible.

Both answer "may this request proceed?" and both enforce the same average rate.
They disagree completely about *bursts*, and that disagreement is the whole
lesson: choosing a rate limiter is choosing what you want to happen at the
boundary between two windows.

Stdlib only, single process. Everything a distributed limiter needs -- shared
state, clock skew, atomic check-and-decrement -- is deliberately absent; see
README.md for what production adds and why.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    """Classic token bucket: refill at a steady rate, spend one token per request.

    Allows a burst up to `capacity`, then settles to `rate` per second. That
    burst tolerance is usually what you want for user-facing APIs -- a client
    that has been quiet for a minute can fire a handful of requests at once
    without being punished for its own politeness.

    Tokens are computed lazily from elapsed time rather than by a background
    thread. A timer per bucket would not survive ten thousand buckets, and the
    arithmetic is exact either way.
    """

    rate: float           # tokens added per second
    capacity: float       # maximum tokens held, i.e. the largest burst
    _tokens: float = field(init=False)
    _last: float | None = field(init=False, default=None)
    _lock: threading.Lock = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError("rate must be positive")
        if self.capacity <= 0:
            raise ValueError("capacity must be positive")
        self._tokens = float(self.capacity)
        self._lock = threading.Lock()

    def _refill(self, now: float) -> None:
        # Anchored on first use rather than at construction, so the bucket works
        # against an injected clock as well as the real one. Seeding _last from
        # time.monotonic() here would make every injected timestamp look like it
        # was in the distant past, and the bucket would silently never refill.
        if self._last is None:
            self._last = now
            return
        elapsed = now - self._last
        if elapsed <= 0:
            return
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last = now

    def allow(self, cost: float = 1.0, now: float | None = None) -> bool:
        """True if the request may proceed, spending `cost` tokens."""
        with self._lock:
            self._refill(time.monotonic() if now is None else now)
            if self._tokens >= cost:
                self._tokens -= cost
                return True
            return False

    def retry_after(self, cost: float = 1.0, now: float | None = None) -> float:
        """Seconds until `cost` tokens exist. 0.0 if allowed right now.

        Worth returning to callers: a limiter that says "no" without saying
        "when" guarantees the client retries immediately and wastes both your
        time and its own.
        """
        with self._lock:
            self._refill(time.monotonic() if now is None else now)
            if self._tokens >= cost:
                return 0.0
            return (cost - self._tokens) / self.rate

    @property
    def tokens(self) -> float:
        with self._lock:
            self._refill(time.monotonic())
            return self._tokens


class SlidingWindowLog:
    """Exact count over a moving window, by remembering every timestamp.

    Precise where a fixed window is not: a fixed counter resetting at each
    boundary lets a client send `limit` requests at 0:59 and `limit` again at
    1:01 -- double the intended rate across two seconds. This cannot.

    The cost is memory proportional to the limit, per key, which is why
    production systems usually accept the approximation instead.
    """

    def __init__(self, limit: int, window_s: float) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_s <= 0:
            raise ValueError("window_s must be positive")
        self.limit = limit
        self.window_s = window_s
        self._hits: deque[float] = deque()
        self._lock = threading.Lock()

    def _evict(self, now: float) -> None:
        cutoff = now - self.window_s
        while self._hits and self._hits[0] <= cutoff:
            self._hits.popleft()

    def allow(self, now: float | None = None) -> bool:
        t = time.monotonic() if now is None else now
        with self._lock:
            self._evict(t)
            if len(self._hits) < self.limit:
                self._hits.append(t)
                return True
            return False

    def retry_after(self, now: float | None = None) -> float:
        t = time.monotonic() if now is None else now
        with self._lock:
            self._evict(t)
            if len(self._hits) < self.limit:
                return 0.0
            # Room appears when the oldest hit leaves the window.
            return max(0.0, self._hits[0] + self.window_s - t)

    @property
    def count(self) -> int:
        with self._lock:
            self._evict(time.monotonic())
            return len(self._hits)


class FixedWindowCounter:
    """The naive one, included ONLY to demonstrate its flaw.

    Counts per aligned window and resets at the boundary. Cheap -- one integer
    per key -- and wrong at exactly the moment it matters: a client can send
    2 x limit requests across a boundary. test_rate_limiter.py proves it.

    Do not reach for this because it appears in the list; reach for it when you
    have decided the boundary burst is acceptable.
    """

    def __init__(self, limit: int, window_s: float) -> None:
        self.limit = limit
        self.window_s = window_s
        self._window = -1
        self._count = 0
        self._lock = threading.Lock()

    def allow(self, now: float | None = None) -> bool:
        t = time.monotonic() if now is None else now
        w = int(t // self.window_s)
        with self._lock:
            if w != self._window:
                self._window = w
                self._count = 0
            if self._count < self.limit:
                self._count += 1
                return True
            return False
