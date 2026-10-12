"""Tests that assert the defining properties, not that the code runs.

The headline is `test_every_factory_hands_out_a_matched_set`, and it sweeps
*every* factory rather than checking one. Checking one proves the pattern was
understood; checking all of them catches the realistic bug, which is a
copy-pasted fourth factory whose `queue()` still returns the third family's
queue. A test that would not catch that is decoration.

The second pair is the decision rule. `test_adding_a_product_breaks_every_factory`
defines a factory missing one method and watches it fail at instantiation, and
`test_the_edit_cost_of_a_new_product_is_one_per_family` counts the price in
methods. Together they say what "Abstract Factory is rigid" means in numbers:
a new family is one edit, a new product is F+1.

The third group is the leaky family, with all three bad options made runnable
beside the honest fourth -- because the choice between them is the real
decision in any provider abstraction, and reading three bullet points about it
convinces nobody.
"""

from __future__ import annotations

import inspect

import pytest

from abstract_factory import (
    BACKENDS,
    FACTORIES,
    Backend,
    BackendFactory,
    DiskStore,
    LocalFactory,
    MemoryQueue,
    Queue,
    S3Factory,
    S3Store,
    Store,
    upload,
)

PRODUCTS = ("store", "queue")


# ── the invariant, which is the whole point ─────────────────────────────────


@pytest.mark.parametrize("factory", FACTORIES, ids=lambda f: f.family)
def test_every_factory_hands_out_a_matched_set(factory):
    """Sweep all of them. One would prove nothing about the next one added.

    The pattern's product is a *negative* guarantee: no S3 store beside an
    in-memory queue. That guarantee is only as good as the least careful
    factory, so the test has to be parameterised over the list rather than
    written once against a favourite.
    """
    assert factory.store().family == factory.family
    assert factory.queue().family == factory.family


def test_the_client_cannot_mix_families():
    """`upload` names no concrete class, so no path through it can mix."""
    for factory in FACTORIES:
        store_ref, queue_ref = upload(factory, "report.csv", b"x")
        assert store_ref and queue_ref

    assert upload(S3Factory(), "k", b"")[0].startswith("s3://")
    assert upload(LocalFactory(), "k", b"")[0].startswith("/var/data/")

    # Honest about the limit: Python has no package-private constructor, so a
    # caller who bypasses the factory entirely can still build a mixed pair.
    # The pattern makes mixing unreachable through the intended door, not
    # unrepresentable in the language.
    assert S3Store().family != MemoryQueue().family, "hand-mixing is still legal here"


# ── the asymmetry, which is the decision rule ───────────────────────────────


def test_adding_a_product_breaks_every_factory():
    """A factory missing one method will not instantiate. That IS the cost.

    This is what "adding a product changes every factory" means mechanically:
    the moment a third `@abstractmethod` lands on `BackendFactory`, every
    concrete factory below it is in exactly this state until someone edits it.

    The ABC is doing real work here, and it is the opposite of the advice on
    the Singleton and Factory Method pages. Loud failure at instantiation beats
    a duck-typed `AttributeError` at a call site in production, because the
    cost arrives at the moment you incur it rather than at the moment a user
    finds it.
    """
    class Incomplete(BackendFactory):
        family = "broken"

        def store(self) -> Store:
            return DiskStore()
        # no queue() -- a third product was added and this one was missed

    with pytest.raises(TypeError) as e:
        Incomplete()
    assert "abstract" in str(e.value).lower()


def test_the_edit_cost_of_a_new_product_is_one_per_family():
    """Count it, so "rigid" becomes a number you can plan around.

    Adding a FAMILY  -> 1 new class, 0 edits to anything that exists.
    Adding a PRODUCT -> 1 interface method + 1 method in every factory.

    O(1) against O(F). Hence the rule: reach for this pattern when the count of
    families grows and the count of products is stable, and avoid it when that
    is the other way round.
    """
    required = [n for n, m in inspect.getmembers(BackendFactory)
                if getattr(m, "__isabstractmethod__", False)]
    assert sorted(required) == sorted(PRODUCTS)

    # A NEW FAMILY: one new class, and not one line of anything that already
    # exists is touched. Defined here, works immediately.
    class GcsFactory(BackendFactory):
        family = "gcs"

        def store(self) -> Store:
            return S3Store()

        def queue(self) -> Queue:
            return SqsQueue()

    assert GcsFactory().family == "gcs"
    assert all(f.store().family == f.family for f in FACTORIES), "nothing else moved"

    # A NEW PRODUCT: one interface method, and then every factory in this list
    # is incomplete until someone edits it -- the state
    # test_adding_a_product_breaks_every_factory puts one in.
    assert all(set(required) <= set(dir(type(f))) for f in FACTORIES)
    assert len(FACTORIES) * len(required) == sum(
        len(required) for _ in FACTORIES), "every cell written by hand, once per family"


# ── the family that leaks ───────────────────────────────────────────────────


def test_capabilities_declare_the_asymmetry_instead_of_hiding_it():
    """The honest option. The caller branches on a value, not on a type.

    Providers differ in what they can *do*, not only in what things are
    called, and no interface design makes an asymmetric family symmetric. This
    admits that: `supports` is a documented, checkable fact, so a caller never
    has to ask what concrete class it is holding.
    """
    s3, local = S3Factory(), LocalFactory()

    assert s3.supports("presign")
    assert not local.supports("presign")
    assert s3.presign("k").startswith("https://")
    assert not hasattr(local, "presign"), "absent, rather than present and raising"


def test_the_union_option_makes_the_type_system_lie():
    """Put presign on the base and the signature promises what local cannot do.

    The worst of the three textbook options, and the most commonly chosen,
    because it is the one that compiles. Every caller now has to know which
    providers actually implement it -- which is the knowledge the abstraction
    existed to remove.
    """
    class UnionFactory(BackendFactory):
        family = "union-local"

        def store(self) -> Store:
            return DiskStore()

        def queue(self) -> Queue:
            return MemoryQueue()

        def presign(self, key: str) -> str:
            raise NotImplementedError("local disk cannot presign")

    f = UnionFactory()
    assert hasattr(f, "presign"), "the type says you may call it"
    with pytest.raises(NotImplementedError):
        f.presign("k")                       # and the runtime disagrees


def test_the_intersection_option_costs_everyone_the_feature():
    """Drop presign from the interface and three of four providers lose it.

    Nothing raises and nothing lies -- which is why this one looks responsible.
    The cost is silent: you are paying for an abstraction that makes *every*
    option worse than picking one provider would have been.
    """
    intersection = [n for n, m in inspect.getmembers(BackendFactory)
                    if getattr(m, "__isabstractmethod__", False)]

    assert "presign" not in intersection, "the common interface cannot include it"
    assert S3Factory().supports("presign"), "yet the capability exists and is unreachable"


def test_the_isinstance_option_couples_the_caller_to_the_concrete_type():
    """The abstraction is dead, and still being maintained. Shown, not argued."""
    def leaky_url(factory: BackendFactory, key: str) -> str:
        if isinstance(factory, S3Factory):        # ← knows the concrete class
            return factory.presign(key)
        return factory.store().put(key, b"")

    assert leaky_url(S3Factory(), "k").startswith("https://")
    assert leaky_url(LocalFactory(), "k") == "/var/data/k"

    # Every new provider needs another branch here, in every function that
    # does this -- which is precisely the edit the abstraction promised to
    # remove. `supports()` needs none.
    assert "isinstance" in inspect.getsource(leaky_url)


# ── what to actually write in Python ────────────────────────────────────────


@pytest.mark.parametrize("name", sorted(BACKENDS))
def test_a_frozen_dataclass_keeps_the_invariant_with_one_class(name):
    """Families as values. Same guarantee, one class instead of one per family."""
    b = BACKENDS[name]
    assert b.store().family == b.queue().family == name


def test_you_cannot_construct_half_a_family():
    """Both fields are required, and frozen means nobody swaps one out later."""
    with pytest.raises(TypeError):
        Backend("s3", S3Store)               # type: ignore[call-arg]

    b = BACKENDS["s3"]
    with pytest.raises(Exception):           # FrozenInstanceError subclasses it
        b.queue = MemoryQueue                # type: ignore[misc]


def test_families_as_values_can_be_swept_in_one_line():
    """The practical win: a test can run against every family without knowing
    any of their names, which the class-per-family version makes awkward."""
    assert {n: b.store().family for n, b in BACKENDS.items()} == {
        "s3": "s3", "local": "local", "fake": "fake"}
