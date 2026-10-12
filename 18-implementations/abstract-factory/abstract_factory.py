"""Abstract Factory: the invariant, the asymmetry, and the family that leaks.

The pattern does not make objects easier to create. It makes an **illegal
combination harder to express** -- an S3 store next to an in-memory queue --
and that negative guarantee is the entire product. If you do not have an
invariant across two or more objects, you do not need this pattern; you need
Factory Method or a parameter.

Three things this file exists to show, in increasing order of how much they
cost in real work.

**1. The invariant.** Every factory hands out a matched set, and
`test_every_factory_hands_out_a_matched_set` checks all of them rather than one,
because the realistic bug is a copy-pasted fourth factory whose queue still says
`s3`.

**2. The asymmetry, which is the actual decision rule.** "Abstract Factory is
rigid" is too vague to act on. The rigidity has a shape: adding a *family* costs
one new class and zero edits elsewhere; adding a *product* costs one interface
method plus one method in **every** factory. O(1) against O(F). So the rule is:
use it when the number of families grows and the number of products is stable.
Invert that and you have picked the pattern that charges you on exactly the axis
you are growing.

This is also the one place where an ABC earns its keep in Python. Add an
abstract method and every concrete factory fails *loudly, at instantiation*,
with `TypeError: Can't instantiate abstract class ...`. That is not an
annoyance, it is the cost being made visible at the moment you incur it.
Duck-typed, the same change fails later, at a call site, in production.

**3. The family that leaks, which is why cloud abstraction fails.** Providers
differ in *capability*, not only in naming. `LocalBackend` has no presigned
URLs and never will. The three usual responses are all bad -- the intersection
loses every provider's good features, the union makes the type system lie, and
`isinstance` checks mean the abstraction is dead and still being maintained.
`capabilities` below is the fourth option, and the only honest one: declare the
asymmetry instead of hiding it.

`BACKENDS` at the bottom is what to actually reach for in Python -- a frozen
dataclass of callables. One class in total, families become *values* you can
put in a dict and parameterise a test with, and you cannot construct half a
family because both fields are required.

Stdlib only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

# ─────────────────────────────────────────────────────────────────────────────
# The products -- two of them, which is the minimum for the pattern to mean
# anything. One product is Factory Method's job.
# ─────────────────────────────────────────────────────────────────────────────


class Store(ABC):
    """A product. `family` is the marker the invariant test checks."""

    family: str

    @abstractmethod
    def put(self, key: str, data: bytes) -> str: ...


class Queue(ABC):
    """The other product. These two must come from the same family: a worker
    reading from the queue has to be able to reach what the store wrote."""

    family: str

    @abstractmethod
    def push(self, msg: str) -> str: ...


class S3Store(Store):
    family = "s3"

    def put(self, key: str, data: bytes) -> str:
        return f"s3://bucket/{key}"


class SqsQueue(Queue):
    family = "s3"

    def push(self, msg: str) -> str:
        return f"sqs:{msg}"


class DiskStore(Store):
    family = "local"

    def put(self, key: str, data: bytes) -> str:
        return f"/var/data/{key}"


class MemoryQueue(Queue):
    family = "local"

    def push(self, msg: str) -> str:
        return f"mem:{msg}"


class FakeStore(Store):
    family = "fake"

    def put(self, key: str, data: bytes) -> str:
        return f"fake://{key}"


class FakeQueue(Queue):
    family = "fake"

    def push(self, msg: str) -> str:
        return f"fake:{msg}"


# ─────────────────────────────────────────────────────────────────────────────
# The classic form
# ─────────────────────────────────────────────────────────────────────────────


class BackendFactory(ABC):
    """The abstract factory. Several creation methods, one matched set each.

    `capabilities` is not in the Gang of Four description and is the most
    useful thing on this class. Real families are asymmetric -- S3 can presign
    a URL and a local disk cannot -- and the three textbook responses to that
    are all bad:

        intersection  drop presign from the interface entirely, and every
                      caller loses a feature three of four providers have
        union         put presign on the base and have DiskStore raise
                      NotImplementedError. The type now says "you may call
                      this" and the runtime disagrees. The worst option: the
                      compiler has been turned into a liar
        isinstance    `if isinstance(store, S3Store): store.presign(...)`.
                      The abstraction is dead and you are still maintaining it

    Declaring capabilities is the fourth option. It does not pretend the
    family is symmetric; it makes the asymmetry a documented, checkable value,
    so a caller branches on `supports("presign")` rather than on a concrete
    type. This is what mature libraries settle on, and it is the honest answer
    when you genuinely must abstract an asymmetric family.

    The better answer, where you can take it, is not to abstract at all: use
    one provider and accept the lock-in. The abstraction tax is paid every day;
    the migration happens once, or never.
    """

    family: str
    capabilities: frozenset[str] = frozenset()

    @abstractmethod
    def store(self) -> Store: ...

    @abstractmethod
    def queue(self) -> Queue: ...

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities


class S3Factory(BackendFactory):
    family = "s3"
    capabilities = frozenset({"presign", "versioning"})

    def store(self) -> Store:
        return S3Store()

    def queue(self) -> Queue:
        return SqsQueue()

    def presign(self, key: str) -> str:
        """Only exists where it is supported, and `capabilities` says so."""
        return f"https://bucket.s3/{key}?sig=abc"


class LocalFactory(BackendFactory):
    """No presign, no versioning -- and it says so rather than raising later."""

    family = "local"
    capabilities = frozenset()

    def store(self) -> Store:
        return DiskStore()

    def queue(self) -> Queue:
        return MemoryQueue()


class FakeFactory(BackendFactory):
    """The best Abstract Factory most people will ever write: a test
    environment.

    One object hands out a matched set of fakes, so a test physically cannot
    reach a real store while using a fake queue. It is also symmetric *by
    construction* -- you wrote both sides -- which is exactly the condition the
    pattern needs and the condition cloud providers do not meet.
    """

    family = "fake"
    capabilities = frozenset({"presign"})

    def store(self) -> Store:
        return FakeStore()

    def queue(self) -> Queue:
        return FakeQueue()

    def presign(self, key: str) -> str:
        return f"https://fake/{key}"


FACTORIES: list[BackendFactory] = [S3Factory(), LocalFactory(), FakeFactory()]


def upload(factory: BackendFactory, key: str, data: bytes) -> tuple[str, str]:
    """A client that never names a concrete class.

    Worth being precise about the guarantee, because it is weaker in Python
    than the textbook implies. Nothing stops someone writing
    `S3Store(), MemoryQueue()` by hand -- Python has no package-private
    constructor to stop them. What the pattern buys is that no code path
    *through the factory* can mix families, and this function has no
    expression that could. In Java with package-private product constructors
    it really is unrepresentable; here it is merely unreachable by anyone using
    the intended door.
    """
    return factory.store().put(key, data), factory.queue().push(key)


# ─────────────────────────────────────────────────────────────────────────────
# What to actually write in Python
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Backend:
    """A family as a *value*. One class instead of one per family.

    A class is an ordinary object in Python, so the factory does not need to be
    a type with methods -- it can be a record of callables. The invariant
    survives: both fields are required, so there is no way to construct half a
    family, and `frozen=True` means nobody swaps one member out afterwards.

    What this gives up against the ABC version is the loud failure. Add a third
    product and the ABC breaks every factory at instantiation; this breaks at
    the `Backend(...)` call sites instead, which is nearly as loud and
    considerably less ceremony.

    What it gains is that families are now data: dict them, pass them, and
    parameterise a test over all of them with `@pytest.mark.parametrize`.
    """

    family: str
    store: Callable[[], Store]
    queue: Callable[[], Queue]
    capabilities: frozenset[str] = frozenset()


BACKENDS: dict[str, Backend] = {
    "s3": Backend("s3", S3Store, SqsQueue, frozenset({"presign", "versioning"})),
    "local": Backend("local", DiskStore, MemoryQueue),
    "fake": Backend("fake", FakeStore, FakeQueue, frozenset({"presign"})),
}


def demo() -> None:
    """Assert the findings with no test runner. `python abstract_factory.py`."""
    # 1. Every factory hands out a matched set.
    for f in FACTORIES:
        assert f.store().family == f.queue().family == f.family

    # 2. Adding a product breaks every factory. Here is one, missing `queue`.
    class Incomplete(BackendFactory):
        family = "broken"

        def store(self) -> Store:
            return DiskStore()

    try:
        Incomplete()
        raise AssertionError("an incomplete factory must not be instantiable")
    except TypeError as e:
        assert "abstract" in str(e)

    # 3. The family is asymmetric, and says so instead of raising later.
    s3, local = S3Factory(), LocalFactory()
    assert s3.supports("presign") and not local.supports("presign")
    assert hasattr(s3, "presign") and not hasattr(local, "presign")

    # 4. Families as values, with the invariant intact.
    for name, b in BACKENDS.items():
        assert b.store().family == b.queue().family == name

    print("3 factories, 3 matched sets · an incomplete factory will not "
          "instantiate · asymmetry declared, not raised · families as values")


if __name__ == "__main__":
    demo()
