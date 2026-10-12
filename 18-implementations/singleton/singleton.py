"""Singleton, and the four things people get wrong about it.

Every tutorial on this pattern teaches the same thing -- how to make the
creation thread-safe -- and then stops. That is the least interesting of the
four problems, and the only one a language feature already solves for you.

**1. Creation races.** `NaiveSingleton` has the bug every tutorial names: the
check and the assignment are two steps, and a thread can be interrupted between
them. `LockedSingleton` is the fix. The two are tested side by side with the
same threads and the same constructor, and the naive one builds eight instances
while the locked one builds one.

**2. Thread-safe creation does not make the instance thread-safe to USE.** This
is the one that actually costs people data, and it is almost never mentioned.
`Metrics` is created under a lock -- correctly, exactly once -- and still loses
seven out of eight increments, because the lock protected the object's birth and
nothing about its life. `Metrics.bump` and `Metrics.bump_safe` differ by one
`with` statement and a second, separate lock. See the test pair.

**3. "One instance" means one PER PROCESS, and production runs many.** Four
Gunicorn workers hold four singletons, each with its own cache and its own
counters. Nothing errors; the system just quietly under-delivers. `bench.py`
spawns real processes and prints the four distinct instances, because reading
that sentence convinces nobody.

**4. It is hostile to testing, and this file proves it by needing a hack.**
Every class here carries a `_reset()` classmethod that exists for one reason:
the tests cannot run twice otherwise. That method is the cost of the pattern,
made visible. `ReportService` at the bottom is the alternative -- same single
instance, handed in as an argument, no reset needed, no global to fight over.

The deterministic-test trick, since it is the non-obvious part: instead of
sleeping and hoping the race shows up, the constructor calls an injected `gate`
callable. The test uses that gate to hold every thread *inside* the constructor
until it has counted them, so "eight threads were in there at once" is asserted
rather than hoped for. No sleeps, no flakes, no timing assumptions.

Stdlib only. Written to be read top to bottom.
"""

from __future__ import annotations

import threading


def _noop() -> None:
    """The default gate: in normal use the constructor has no extra behaviour.

    Tests pass a real callable here to pin down thread interleaving. Production
    code never passes anything, so this costs one function call on the one
    occasion the instance is built.
    """


# ─────────────────────────────────────────────────────────────────────────────
# 1. The naive version, and why it breaks
# ─────────────────────────────────────────────────────────────────────────────


class NaiveSingleton:
    """The version in every tutorial. It is broken, and the test proves it.

    The GIL does not save you here. It guarantees that one thread runs bytecode
    at a time; it does not make a multi-bytecode *sequence* atomic. The check
    and the assignment in `instance()` are separate operations and a thread
    switch can land between them -- which is exactly what happens the moment
    the constructor does anything slow, and a constructor worth caching is slow
    by definition.
    """

    # A CLASS attribute, not an instance attribute -- note there is no `self`.
    # It lives on the class object itself, so there is exactly one of these no
    # matter how many callers there are. This is the slot the single instance
    # gets filled into: it starts as None and is written once.
    _instance: NaiveSingleton | None = None

    def __init__(self, dsn: str = "postgres://localhost/app", size: int = 4,
                 gate=_noop) -> None:
        # "Instance" means this: a real object in memory with its own `conns`.
        # The class is the blueprint; this is the thing built from it.
        gate()  # the slow part of a real constructor -- opening sockets
        self.dsn = dsn
        self.conns = [f"{dsn}#{i}" for i in range(size)]

    @classmethod
    def instance(cls, gate=_noop) -> NaiveSingleton:
        # @classmethod is what makes this callable as NaiveSingleton.instance()
        # *without having an object first* -- and that is the whole reason the
        # accessor must be class-level rather than an ordinary method. An
        # ordinary method needs a `self`, and `self` is the thing you are trying
        # to obtain. Chicken and egg.
        if cls._instance is None:          # ← thread A can be interrupted HERE
            cls._instance = cls(gate=gate)  # ← while thread B also sees None
        return cls._instance

    @classmethod
    def _reset(cls) -> None:
        """Discard the instance so a test can start clean.

        This method is the pattern's testability cost, in the flesh. Nothing in
        production wants it; it exists because global state outlives the test
        that touched it, and without it the second test in any file inherits
        whatever the first one built. A test that passes alone and fails in a
        suite is this method's absence.
        """
        cls._instance = None


# ─────────────────────────────────────────────────────────────────────────────
# 2. The fix: double-checked locking
# ─────────────────────────────────────────────────────────────────────────────


class LockedSingleton:
    """Correct creation. Two checks, one lock, and a reason for each.

    The outer check is outside the lock so the overwhelming majority of calls
    -- every call after startup -- never touch it. The inner check is inside
    the lock because between a thread's first check and acquiring the lock,
    another thread may have finished the whole job; without the re-check the
    lock buys nothing and the second thread builds a second instance anyway.

    Python-specific note: this is enough here. In Java the same code needs the
    instance field marked `volatile`, or another thread can observe a non-null
    reference to a half-constructed object. CPython's object model does not
    expose that reordering, so the direct translation of this class into Java
    without `volatile` would be subtly broken.
    """

    _instance: LockedSingleton | None = None
    _lock = threading.Lock()

    def __init__(self, dsn: str = "postgres://localhost/app", size: int = 4,
                 gate=_noop) -> None:
        gate()
        self.dsn = dsn
        self.conns = [f"{dsn}#{i}" for i in range(size)]

    @classmethod
    def instance(cls, gate=_noop) -> LockedSingleton:
        if cls._instance is None:               # fast path: no lock once warm
            with cls._lock:                     # only the first callers pay this
                if cls._instance is None:       # re-check: someone may have won
                    cls._instance = cls(gate=gate)
        return cls._instance

    @classmethod
    def _reset(cls) -> None:
        cls._instance = None


# ─────────────────────────────────────────────────────────────────────────────
# 3. What Python actually does instead
# ─────────────────────────────────────────────────────────────────────────────


class ConnectionPool:
    """A plain class with no singleton machinery whatsoever.

    Uniqueness comes from `POOL` below instead. Python's import system already
    guarantees that a module's body executes exactly once, under a lock, no
    matter how many files import it -- so a module-level object *is* a lazy,
    thread-safe singleton, with nothing to get wrong. The `_instance`/`_lock`
    shape above is Java habits leaking across; it is worth knowing because
    interviewers ask for it, and worth not writing.

    Note what this bought: the class stayed ordinary. A test can construct as
    many of these as it likes, which is precisely what `LockedSingleton` forbids.
    """

    def __init__(self, dsn: str, size: int = 4) -> None:
        self.dsn = dsn
        self.conns = [f"{dsn}#{i}" for i in range(size)]


POOL = ConnectionPool("postgres://localhost/app")
"""The module-level singleton. Import it from anywhere; it is the same object.

And it is the same object only within one interpreter. Import this module in a
second process and the body runs again, building a second POOL -- see bench.py.
"""


# ─────────────────────────────────────────────────────────────────────────────
# 4. The problem nobody mentions: safe to create, unsafe to use
# ─────────────────────────────────────────────────────────────────────────────


class Metrics:
    """Created exactly once, correctly, under a lock -- and still loses data.

    This is the gap the tutorials leave. `instance()` below is airtight: one
    instance, no race, nothing to criticise. Then every request thread in the
    process shares that one object's mutable state, and `bump` loses increments,
    because a lock around *construction* says nothing about *mutation*.

    `bump` and `bump_safe` differ by one `with` statement and a second lock --
    and that second lock is the point. `_lock` guards who gets to build the
    object; `_use_lock` guards what happens to it afterwards. Confusing the two
    is how a correctly-implemented singleton still corrupts a counter.
    """

    _instance: Metrics | None = None
    _lock = threading.Lock()  # guards CREATION

    def __init__(self) -> None:
        self.hits = 0
        self._use_lock = threading.Lock()  # guards MUTATION -- a different job

    @classmethod
    def instance(cls) -> Metrics:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def bump(self, gate=_noop) -> None:
        """Lose increments under concurrency. Read, pause, write.

        `self.hits += 1` is the same bug written shorter: it reads, adds, and
        writes as separate steps. Anything at all between the read and the write
        -- a method call, a log line, an `await`, a GC pause, the interpreter's
        own thread switch -- lets another thread read the same stale value.
        """
        current = self.hits   # READ
        gate()                # ← anything here, including nothing in particular
        self.hits = current + 1  # WRITE, based on a value that may be stale

    def bump_safe(self, gate=_noop) -> None:
        """The same three steps, made indivisible."""
        with self._use_lock:
            current = self.hits
            gate()
            self.hits = current + 1

    @classmethod
    def _reset(cls) -> None:
        cls._instance = None


# ─────────────────────────────────────────────────────────────────────────────
# 5. Borg / Monostate: shared state, many instances
# ─────────────────────────────────────────────────────────────────────────────


class Borg:
    """Many objects, one set of attributes. The inverse trade of Singleton.

    Singleton controls identity and shares state as a consequence. Borg shares
    state directly and lets identity be whatever it likes, by pointing every
    instance's `__dict__` at one shared mapping. Callers construct it normally
    and never need to know -- there is no `instance()` to remember.

    Worth knowing, rarely worth using: `a is not b` while `a.x is b.x` violates
    an assumption almost every reader holds, and the surprise is not paid for by
    anything Singleton does not also give you.
    """

    _shared: dict = {}

    def __init__(self) -> None:
        self.__dict__ = self._shared


# ─────────────────────────────────────────────────────────────────────────────
# 6. The alternative: one instance, handed in
# ─────────────────────────────────────────────────────────────────────────────


class ReportService:
    """Dependency injection, with no framework in sight.

    This is the whole technique: the thing it needs arrives as a constructor
    argument instead of being fetched from a global. Compare the two bodies --

        def run(self):  pool = LockedSingleton.instance()   # fetched: no seam
        def run(self):  pool = self._pool                   # injected: swappable

    -- and note three things the signature now tells you that the fetching
    version hides. It needs a pool. It needs exactly one. A test can give it a
    different one. None of that required a container; a container only becomes
    useful when the wiring gets large enough to be tedious, and its "singleton
    scope" does exactly what `POOL` above does.

    The uniqueness guarantee did not go anywhere. One pool is still constructed,
    in one place, at startup. What changed is that reaching it is no longer a
    global lookup -- which is the entire difference between the two columns in
    the testability diagram on the page this file accompanies.
    """

    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def connection_count(self) -> int:
        return len(self._pool.conns)


def demo() -> None:
    """Assert the four claims above, with no test runner. `python singleton.py`."""
    barrier = threading.Barrier(4)
    seen: list[int] = []
    NaiveSingleton._reset()

    def grab() -> None:
        seen.append(id(NaiveSingleton.instance(gate=barrier.wait)))

    threads = [threading.Thread(target=grab) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(seen)) == 4, f"expected 4 instances from the race, got {set(seen)}"

    LockedSingleton._reset()
    one = LockedSingleton.instance()
    assert LockedSingleton.instance() is one

    Metrics._reset()
    m, gate = Metrics.instance(), threading.Barrier(4).wait
    threads = [threading.Thread(target=m.bump, args=(gate,)) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert m.hits == 1, f"4 threads, 1 increment survives; got {m.hits}"

    a, b = Borg(), Borg()
    a.colour = "green"
    assert a is not b and b.colour == "green"

    assert ReportService(ConnectionPool("fake://", size=99)).connection_count() == 99
    print("naive raced to 4 instances · locked held at 1 · "
          "3 of 4 increments lost · borg shares · DI substitutes")


if __name__ == "__main__":
    demo()
