"""Tests that assert the *defining properties*, not just that the code runs.

Every test injects `now` rather than sleeping. A limiter tested with real sleeps
is slow and flaky, and the injected clock lets us assert things about a boundary
crossing that would otherwise be impossible to hit reliably.
"""

from __future__ import annotations

import pytest

from rate_limiter import FixedWindowCounter, SlidingWindowLog, TokenBucket


# --------------------------------------------------------------------------- #
# Token bucket                                                                 #
# --------------------------------------------------------------------------- #

def test_burst_is_allowed_up_to_capacity():
    b = TokenBucket(rate=10, capacity=5)
    assert [b.allow(now=100.0) for _ in range(5)] == [True] * 5
    assert b.allow(now=100.0) is False


def test_refill_is_proportional_to_elapsed_time():
    b = TokenBucket(rate=10, capacity=10)
    for _ in range(10):
        b.allow(now=0.0)
    assert b.allow(now=0.0) is False

    # 0.25s at 10/s = 2.5 tokens, so exactly two more requests.
    assert b.allow(now=0.25) is True
    assert b.allow(now=0.25) is True
    assert b.allow(now=0.25) is False


def test_tokens_never_exceed_capacity():
    """Idle time must not bank unlimited credit -- otherwise a client silent for
    an hour could flatten you the moment it wakes up."""
    b = TokenBucket(rate=10, capacity=5)
    b.allow(now=0.0)
    assert b.allow(now=10_000.0) is True
    assert sum(b.allow(now=10_000.0) for _ in range(100)) == 4


def test_long_run_average_converges_on_the_configured_rate():
    """The property that actually matters: over a long window, throughput is
    the rate. Deleting the refill cap would still pass the burst tests."""
    b = TokenBucket(rate=100, capacity=10)
    allowed = sum(b.allow(now=t / 1000.0) for t in range(10_000))  # 10s, 1ms apart
    # 10s x 100/s = 1000, plus the initial capacity of 10.
    assert 1000 <= allowed <= 1010


def test_retry_after_is_zero_when_allowed_and_accurate_when_not():
    b = TokenBucket(rate=2, capacity=1)
    assert b.retry_after(now=0.0) == 0.0
    assert b.allow(now=0.0) is True
    assert b.retry_after(now=0.0) == pytest.approx(0.5)


def test_cost_greater_than_one_is_charged_correctly():
    b = TokenBucket(rate=1, capacity=10)
    assert b.allow(cost=7, now=0.0) is True
    assert b.allow(cost=7, now=0.0) is False
    assert b.allow(cost=3, now=0.0) is True


@pytest.mark.parametrize("rate,capacity", [(0, 1), (-1, 1), (1, 0), (1, -5)])
def test_invalid_configuration_is_rejected(rate, capacity):
    with pytest.raises(ValueError):
        TokenBucket(rate=rate, capacity=capacity)


# --------------------------------------------------------------------------- #
# Sliding window                                                               #
# --------------------------------------------------------------------------- #

def test_sliding_window_enforces_the_limit():
    w = SlidingWindowLog(limit=3, window_s=1.0)
    assert [w.allow(now=0.0) for _ in range(3)] == [True] * 3
    assert w.allow(now=0.0) is False


def test_sliding_window_frees_capacity_as_hits_age_out():
    w = SlidingWindowLog(limit=3, window_s=1.0)
    for t in (0.0, 0.1, 0.2):
        assert w.allow(now=t) is True
    assert w.allow(now=0.5) is False
    # The 0.0 hit leaves the window just after t=1.0.
    assert w.allow(now=1.01) is True


def test_sliding_window_retry_after_points_at_the_oldest_hit():
    w = SlidingWindowLog(limit=1, window_s=2.0)
    w.allow(now=10.0)
    assert w.retry_after(now=10.5) == pytest.approx(1.5)


# --------------------------------------------------------------------------- #
# The boundary burst -- why the fixed window is the wrong default              #
# --------------------------------------------------------------------------- #

def test_fixed_window_allows_double_the_limit_across_a_boundary():
    """This is the flaw, asserted rather than described.

    limit=5/second, yet 10 requests succeed inside ~0.02s because they straddle
    a window boundary."""
    f = FixedWindowCounter(limit=5, window_s=1.0)
    late = sum(f.allow(now=0.99) for _ in range(5))     # end of window 0
    early = sum(f.allow(now=1.001) for _ in range(5))   # start of window 1
    assert late == 5
    assert early == 5
    assert late + early == 10  # 2x the configured limit, ~20ms apart


def test_sliding_window_does_not_have_that_flaw():
    """Same traffic, same limit, correct answer -- this is the reason to pay
    the extra memory."""
    w = SlidingWindowLog(limit=5, window_s=1.0)
    late = sum(w.allow(now=0.99) for _ in range(5))
    early = sum(w.allow(now=1.001) for _ in range(5))
    assert late == 5
    assert early == 0


def test_token_bucket_also_resists_the_boundary_burst():
    b = TokenBucket(rate=5, capacity=5)
    late = sum(b.allow(now=0.99) for _ in range(5))
    early = sum(b.allow(now=1.001) for _ in range(5))
    assert late == 5
    assert early == 0  # only ~0.055 tokens accrued in 11ms
