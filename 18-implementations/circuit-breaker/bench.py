#!/usr/bin/env python3
"""Measure the conversion: how much wall-clock a breaker saves, and what it costs.

Numbers here are produced by running this file against a dependency that
genuinely blocks. Nothing is estimated. The slow path really sleeps -- that is
the whole measurement, and it is why this benchmark takes a few seconds where
the others take milliseconds.

(The *tests* never sleep; they drive an injected clock. Sleeping belongs in a
benchmark, where wall-clock is the thing being measured, and nowhere else.)

    python bench.py
"""

from __future__ import annotations

import platform
import statistics
import sys
import time

from circuit_breaker import CircuitBreaker, CircuitOpenError

CALLS = 200
LATENCY_S = 0.010     # a dependency that hangs for 10ms before failing
OVERHEAD_OPS = 200_000
ROUNDS = 3


def best_of(fn, ops: int) -> float:
    """Per-op cost in microseconds, best of `ROUNDS`.

    The minimum, not the mean. A slower round is not the code being slower --
    it is the operating system giving the CPU to something else, and averaging
    that in measures background load rather than the algorithm. The overhead
    figures below are a comparison against a bare function call, and a
    comparison distorted by whatever else the machine is doing is worthless.
    """
    best = float("inf")
    for _ in range(ROUNDS):
        start = time.perf_counter()
        fn(ops)
        best = min(best, time.perf_counter() - start)
    return best / ops * 1e6


def slow_and_broken() -> None:
    """Accepts the connection, holds the thread, then fails. The bad case.

    A refused connection returns in microseconds and is nearly harmless. This
    is the failure that fills thread pools.
    """
    time.sleep(LATENCY_S)
    raise TimeoutError("upstream did not answer")


def run_unprotected() -> tuple[float, list[float], int]:
    latencies = []
    reached = 0
    start = time.perf_counter()
    for _ in range(CALLS):
        t0 = time.perf_counter()
        try:
            slow_and_broken()
        except TimeoutError:
            reached += 1
        latencies.append((time.perf_counter() - t0) * 1000)
    return time.perf_counter() - start, latencies, reached


def run_protected() -> tuple[float, list[float], int]:
    breaker = CircuitBreaker(failure_threshold=5, reset_timeout_s=60.0)
    latencies = []
    reached = 0
    start = time.perf_counter()
    for _ in range(CALLS):
        t0 = time.perf_counter()
        try:
            breaker.call(slow_and_broken)
        except TimeoutError:
            reached += 1
        except CircuitOpenError:
            pass
        latencies.append((time.perf_counter() - t0) * 1000)
    return time.perf_counter() - start, latencies, reached


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * p))]


def main() -> int:
    print(f"machine : {platform.processor() or platform.machine()}")
    print(f"python  : {platform.python_version()} ({platform.system()} {platform.release()})")
    print(f"scenario: {CALLS} calls to a dependency that hangs "
          f"{LATENCY_S * 1000:.0f}ms then fails\n")

    print("SLOW FAILURE vs FAST FAILURE  (real wall-clock, the dependency really blocks)")
    bare_total, bare_lat, bare_reached = run_unprotected()
    brk_total, brk_lat, brk_reached = run_protected()

    print(f"  {'':<14} {'total':>9} {'mean':>10} {'p50':>10} {'p99':>10}   reached dep")
    print(f"  {'no breaker':<14} {bare_total:>8.3f}s {statistics.fmean(bare_lat):>8.3f}ms"
          f" {percentile(bare_lat, 0.50):>8.3f}ms {percentile(bare_lat, 0.99):>8.3f}ms"
          f"   {bare_reached:>6}")
    print(f"  {'with breaker':<14} {brk_total:>8.3f}s {statistics.fmean(brk_lat):>8.3f}ms"
          f" {percentile(brk_lat, 0.50):>8.3f}ms {percentile(brk_lat, 0.99):>8.3f}ms"
          f"   {brk_reached:>6}")

    print(f"\n  {bare_total / brk_total:,.0f}x less blocked thread time.")
    print(f"  Median latency {percentile(bare_lat, 0.50):.3f}ms -> "
          f"{percentile(brk_lat, 0.50):.4f}ms: a caller can act on the second one.")
    print(f"  {bare_reached} requests reached the failing dependency without a breaker, "
          f"{brk_reached} with one --")
    print("  which is also why its own error-rate dashboard looks healthy during an outage.")

    print("\n  On one thread this is a latency win. On a pool of 200 threads it is the")
    print("  difference between a degraded feature and a caller that has no threads left.")

    # ---------------------------------------------------------------------- #
    print(f"\nBREAKER OVERHEAD  (what you pay on the happy path, best of {ROUNDS})")
    closed = CircuitBreaker(failure_threshold=1_000_000_000)
    opened = CircuitBreaker(failure_threshold=1, reset_timeout_s=1e9)
    opened.record_failure()

    for _ in range(2000):
        closed.allow()
        opened.allow()

    def noop() -> None:
        """A dependency with zero cost, so the measurement is pure wrapper."""

    # Plain loops, not comprehensions: a comprehension would add list growth to
    # every figure and the wrapper cost is measured as a DIFFERENCE against the
    # bare call, so anything common to both must stay out of both.
    def loop_allow_closed(n: int) -> None:
        for _ in range(n):
            closed.allow()

    def loop_allow_open(n: int) -> None:
        for _ in range(n):
            opened.allow()

    def loop_call(n: int) -> None:
        for _ in range(n):
            closed.call(noop)

    def loop_raw(n: int) -> None:
        for _ in range(n):
            noop()

    closed_us = best_of(loop_allow_closed, OVERHEAD_OPS)
    open_us = best_of(loop_allow_open, OVERHEAD_OPS)
    call_us = best_of(loop_call, OVERHEAD_OPS)
    raw_us = best_of(loop_raw, OVERHEAD_OPS)

    print(f"  {'allow(), closed':<26} {closed_us:7.3f} us/op")
    print(f"  {'allow(), open (rejecting)':<26} {open_us:7.3f} us/op")
    print(f"  {'call() wrapping a no-op':<26} {call_us:7.3f} us/op")
    print(f"  {'the no-op alone':<26} {raw_us:7.3f} us/op")
    print(f"\n  Wrapper cost: {call_us - raw_us:.3f} us per call. Against a network hop of")
    print(f"  even 1ms that is {(call_us - raw_us) / 1000:.4%} overhead -- free, in the sense that matters.")
    print(f"  Rejecting costs {open_us:.3f} us against {LATENCY_S * 1e6:,.0f} us of hanging: "
          f"~{LATENCY_S * 1e6 / open_us:,.0f}x cheaper.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
