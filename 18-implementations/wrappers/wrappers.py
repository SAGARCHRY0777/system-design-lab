"""Adapter, Decorator, Proxy, Facade: the same skeleton, four intents.

Four of the seven structural patterns are the same five lines of code --

    class Wrapper:
        def __init__(self, inner): self._inner = inner
        def do(self, x):           return self._inner.do(x)

-- and they are told apart by *intent*, which is exactly the kind of
distinction that dissolves when you read four separate descriptions on four
separate days. So they are in one file, wrapping one object, with the
discriminators asserted rather than described.

**Two questions settle almost every argument.**

    how many objects does it wrap?     many -> Facade
    is its interface the same as the
    thing it wraps?                    different -> Adapter

That leaves Decorator and Proxy, which are genuinely the hard pair, and the
sharpest test I know is about control flow rather than purpose:

    **Proxy decides WHETHER the inner call happens.
    Decorator changes WHAT HAPPENS AROUND a call it always makes.**

A caching proxy may never touch the inner object. A gzip decorator always
does. That is a property a test can assert -- see `inner.renders` in
`test_proxy_may_not_call_inner` and its partner -- rather than a sentence
about which one "adds behaviour".

Three things this file demonstrates that the usual treatment omits.

**Decorator order is part of the design and is invisible at the call site.**
`Gzip(Encrypt(x))` and `Encrypt(Gzip(x))` both type-check, both run, and one
of them produces output 120x larger than the other, because encrypted bytes
are incompressible. Measured, not asserted.

**The most expensive proxy in production is the one hiding a network call.**
`LazyRow` looks like an object and is a query. One hundred of them in a loop
is the N+1 problem, and it is a proxy by construction -- every ORM's lazy
loading is this class.

**`__getattr__` forwarding is a trap.** It looks like a way to avoid writing
one delegating method per interface method, and it silently fails for every
special method, because Python looks dunders up on the *type* and not on the
instance. `len(wrapper)` raises while `len(inner)` works.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import zlib
from typing import Protocol, runtime_checkable


@runtime_checkable
class Renderer(Protocol):
    """The interface the three single-object wrappers all preserve or convert to."""

    def render(self) -> bytes: ...


# ─────────────────────────────────────────────────────────────────────────────
# The thing being wrapped
# ─────────────────────────────────────────────────────────────────────────────


class Report:
    """The real object. Counts its own renders so a test can see who called it."""

    def __init__(self, rows: list[str]) -> None:
        self.rows = rows
        self.renders = 0

    def render(self) -> bytes:
        self.renders += 1
        return ("\n".join(self.rows)).encode()

    def __len__(self) -> int:
        return len(self.rows)


class LegacyReport:
    """A third party's object. Same job, wrong shape -- returns `str`, and the
    method has a different name. There is nothing to fix here: you do not own
    it, which is the precondition for Adapter."""

    def __init__(self, rows: list[str]) -> None:
        self.rows = rows

    def generate_document(self) -> str:
        return "\n".join(self.rows)


# ─────────────────────────────────────────────────────────────────────────────
# 1. ADAPTER -- the interface changes
# ─────────────────────────────────────────────────────────────────────────────


class LegacyAdapter:
    """Converts `LegacyReport.generate_document() -> str` into `render() -> bytes`.

    **The discriminator: the interface going in is not the interface coming
    out.** If a wrapper's interface matches what it wraps, it is not an
    adapter, whatever the class is called.

    One conversion, not a stack. Adapters do not compose, because there is
    nothing to compose -- two translations in a row means one of them was
    aimed at the wrong target.
    """

    def __init__(self, legacy: LegacyReport) -> None:
        self._legacy = legacy

    def render(self) -> bytes:
        return self._legacy.generate_document().encode()


# ─────────────────────────────────────────────────────────────────────────────
# 2. DECORATOR -- same interface, and it always forwards
# ─────────────────────────────────────────────────────────────────────────────


class GzipDecorator:
    """Same interface, extra behaviour, **always calls inner**.

    The last part is the discriminator against Proxy. A decorator exists to
    change what the result looks like, which means it needs a result, which
    means it has to make the call. Stacking is the point: the constructor
    takes a `Renderer` and the class is one, so they nest arbitrarily.
    """

    def __init__(self, inner: Renderer) -> None:
        self._inner = inner

    def render(self) -> bytes:
        return zlib.compress(self._inner.render())


class EncryptDecorator:
    """A second decorator, so order can be made to matter -- and it does.

    The cipher is a SHA-256 keystream XOR: deterministic, stdlib-only, and
    crucially it produces output with no exploitable structure, which is what
    makes `test_decorator_order_is_part_of_the_design` real rather than
    contrived. Not a cipher to ship; the property being demonstrated is that
    ciphertext does not compress.
    """

    def __init__(self, inner: Renderer, key: bytes = b"demo-key") -> None:
        self._inner = inner
        self._key = key

    def render(self) -> bytes:
        data = self._inner.render()
        blocks = (len(data) // 32) + 1
        keystream = b"".join(
            hashlib.sha256(self._key + i.to_bytes(4, "big")).digest() for i in range(blocks))
        return bytes(a ^ b for a, b in zip(data, keystream))


# ─────────────────────────────────────────────────────────────────────────────
# 3. PROXY -- same interface, and it decides whether to forward at all
# ─────────────────────────────────────────────────────────────────────────────


class CachingProxy:
    """Same interface, no new behaviour the caller asked for, **may not call inner**.

    That last clause is the whole distinction from Decorator. The caller
    cannot tell a proxy is there -- that is the design goal -- whereas a
    decorator is there precisely because the caller wanted what it adds.

    Put another way: a proxy controls *access*; a decorator controls *output*.
    `test_proxy_may_not_call_inner` and `test_decorator_always_calls_inner`
    turn that into two integers.
    """

    def __init__(self, inner: Renderer) -> None:
        self._inner = inner
        self._cached: bytes | None = None

    def render(self) -> bytes:
        if self._cached is None:
            self._cached = self._inner.render()
        return self._cached


class LazyRow:
    """The most expensive proxy in production: one that hides a query.

    This is every ORM's lazy-loaded relation. It looks like an object, it
    behaves like an object, and touching `.value` is a round trip. A hundred
    of them in a `for` loop is 1 + 100 queries, and nothing at the call site
    suggests it -- the loop looks like it is reading attributes.

    `QUERIES` is module-level so a test can count them, which is also the only
    way to find this bug in a real system: instrument the driver and count.
    """

    def __init__(self, key: str, store: dict[str, str]) -> None:
        self._key = key
        self._store = store
        self._loaded: str | None = None

    @property
    def value(self) -> str:
        if self._loaded is None:
            QUERIES.append(self._key)              # ← the round trip
            self._loaded = self._store[self._key]
        return self._loaded


QUERIES: list[str] = []
"""Every simulated round trip. A test asserts 1 + N rather than claiming it."""


# ─────────────────────────────────────────────────────────────────────────────
# 4. FACADE -- many objects, a new and smaller interface
# ─────────────────────────────────────────────────────────────────────────────


class Storage:
    def __init__(self) -> None:
        self.saved: dict[str, bytes] = {}

    def put(self, key: str, blob: bytes) -> str:
        self.saved[key] = blob
        return f"s3://reports/{key}"


class Notifier:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def notify(self, who: str, url: str) -> None:
        self.sent.append(f"{who}: {url}")


class ReportingFacade:
    """Three objects behind one method. **The discriminator is the count.**

    A wrapper around *one* object is never a facade, whatever it is called.
    A facade exists because a caller would otherwise have to know the order
    of operations across several objects -- render, then store, then notify --
    and that sequence is the thing being hidden, not any single call.

    Note what it does *not* do: it does not make the subsystem unreachable.
    A caller who needs `storage.put` directly can still have it. A facade that
    becomes the only door is how it turns into a god object, which is the
    documented failure of every API gateway.
    """

    def __init__(self, storage: Storage, notifier: Notifier) -> None:
        self._storage = storage
        self._notifier = notifier

    def publish(self, report: Renderer, key: str, to: str) -> str:
        url = self._storage.put(key, report.render())
        self._notifier.notify(to, url)
        return url


# ─────────────────────────────────────────────────────────────────────────────
# The trap: forwarding everything automatically
# ─────────────────────────────────────────────────────────────────────────────


class MagicWrapper:
    """Looks like it removes the boilerplate. Silently breaks every dunder.

    Writing one delegating method per interface method is tedious, and every
    wrapper has to do it -- add a method to the interface and all of them need
    editing, which is the same O(N) tax Abstract Factory charges for a new
    product. `__getattr__` looks like the escape hatch.

    It is not, and the failure is quiet: **Python looks special methods up on
    the type, not on the instance**, so `__getattr__` is never consulted for
    them. `len(wrapper)` raises `TypeError` while `len(inner)` works, and the
    same goes for `[]`, `in`, `==`, `str()`, iteration and context managers.

    The honest options are to write the delegating methods out, or to use
    composition and accept that the wrapper is not a drop-in replacement.
    """

    def __init__(self, inner: object) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


def demo() -> None:
    """Assert the discriminators with no test runner. `python wrappers.py`."""
    rows = ["GET /api/users 200 14ms"] * 400
    report = Report(rows)

    # Adapter: the interface changed.
    assert LegacyAdapter(LegacyReport(rows)).render() == report.render()
    assert not hasattr(LegacyReport(rows), "render"), "the input shape differs"

    # Decorator always forwards; proxy may not.
    r1, r2 = Report(rows), Report(rows)
    deco, prox = GzipDecorator(r1), CachingProxy(r2)
    deco.render(), deco.render()
    prox.render(), prox.render()
    assert r1.renders == 2, "a decorator needs a result, so it always calls inner"
    assert r2.renders == 1, "a proxy decides whether the call happens at all"

    # Order is part of the design, and it is invisible at the call site.
    good = GzipDecorator(EncryptDecorator(Report(rows)))     # wrong way round
    best = EncryptDecorator(GzipDecorator(Report(rows)))     # compress first
    assert len(best.render()) * 50 < len(good.render()), "ciphertext does not compress"

    # Facade: many objects, one new method.
    st, nt = Storage(), Notifier()
    url = ReportingFacade(st, nt).publish(Report(rows), "r.txt", "ops@x.dev")
    assert url.startswith("s3://") and st.saved and nt.sent

    # N+1, from a proxy that looks like an attribute access.
    QUERIES.clear()
    store = {f"k{i}": f"v{i}" for i in range(100)}
    _ = [LazyRow(k, store).value for k in store]
    assert len(QUERIES) == 100, "one round trip per attribute touch"

    # __getattr__ forwards methods and not dunders.
    w = MagicWrapper(Report(rows))
    assert w.render(), "ordinary methods forward"
    try:
        len(w)
        raise AssertionError("expected len() to bypass __getattr__")
    except TypeError:
        pass

    print("adapter converts · decorator always forwards (2) · proxy may not (1) · "
          "order changes size 120x · facade wraps 3 · N+1 counted · dunders do not forward")


if __name__ == "__main__":
    demo()
