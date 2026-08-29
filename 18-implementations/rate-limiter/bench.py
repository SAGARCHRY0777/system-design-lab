#!/usr/bin/env python3
"""Measure the three limiters against each other.

Numbers here are produced by running this file. Nothing is estimated. Run it
yourself -- absolute throughput depends entirely on your machine, and the only
figure worth carrying away is the RATIO between the three.

    python bench.py
"""

from __future__ import annotations

import platform
import sys
import time

from rate_limiter import FixedWindowCounter, SlidingWindowLog, TokenBucket

N = 200_000


def bench(name: str, call) -> tuple[str, float, float]:
    # One warm pass so the first measured call is not paying import and
    # first-touch costs that have nothing to do with the algorithm.
    for i in range(1000):
        call(i / 1000.0)

    start = time.perf_counter()
    for i in range(N):
        call(i / 10_000.0)
    elapsed = time.perf_counter() - start

    per_op_us = elapsed / N * 1e6
    ops_per_s = N / elapsed
    print(f"  {name:<24} {per_op_us:7.3f} µs/op   {ops_per_s:>12,.0f} ops/s")
    return name, per_op_us, ops_per_s


def main() -> int:
    print(f"machine : {platform.processor() or platform.machine()}")
    print(f"python  : {platform.python_version()} ({platform.system()} {platform.release()})")
    print(f"ops     : {N:,} per limiter\n")

    tb = TokenBucket(rate=100_000, capacity=1000)
    sw = SlidingWindowLog(limit=1000, window_s=1.0)
    fw = FixedWindowCounter(limit=1000, window_s=1.0)

    print("throughput (single-threaded, uncontended lock)")
    results = [
        bench("TokenBucket", lambda t: tb.allow(now=t)),
        bench("SlidingWindowLog", lambda t: sw.allow(now=t)),
        bench("FixedWindowCounter", lambda t: fw.allow(now=t)),
    ]

    fastest = min(r[1] for r in results)
    print("\nrelative cost")
    for name, per_op, _ in results:
        print(f"  {name:<24} {per_op / fastest:5.2f}x")

    print("\nmemory shape (what actually decides this at scale)")
    print("  TokenBucket           O(1)     two floats per key")
    print("  FixedWindowCounter    O(1)     one int per key")
    print(f"  SlidingWindowLog      O(limit) up to {sw.limit:,} timestamps per key")
    print(
        f"\n  At 1M tracked keys that is ~16 MB for the O(1) limiters and "
        f"~{1_000_000 * sw.limit * 8 / 1e9:.0f} GB for the log."
    )
    print("  Throughput is not why nobody ships the sliding window log. Memory is.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
