#!/usr/bin/env python3
"""The scope demonstration, and a measurement that contradicts the folklore.

Part 1 is the point of this file. "One instance per process" is a sentence
nobody is persuaded by, so this starts four real processes -- the same thing
`gunicorn -w 4`, `uwsgi --processes 4`, PHP-FPM, a Node cluster or four
Kubernetes replicas do -- and has each report the singleton it ended up with.
Four processes, four singletons, four independent counters.

Then it reads those counters as a rate limiter set to 100 and finds it admitted
400, which is the production symptom in its usual form: nothing raises, no log
line appears, the limiter simply enforces 4x what it was set to. The same bug in
a cache halves the hit rate; in a metrics registry it halves the dashboard; in a
Snowflake ID generator it issues duplicate primary keys.

(Implementation note, because the obvious approach silently does not work:
`mp.Pool(4).map(worker, range(4))` hands all four tasks to whichever worker is
free first, so a pool of four can run four tasks in one process -- which it did,
on the first version of this file, producing a confident table of four identical
pids. Explicit `Process` objects are the only way to be sure there really are
four.)

Part 2 settles whether the outer check in double-checked locking earns its
keep, against the only comparison that can answer it: the same class with the
check removed. It does -- roughly halves the warm call. Then it measures a
module-level global in the same loop and that is several times cheaper again,
with no lock, no check, and no way to implement it incorrectly.

Both numbers are needed, because they answer different questions. If you are
writing the class, keep the outer check. If you are choosing what to write,
do not write the class.

(An earlier version of part 2 compared `instance()` against a bare `with lock:
pass` loop and concluded the check saved nothing. That comparison measures a
method call against no method call; the check was never in it. The number was
wrong by about 150ns and the conclusion was wrong outright.)

    python bench.py
"""

from __future__ import annotations

import multiprocessing as mp
import os
import platform
import sys
import threading
import time

from singleton import POOL, LockedSingleton, Metrics

WORKERS = 4
PER_WORKER = 100
LIMIT = 100
OVERHEAD_OPS = 500_000
ROUNDS = 5


class AlwaysLocks:
    """`LockedSingleton` with the outer check deleted. Exists to be measured.

    Identical in every other respect, so the difference between the two numbers
    in part 2 is attributable to the outer `if` and nothing else. Comparing
    `instance()` against a bare `with lock: pass` loop -- the first version of
    this benchmark -- compares a method call against no method call and tells
    you nothing about the check.
    """

    _instance: AlwaysLocks | None = None
    _lock = threading.Lock()

    @classmethod
    def instance(cls) -> AlwaysLocks:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance


def worker(out: mp.Queue) -> None:
    """Run in a fresh process. Touch the singletons, report what we found.

    `POOL` and `Metrics` are the same objects the parent imported -- as source
    code. At runtime they are not: `spawn` re-imports the module in the child, so
    the module body runs again and builds another POOL. The child has no way to
    tell, and that is exactly the problem.
    """
    m = Metrics.instance()
    for _ in range(PER_WORKER):
        m.bump_safe()
    out.put((os.getpid(), id(POOL), id(m), m.hits))


def best_of(fn, ops: int) -> float:
    """Per-op cost in nanoseconds, best of ROUNDS.

    The minimum, not the mean -- a slower round is the OS scheduling something
    else, and averaging that in measures background load instead of the code.
    """
    best = float("inf")
    for _ in range(ROUNDS):
        start = time.perf_counter()
        fn(ops)
        best = min(best, time.perf_counter() - start)
    return best / ops * 1e9


def scope() -> None:
    print(f"\n1. One instance per PROCESS -- {WORKERS} workers, like gunicorn -w {WORKERS}\n")
    out: mp.Queue = mp.Queue()
    procs = [mp.Process(target=worker, args=(out,)) for _ in range(WORKERS)]
    for p in procs:
        p.start()
    rows = sorted(out.get(timeout=60) for _ in procs)
    for p in procs:
        p.join(timeout=60)

    print(f"  {'pid':>8}  {'id(POOL)':>18}  {'id(Metrics)':>18}  {'its counter':>12}")
    for pid, pool_id, metrics_id, hits in rows:
        print(f"  {pid:>8}  {pool_id:>18}  {metrics_id:>18}  {hits:>12}")

    pids, pools = {r[0] for r in rows}, {r[1] for r in rows}
    total = sum(r[3] for r in rows)
    print(f"\n  {len(pids)} distinct processes, {len(pools)} distinct POOL objects.")
    print(f"  Every process believes its counter is *the* counter, and each says {PER_WORKER}.")
    print(f"  The true total is {total}. No process can see that number and nothing logged it.")
    print(f"\n  Read as a rate limiter set to {LIMIT}: it admitted {total} requests, "
          f"{total // LIMIT}x its own limit.")
    print("  The in-process guarantee held perfectly. It was the wrong guarantee.")
    print("  Uniqueness across processes needs a lease and a fencing token, not a static field.")


def fast_path() -> None:
    print("\n2. Does the outer check actually buy a cheap fast path?\n")
    LockedSingleton._reset()
    LockedSingleton.instance()
    AlwaysLocks.instance()

    def checked(n: int) -> None:
        for _ in range(n):
            LockedSingleton.instance()

    def unchecked(n: int) -> None:
        for _ in range(n):
            AlwaysLocks.instance()

    def module_level(n: int) -> None:
        for _ in range(n):
            POOL  # noqa: B018 -- a global load, which is the entire mechanism

    checked_ns = best_of(checked, OVERHEAD_OPS)
    unchecked_ns = best_of(unchecked, OVERHEAD_OPS)
    global_ns = best_of(module_level, OVERHEAD_OPS)

    print(f"  {'double-checked instance()':<30} {checked_ns:7.1f} ns/op")
    print(f"  {'always-locking instance()':<30} {unchecked_ns:7.1f} ns/op")
    print(f"  {'a module-level global':<30} {global_ns:7.1f} ns/op")

    saved = unchecked_ns - checked_ns
    print(f"\n  The outer check saves {saved:.1f} ns/op, {saved / unchecked_ns:.0%} of the warm")
    print("  call -- so the uncontended lock really is about half the cost of getting")
    print("  the instance, and skipping it is worth the two extra lines. Keep the")
    print("  outer `if` if you are writing this class.")
    print(f"\n  But the module-level global is {checked_ns / global_ns:.0f}x cheaper than even the")
    print(f"  double-checked version ({global_ns:.0f} ns against {checked_ns:.0f}), needs no lock,")
    print("  and has no incorrect version to accidentally write. In Python the answer")
    print("  is not a better accessor. It is not having one.")


def main() -> int:
    print(f"singleton bench -- {platform.python_implementation()} "
          f"{platform.python_version()} on {platform.system()}, "
          f"start method: {mp.get_start_method()}")
    scope()
    fast_path()
    return 0


if __name__ == "__main__":
    # Required where the start method is `spawn` (Windows, macOS): the child
    # re-imports this module, and without the guard it would run main() again
    # and start four more processes. Which is itself a lesson about module state.
    mp.freeze_support()
    sys.exit(main())
