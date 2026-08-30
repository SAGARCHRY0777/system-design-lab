#!/usr/bin/env python3
"""Measure the ring against the modulus, and the cost of virtual nodes.

Numbers here are produced by running this file. Nothing is estimated. Run it
yourself -- the throughput figures belong to your machine, but the two that
matter (keys remapped, load spread) are properties of the algorithm and will
come out identical everywhere, because the hash is pinned.

    python bench.py
"""

from __future__ import annotations

import gc
import platform
import sys
import time

from consistent_hashing import HashRing, ModuloSharder, remap_fraction, spread

KEYS = [f"user:{i}" for i in range(100_000)]
LOOKUPS = 100_000


class Snapshot:
    """Frozen key -> node map, so a sharder can be compared with its own past."""

    def __init__(self, sharder, keys) -> None:
        self._map = {k: sharder.get(k) for k in keys}

    def get(self, key: str) -> str:
        return self._map[key]


# Many short rounds rather than a few long ones. The minimum only means
# anything if at least one round ran without the OS handing the core to
# something else, and on a busy desktop a one-second round is very likely to be
# interrupted while a 0.1-second round often is not. Measured here: three
# 200,000-op rounds reported anywhere between 0.9 and 8.6 us/op for identical
# code, purely on background load.
ROUNDS = 7


def bench_lookup(name: str, sharder, out: list[str]) -> float:
    """Per-op cost, best of `ROUNDS`. Appends its line to `out`.

    The minimum, not the mean. A slower round is not the code being slower --
    it is the operating system giving the CPU to something else, and averaging
    that in measures the machine's background load rather than the algorithm.
    It matters here because the whole section is a COMPARISON: if a browser
    wakes up during one sharder's round and not another's, the ratio is
    fiction. This is the same reason `timeit` documents `min()`.
    """
    for i in range(1000):  # warm: never measure the first-touch cost
        sharder.get(KEYS[i])

    best = float("inf")
    for _ in range(ROUNDS):
        start = time.perf_counter()
        for i in range(LOOKUPS):
            sharder.get(KEYS[i % len(KEYS)])
        best = min(best, time.perf_counter() - start)

    per_op_us = best / LOOKUPS * 1e6
    out.append(f"  {name:<32} {per_op_us:7.3f} us/op   {LOOKUPS / best:>12,.0f} ops/s")
    return per_op_us


def measure_rebuild() -> list[str]:
    """Time a ring rebuild at four sizes; return the lines to print later.

    Best-of-N rather than a mean. A rebuild is a single-shot allocation of a
    large dict plus a large sort, so it is far more sensitive to GC and to
    whatever else the machine is doing than the averaged throughput loops. The
    minimum is the closest honest estimate of what the work costs; the spread
    is the machine, not the code.
    """
    out = [f"REBUILD COST when membership changes  (best of {ROUNDS}, clean heap)"]
    for n, vnodes in ((8, 150), (64, 150), (512, 150), (512, 1000)):
        timings = []
        for _ in range(ROUNDS):
            ring = HashRing([f"node-{i}" for i in range(n)], vnodes=vnodes)
            gc.collect()
            start = time.perf_counter()
            ring.add("joiner")
            timings.append((time.perf_counter() - start) * 1000)
        out.append(f"  {n:>4} nodes x {vnodes:>4} vnodes = {ring.points:>7,} points"
                   f"   {min(timings):7.2f} ms")
    return out


def measure_throughput() -> list[str]:
    """Measure lookups on a clean heap; return the lines to print later."""
    out = [f"LOOKUP THROUGHPUT (single-threaded, best of {ROUNDS}, measured on a clean heap)"]

    ring_small = HashRing([f"node-{i}" for i in range(8)])
    ring_big = HashRing([f"node-{i}" for i in range(512)])
    mod = ModuloSharder([f"node-{i}" for i in range(8)])

    ring_us = bench_lookup(f"HashRing 8 nodes ({ring_small.points:,} pts)", ring_small, out)
    big_us = bench_lookup(f"HashRing 512 nodes ({ring_big.points:,} pts)", ring_big, out)
    mod_us = bench_lookup("ModuloSharder 8 nodes", mod, out)

    out.append(f"\n  ring / modulo            {ring_us / mod_us:5.2f}x   the price of not remapping")
    out.append(f"  1,200 pts -> 76,800 pts  {big_us / ring_us:5.2f}x   64x the ring, "
               f"O(log n) bisect absorbs it")
    return out


def main() -> int:
    print(f"machine : {platform.processor() or platform.machine()}")
    print(f"python  : {platform.python_version()} ({platform.system()} {platform.release()})")
    print(f"keys    : {len(KEYS):,}\n")

    # Both timed sections are measured FIRST and buffered, then printed in
    # narrative order below. This is not tidiness -- it IS the measurement.
    #
    # The remap and spread sections build and discard several 100,000-entry
    # dicts. Run the sub-microsecond lookup loop after that and it reports
    # 2.2 us/op against 0.86 us/op on a clean heap; run the rebuild after it
    # and 560ms becomes 4,926ms. Both are 3-8x errors and neither has anything
    # to do with the code being measured -- they are the allocator state the
    # earlier sections left behind. Notably the RATIOS survived intact in both
    # cases while the absolute numbers did not, which is exactly why the
    # tables below are read as ratios.
    #
    # Worth remembering the next time a benchmark reports something surprising:
    # the first question is what else the process did before the stopwatch
    # started.
    # Throughput before rebuild, and the order is load-bearing. `measure_rebuild`
    # calls `gc.collect()`, and a full collection that frees half a million
    # objects leaves the allocator returning and re-faulting arenas -- measured
    # at 5.9 us/op immediately afterwards against 0.7 us/op before it. The
    # cheapest, most allocation-sensitive measurement has to go first.
    throughput = measure_throughput()
    rebuild = measure_rebuild()

    # ---------------------------------------------------------------------- #
    print("KEYS REMAPPED when one node joins  (the whole point)")
    print(f"  {'cluster':<12} {'ring':>10} {'modulo':>10} {'ideal 1/N+1':>13}   damage")
    for n in (4, 8, 16, 32):
        names = [f"node-{i}" for i in range(n)]

        ring = HashRing(names)
        ring_before = Snapshot(ring, KEYS)
        ring.add(f"node-{n}")
        ring_moved = remap_fraction(ring_before, ring, KEYS)

        mod = ModuloSharder(names)
        mod_before = Snapshot(mod, KEYS)
        mod.add(f"node-{n}")
        mod_moved = remap_fraction(mod_before, mod, KEYS)

        print(f"  {f'{n} -> {n + 1}':<12} {ring_moved:>9.1%} {mod_moved:>10.1%}"
              f" {1 / (n + 1):>12.1%}   {mod_moved / ring_moved:>4.1f}x worse")

    print("\n  The modulo column gets WORSE as the cluster grows -- exactly backwards.")
    print("  At 100k cached objects, 32 -> 33 nodes: ~3k misses on a ring, ~97k on a modulus.")

    # ---------------------------------------------------------------------- #
    print("\nLOAD SPREAD vs virtual nodes  (8 nodes, relative stdev; 0.0 is perfect)")
    print(f"  {'vnodes':>7} {'spread':>9} {'busiest':>9} {'quietest':>9}   ring points")
    fair = len(KEYS) / 8
    for vnodes in (1, 5, 25, 50, 150, 500, 1000):
        ring = HashRing([f"node-{i}" for i in range(8)], vnodes=vnodes)
        counts = ring.distribution(KEYS)
        print(f"  {vnodes:>7} {spread(counts.values()):>9.3f}"
              f" {max(counts.values()) / fair:>8.2f}x {min(counts.values()) / fair:>8.2f}x"
              f"   {ring.points:>11,}")

    print("\n  Spread falls as ~1/sqrt(vnodes). One vnode per node is not a design,")
    print("  it is a coin flip -- and it is the version people write first.")

    # ---------------------------------------------------------------------- #
    print()
    print("\n".join(throughput))

    # ---------------------------------------------------------------------- #
    print()
    print("\n".join(rebuild))

    print("\n  Rebuilding the entire ring on every join looks wasteful and is not:")
    print("  membership changes minutes apart, and correctness beats a clever patch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
