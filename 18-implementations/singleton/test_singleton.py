"""Tests that assert the defining properties, not that the code runs.

Nothing here sleeps to wait for something. A concurrency test built on sleeps
measures the machine and then flakes in CI, and worse, a *race* test that sleeps
can only ever report "the race did not show up this time" -- which is
indistinguishable from "there is no race". So the interleaving is pinned
instead: `Gate` holds every thread inside the constructor while the test counts
them. "Eight threads were in there simultaneously" becomes an assertion.

Two headline pairs, adjacent on purpose.

The first is the race everyone knows about:
`test_the_naive_singleton_builds_one_instance_per_thread` against
`test_the_locked_singleton_builds_exactly_one` -- same threads, same gate, same
constructor; eight instances against one.

The second is the one almost nobody mentions, and it is the expensive one:
`test_a_correctly_created_singleton_still_loses_writes` against
`test_the_second_lock_is_what_makes_mutation_safe`. The instance in both is
built exactly once, under a lock, flawlessly. Seven of eight increments
disappear anyway, because a lock around construction says nothing about
mutation.

Every test opens by resetting class state, and that fixture is itself a
finding: it only has to exist because the thing under test is global. The
injection test at the bottom needs no reset, which is the whole argument for it.
"""

from __future__ import annotations

import threading

import pytest

from singleton import (
    POOL,
    Borg,
    ConnectionPool,
    LockedSingleton,
    Metrics,
    NaiveSingleton,
    ReportService,
)

THREADS = 8


class Gate:
    """Pin thread interleaving without sleeping.

    Passed into a constructor as its `gate`. Every thread that reaches it
    announces itself and then blocks until the test releases it, so the test can
    assert exactly how many threads got inside before any of them finished.

    `wait_for(n)` is the positive assertion -- n threads really were in there at
    once. `no_more()` is the negative one, and it is the interesting half: it
    proves the lock kept everyone else *out*. It cannot produce a false pass,
    because a second thread entering would require the lock to have been
    released, and the holder does not release it until `go()` is called.
    """

    def __init__(self) -> None:
        self.arrived = threading.Semaphore(0)
        self.proceed = threading.Event()

    def __call__(self) -> None:
        self.arrived.release()
        self.proceed.wait(10)

    def wait_for(self, n: int) -> None:
        for i in range(n):
            assert self.arrived.acquire(timeout=10), (
                f"only {i} of {n} threads reached the constructor")

    def no_more(self) -> bool:
        return not self.arrived.acquire(timeout=0.25)

    def go(self) -> None:
        self.proceed.set()


def start(target, n: int = THREADS) -> list[threading.Thread]:
    """Launch n threads and return them still running.

    Starting and joining are separate because a gated test has to talk to the
    threads *while* they are blocked inside the constructor. Joining first would
    deadlock against the gate that the test has not released yet.
    """
    threads = [threading.Thread(target=target, daemon=True) for _ in range(n)]
    for t in threads:
        t.start()
    return threads


def finish(threads: list[threading.Thread]) -> None:
    for t in threads:
        t.join(timeout=10)
    assert not any(t.is_alive() for t in threads), "a worker thread never finished"


def run(target, n: int = THREADS) -> None:
    """start + finish, for the ungated tests."""
    finish(start(target, n))


@pytest.fixture(autouse=True)
def _clean_globals():
    """Reset every singleton before and after each test.

    This fixture is the pattern's testability cost, stated as code. It exists
    because the instances are class attributes that outlive the test that
    created them: skip it and the second test in this file silently inherits the
    first test's object, passes for the wrong reason, then fails when the file
    runs in a different order. "Passes alone, fails in a suite" is this fixture
    missing.
    """
    def wipe() -> None:
        for cls in (NaiveSingleton, LockedSingleton, Metrics):
            cls._reset()
        Borg._shared.clear()

    wipe()
    yield
    wipe()


# ── headline pair 1: the creation race ──────────────────────────────────────


def test_the_naive_singleton_builds_one_instance_per_thread():
    """Eight threads, eight "singletons". The bug, demonstrated not described.

    Each thread checks `_instance`, finds None because nobody has assigned yet,
    and constructs. The gate holds all eight inside the constructor so this is
    asserted rather than hoped for -- if the race could not happen, `wait_for`
    would time out and say so.

    The real cost is whatever a constructor worth caching contains. Eight of
    these means eight connection pools: eight times the connections against a
    database that has a hard limit and will start refusing them.
    """
    gate, seen = Gate(), []
    threads = start(lambda: seen.append(NaiveSingleton.instance(gate=gate)))
    gate.wait_for(THREADS)   # all eight really are inside __init__ right now
    gate.go()
    finish(threads)

    assert len(seen) == THREADS
    assert len({id(x) for x in seen}) == THREADS, "expected one instance per thread"
    assert sum(len(x.conns) for x in seen) == THREADS * 4, "8 pools, 4 conns each"


def test_the_locked_singleton_builds_exactly_one():
    """Same eight threads, same gate. One instance, and nobody else gets in.

    `no_more()` is the assertion that matters. One thread inside the constructor
    could also mean the other seven had simply not arrived yet; this proves they
    arrived and were held out, which is the difference between a lock that works
    and a test that got lucky with timing.
    """
    gate, seen = Gate(), []
    threads = start(lambda: seen.append(LockedSingleton.instance(gate=gate)))
    gate.wait_for(1)
    assert gate.no_more(), "a second thread entered the constructor: the lock failed"
    gate.go()
    finish(threads)

    assert len(seen) == THREADS
    assert len({id(x) for x in seen}) == 1, "every caller must get the same object"
    assert seen[0] is LockedSingleton.instance()


def test_the_inner_check_is_what_stops_a_second_build():
    """Delete the re-check and the lock stops buying you anything.

    Two threads, both already past the outer check, then serialised by the lock.
    The first builds and assigns; the second takes the lock, does not look
    again, and builds a second pool over the top of the first. The lock made the
    two builds sequential. It did not make there be one -- and "sequential" is
    not the property anybody wanted.

    Written as a local class rather than exported, because its only purpose is
    to be wrong in exactly one place.
    """
    builds: list[int] = []
    barrier = threading.Barrier(2)

    class SingleChecked:                      # LockedSingleton minus the inner `if`
        _instance = None
        _lock = threading.Lock()

        @classmethod
        def instance(cls):
            if cls._instance is None:         # outer check
                barrier.wait()                # both threads are now past it
                with cls._lock:
                    builds.append(1)          # no re-check here: that is the bug
                    cls._instance = object()
            return cls._instance

    run(SingleChecked.instance, n=2)
    assert len(builds) == 2, "the lock serialised the builds, it did not prevent one"


# ── headline pair 2: safe to create, unsafe to use ──────────────────────────


def test_a_correctly_created_singleton_still_loses_writes():
    """The expensive bug. Creation is flawless; seven of eight writes vanish.

    `Metrics.instance()` is double-checked, locked, and correct -- there is one
    instance and the test asserts it. Then eight threads share that one object's
    mutable state and the counter ends at 1.

    This is what makes the pattern dangerous rather than merely unfashionable.
    The thread-safety everyone teaches is the thread-safety of the *birth*; the
    object then lives for the whole process being touched by every request
    thread at once. Nothing raises. The number is just wrong, quietly, forever.
    """
    m, barrier = Metrics.instance(), threading.Barrier(THREADS)
    assert m is Metrics.instance(), "creation is correct -- that is the point"

    run(lambda: m.bump(gate=barrier.wait))
    assert m.hits == 1, f"8 increments, 1 survivor; got {m.hits}"


def test_the_second_lock_is_what_makes_mutation_safe():
    """One extra `with`, and the window between read and write closes.

    This one cannot reuse the barrier, and the reason is the lesson: a barrier
    inside a mutual-exclusion region deadlocks, because the threads it waits for
    are queued on the lock it is holding. There is no interleaving left to pin,
    which is what "indivisible" means.

    So the property is asserted at the source instead. The gate fires between
    the read and the write, and from there it checks whether the mutation lock
    is held. `bump_safe` says yes and `bump` says no, and that one boolean is
    the entire difference between the previous test and this one.

    Asserting the count alone would not do: a lost update needs the interpreter
    to switch threads inside a four-bytecode window, which at the default 5ms
    switch interval it will usually decline to do. The count would then pass
    against an unlocked `bump_safe` and the test would be worth nothing. It was,
    until this version replaced it.
    """
    m, held = Metrics.instance(), []

    m.bump_safe(gate=lambda: held.append(m._use_lock.locked()))
    assert held == [True], "the read-modify-write must run inside the lock"

    m.bump(gate=lambda: held.append(m._use_lock.locked()))
    assert held == [True, False], "and the unsafe path must not be holding it"

    run(lambda: [m.bump_safe() for _ in range(50)])
    assert m.hits == 2 + THREADS * 50, "no increment lost once the window is closed"


# ── scope, alternatives, and the way out ────────────────────────────────────


def test_the_module_level_instance_is_the_same_object_everywhere():
    """Python's import lock already gives you a lazy, thread-safe singleton.

    `POOL` was imported at the top of this file; importing the module again
    re-binds the same object rather than re-running the module body. No
    `_instance`, no `_lock`, nothing to get wrong -- which is why this, and not
    `LockedSingleton`, is the idiomatic Python answer.

    The guarantee stops at the interpreter. A second process re-imports and
    builds a second POOL; `bench.py` spawns four and prints four.
    """
    import singleton

    assert singleton.POOL is POOL
    assert ConnectionPool("x://", size=2) is not POOL, "the class itself stayed ordinary"


def test_borg_shares_state_without_sharing_identity():
    """The inverse trade: Singleton controls identity, Borg controls state."""
    a, b = Borg(), Borg()
    a.region = "eu-west-1"

    assert a is not b, "distinct objects"
    assert b.region == "eu-west-1", "one shared __dict__"


def test_injection_needs_no_reset_because_there_is_nothing_global():
    """The alternative, and the argument for it visible in the setup.

    Every test above opens by resetting class state. This one hands the service
    a pool and is done -- two services, two different pools, same process, no
    interference. That seam is what the fetching version does not have, and the
    uniqueness guarantee is untouched: production still builds exactly one and
    passes it in.
    """
    real = ReportService(POOL)
    fake = ReportService(ConnectionPool("fake://localhost", size=99))

    assert real.connection_count() == 4
    assert fake.connection_count() == 99, "substitutable, with no framework involved"
