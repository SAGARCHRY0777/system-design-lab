"""Tests that assert the defining properties, not that the code runs.

Four patterns here are the same five lines of code and differ only in intent,
so every test is a *discriminator* -- something true of one and false of
another -- rather than a demonstration that each one works. Four tests that
each show a wrapper wrapping would prove nothing at all.

The hard pair is Decorator against Proxy, and the headline is
`test_decorator_always_calls_inner` beside `test_proxy_may_not_call_inner`.
Same wrapped object, same two calls, same interface: `renders == 2` against
`renders == 1`. That one integer is the distinction, and it is sharper than
any sentence about which one "adds behaviour" --

    Proxy decides WHETHER the inner call happens.
    Decorator changes WHAT HAPPENS AROUND a call it always makes.

The other three are the ones the usual treatment leaves out:
`test_decorator_order_is_part_of_the_design` measures a 120x difference
between two stacks that both type-check and both run;
`test_a_lazy_proxy_is_the_n_plus_one_problem` counts the round trips an
innocent-looking loop makes; and `test_getattr_forwarding_silently_drops_dunders`
is the trap every "let's avoid the boilerplate" wrapper falls into.
"""

from __future__ import annotations

import zlib

import pytest

from wrappers import (
    QUERIES,
    CachingProxy,
    EncryptDecorator,
    GzipDecorator,
    LazyRow,
    LegacyAdapter,
    LegacyReport,
    MagicWrapper,
    Notifier,
    Renderer,
    Report,
    ReportingFacade,
    Storage,
)

ROWS = ["GET /api/users 200 14ms"] * 400


@pytest.fixture
def report() -> Report:
    return Report(list(ROWS))


@pytest.fixture(autouse=True)
def _clear_queries():
    QUERIES.clear()
    yield
    QUERIES.clear()


# ── headline pair: the only hard distinction ───────────────────────────────


def test_decorator_always_calls_inner(report):
    """A decorator needs a result to transform, so it cannot skip the call."""
    deco = GzipDecorator(report)

    deco.render()
    deco.render()

    assert report.renders == 2, "two calls out, two calls in"
    assert zlib.decompress(deco.render()) == b"\n".join(r.encode() for r in ROWS)


def test_proxy_may_not_call_inner(report):
    """Same interface, same two calls, one render. That is the whole difference.

    The caller cannot tell the proxy is there -- which is the design goal, and
    the opposite of a decorator, which exists precisely because the caller
    wanted what it adds.
    """
    prox = CachingProxy(report)

    first = prox.render()
    second = prox.render()

    assert report.renders == 1, "the second call never reached the report"
    assert first is second, "and it is literally the same object back"


def test_both_are_indistinguishable_by_type(report):
    """Which is why the call count is the test and the interface is not.

    Decorator and Proxy both satisfy the same protocol, both take an inner of
    that protocol, and both return the declared type. No type system
    separates them; only behaviour does.
    """
    deco, prox = GzipDecorator(report), CachingProxy(report)

    assert isinstance(deco, Renderer) and isinstance(prox, Renderer)
    assert isinstance(report, Renderer), "and so does the thing they wrap"


# ── the two easy discriminators ────────────────────────────────────────────


def test_adapter_changes_the_interface():
    """The discriminator: what goes in is not shaped like what comes out.

    If a wrapper's interface matches the thing it wraps, it is not an adapter,
    whatever the class is called.
    """
    legacy = LegacyReport(list(ROWS))

    assert not hasattr(legacy, "render"), "the third party has the wrong shape"
    assert not isinstance(legacy, Renderer)

    adapted = LegacyAdapter(legacy)

    assert isinstance(adapted, Renderer), "and the adapter has the right one"
    assert adapted.render() == Report(list(ROWS)).render()


def test_a_facade_wraps_many_objects_behind_a_new_interface(report):
    """The discriminator is the count. One object is never a facade.

    A facade exists because a caller would otherwise have to know a *sequence*
    across several objects -- render, store, notify -- and that sequence is
    what is being hidden, not any single call.
    """
    storage, notifier = Storage(), Notifier()
    facade = ReportingFacade(storage, notifier)

    url = facade.publish(report, "daily.txt", "ops@example.dev")

    assert url == "s3://reports/daily.txt"
    assert storage.saved["daily.txt"], "object one did its part"
    assert notifier.sent == ["ops@example.dev: s3://reports/daily.txt"], "object two did too"
    assert not isinstance(facade, Renderer), "and it does not pretend to be a Renderer"


def test_a_facade_does_not_make_the_subsystem_unreachable(report):
    """The failure it avoids: becoming the only door, and then a god object.

    A caller who needs `storage.put` directly can still have it. The moment a
    facade is the only way in, every capability some caller eventually needs
    has to be added to it -- which is exactly how an API gateway erodes.
    """
    storage = Storage()
    ReportingFacade(storage, Notifier()).publish(report, "a.txt", "x@y.dev")

    storage.put("b.txt", b"direct")              # straight past the facade

    assert set(storage.saved) == {"a.txt", "b.txt"}


# ── what the usual treatment leaves out ────────────────────────────────────


def test_decorator_order_is_part_of_the_design():
    """Both stacks type-check. Both run. One is 120x larger.

    Encrypted bytes have no exploitable structure, so compressing them gains
    nothing -- the output is *bigger* than the input once zlib's framing is
    added. Compress first and the same two decorators give a 100x reduction.

    Nothing at the call site shows which order you picked, which is the real
    hazard: `Gzip(Encrypt(r))` and `Encrypt(Gzip(r))` differ by six characters
    and are different systems. In middleware the same property is the security
    model -- auth-then-log and log-then-auth are not the same stack.
    """
    raw = Report(list(ROWS)).render()
    wrong = GzipDecorator(EncryptDecorator(Report(list(ROWS)))).render()
    right = EncryptDecorator(GzipDecorator(Report(list(ROWS)))).render()

    assert len(right) * 50 < len(wrong), f"{len(right)} vs {len(wrong)}"
    assert len(wrong) > len(raw), "compressing ciphertext costs more than it saves"
    assert len(right) < len(raw) // 50, "compressing first works"


def test_a_lazy_proxy_is_the_n_plus_one_problem():
    """One hundred attribute reads, one hundred round trips, no loop in sight.

    This is every ORM's lazy-loaded relation. The call site reads like it is
    touching fields on objects it already has, and each touch is a query. The
    only way to find it in a real system is to instrument the driver and
    count -- which is what `QUERIES` is.
    """
    store = {f"k{i}": f"v{i}" for i in range(100)}
    rows = [LazyRow(k, store) for k in store]        # "one query" to list them

    assert QUERIES == [], "constructing the proxies touched nothing"

    values = [r.value for r in rows]                 # looks like attribute access

    assert len(values) == 100
    assert len(QUERIES) == 100, "1 + N, and the N is invisible at the call site"


def test_the_lazy_proxy_loads_at_most_once_per_row():
    """It is still a proxy, so re-reading is free. The cost is the first touch."""
    store = {"a": "1"}
    row = LazyRow("a", store)

    assert row.value == "1"
    assert row.value == "1"
    assert QUERIES == ["a"], "cached after the first round trip"


def test_getattr_forwarding_silently_drops_dunders(report):
    """The trap in every "let's not write one method per interface method".

    `__getattr__` forwards ordinary attribute lookups and is **never consulted
    for special methods**, because Python looks those up on the type rather
    than on the instance. So the wrapper is a drop-in replacement right up
    until someone calls `len()`, indexes it, iterates it, compares it or puts
    it in an f-string.

    The failure is quiet in the worst way: the wrapper works in every test
    that calls methods, and breaks in the one place that uses a builtin.
    """
    wrapped = MagicWrapper(report)

    assert wrapped.render(), "ordinary methods forward fine"
    assert wrapped.rows == ROWS, "so do attributes"
    assert len(report) == 400, "and the inner object supports len()"

    with pytest.raises(TypeError, match="has no len"):
        len(wrapped)                                 # ← never reaches __getattr__


def test_every_wrapper_must_forward_every_method(report):
    """The tax, counted: a new interface method is an edit in each wrapper.

    `Renderer` has one method today, so this is cheap. At five methods and
    four wrappers it is twenty delegating bodies, and adding a sixth is four
    edits -- the same O(N) asymmetry Abstract Factory charges for a new
    product, for the same structural reason.
    """
    wrappers = [GzipDecorator(report), CachingProxy(report),
                LegacyAdapter(LegacyReport(list(ROWS)))]

    for w in wrappers:
        assert isinstance(w, Renderer), f"{type(w).__name__} implements the protocol"
        assert "render" in vars(type(w)), "by hand, in its own class body"
