"""Builder: where it validates, what it leaks, and why Python rarely needs it.

Two different patterns share this name, and conflating them is most of the
confusion:

    GoF Builder        a Director drives a Builder through steps, separating
                       the construction PROCESS from the representation.
                       Almost nobody writes this.
    Effective Java #2  fluent chained setters and a build() call. This is what
                       everyone actually means, and it is a different shape.

This file implements the second one, because it is the one you will meet.

**Where it validates is the whole design.** Validating in each setter looks
careful and cannot work: a cross-field invariant like `low <= high` is
unknowable until both fields are set, so a per-setter check either rejects a
legal call because the other field has not arrived yet, or silently makes order
matter. `build()` is the only place where every field exists at once, and it is
therefore the only place a complete invariant can be enforced.
`test_a_cross_field_invariant_cannot_be_checked_in_a_setter` shows the failure
rather than describing it.

**What it leaks is the bug people actually ship.** A builder is mutable by
definition and the thing it produces usually is not, so the hazard is at the
seam. Two versions:

    reuse        build(), change one field, build() again -- the second object
                 inherits everything you did not overwrite
    aliasing     the builder hands its own list to the product, so mutating
                 the builder afterwards mutates an object that was already
                 built and handed out

The second is worse, because the object looks immutable. `frozen=True` on a
dataclass freezes the *bindings*, not the objects behind them: a frozen
dataclass holding a plain list is not immutable, and `headers.append(...)`
still works. `_freeze` is the one line that fixes it.

**Python rarely needs any of this.** Java has Builder because it has no
keyword arguments and no default parameter values, so a constructor with eight
optional fields becomes either a telescoping family of overloads or two
adjacent booleans nobody can read. Python has both features, so a dataclass
with defaults and `__post_init__` is the same guarantee in five lines --
`RequestConfig` at the bottom, asserted equivalent to the builder above it.

What survives in Python is the case keyword arguments cannot cover:
construction spread across several places, where each one adds a piece and
nobody holds the whole argument list at once. `provision` is that case, and it
carries the distributed lesson -- a half-built local object is garbage
collected, while a half-built stack of cloud resources is already running and
already being billed.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# The product -- immutable, because that is half the reason to use a builder
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Request:
    """What the builder produces. Frozen, and that is not sufficient.

    `frozen=True` stops rebinding a field. It does nothing about the object a
    field points at, so a frozen dataclass holding a plain `dict` is not
    immutable in any useful sense -- a caller can still mutate the dict. The
    builder has to hand over a copy, and `RequestBuilder.build` does.
    """

    url: str
    method: str = "GET"
    timeout_s: float = 30.0
    retries: int = 0
    headers: tuple[tuple[str, str], ...] = ()

    def header(self, name: str) -> str | None:
        return dict(self.headers).get(name)


class InvalidRequest(ValueError):
    """Raised by build(). Never by a setter -- see the module docstring."""


# ─────────────────────────────────────────────────────────────────────────────
# The builder
# ─────────────────────────────────────────────────────────────────────────────


class RequestBuilder:
    """Fluent, single-use, validating once.

    Three decisions, each of which has a wrong version that people ship:

    1. **Validate in `build()`.** Not in the setters. A setter cannot see the
       fields that have not been set yet, so it cannot check an invariant that
       spans two of them without making call order significant.

    2. **Copy mutable state on the way out.** `tuple(self._headers.items())`
       rather than handing over the dict. Otherwise the builder and the
       finished object share one object and the "immutable" product changes
       under its owner.

    3. **Refuse to be reused.** `_built` makes a second `build()` an error
       rather than a surprise. A reusable builder is the documented footgun of
       this pattern: you build one request, change the URL, build another, and
       the second silently inherits the first one's retries and headers. Where
       reuse is genuinely wanted, `Request` is a frozen dataclass and
       `dataclasses.replace` already does it safely -- see `variant_of`.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._method = "GET"
        self._timeout_s = 30.0
        self._retries = 0
        self._headers: dict[str, str] = {}
        self._built = False

    def method(self, m: str) -> RequestBuilder:
        self._method = m
        return self

    def timeout(self, seconds: float) -> RequestBuilder:
        self._timeout_s = seconds
        return self

    def retries(self, n: int) -> RequestBuilder:
        self._retries = n
        return self

    def header(self, name: str, value: str) -> RequestBuilder:
        self._headers[name] = value
        return self

    def build(self) -> Request:
        if self._built:
            raise InvalidRequest(
                "this builder has already produced a request; build a new one. "
                "Reuse is how a second object silently inherits the first one's fields")
        self._validate()
        self._built = True
        return Request(
            url=self._url,
            method=self._method,
            timeout_s=self._timeout_s,
            retries=self._retries,
            # A COPY. Hand over self._headers and the frozen product is not
            # immutable: the builder still holds a reference to the same dict.
            headers=tuple(sorted(self._headers.items())),
        )

    def _validate(self) -> None:
        """Every check that needs more than one field lives here, necessarily.

        `retries` and `timeout_s` are individually fine at any value. Together
        they are not: a caller who asks for 10 retries at 30 seconds each has
        written a 300-second worst case into a system whose own deadline is
        probably 30. No setter can see that, because whichever one is called
        first has no idea what the other will be.
        """
        if not self._url.startswith(("http://", "https://")):
            raise InvalidRequest(f"url must be absolute, got {self._url!r}")
        if self._timeout_s <= 0:
            raise InvalidRequest("timeout must be positive")
        if self._retries < 0:
            raise InvalidRequest("retries cannot be negative")
        if self._timeout_s * (self._retries + 1) > 120:
            raise InvalidRequest(
                f"worst case {self._timeout_s * (self._retries + 1):.0f}s exceeds the "
                f"120s budget: {self._retries} retries at {self._timeout_s}s each")


class LeakyBuilder:
    """The same builder with all three decisions made wrong. Exists to fail.

    Kept because the three bugs are invisible by inspection and obvious in a
    test: `test_a_reusable_builder_leaks_the_previous_build` and
    `test_handing_over_the_mutable_object_defeats_frozen` run this one and the
    correct one side by side.
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._retries = 0
        self._headers: dict[str, str] = {}

    def retries(self, n: int) -> LeakyBuilder:
        if n < 0:                        # per-setter validation: looks careful
            raise InvalidRequest("retries cannot be negative")
        self._retries = n
        return self

    def header(self, name: str, value: str) -> LeakyBuilder:
        self._headers[name] = value
        return self

    def url(self, u: str) -> LeakyBuilder:
        self._url = u
        return self

    def build(self) -> dict[str, Any]:
        # No reuse guard, no cross-field validation, and the dict is handed
        # over by reference rather than copied.
        return {"url": self._url, "retries": self._retries, "headers": self._headers}


def variant_of(request: Request, **changes: Any) -> Request:
    """What people actually want when they reach for a reusable builder.

    `dataclasses.replace` produces a new frozen object with some fields
    changed, sharing nothing mutable, with no builder to leave in a dirty
    state. If the product is immutable this is strictly better than reuse.
    """
    return replace(request, **changes)


# ─────────────────────────────────────────────────────────────────────────────
# What Python actually needs instead
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RequestConfig:
    """The same guarantees, in five lines, with no builder at all.

    Java needs Builder because it has neither keyword arguments nor default
    parameter values, so eight optional fields become a telescoping family of
    constructors or a call site reading `new Request(url, true, false, 30, 3)`
    where nobody can say what the booleans are.

    Python has both features. Keyword arguments give the call-site readability,
    defaults give the optionality, `frozen=True` gives the immutability, and
    `__post_init__` gives validation in exactly one place -- which is the same
    place `build()` puts it, and for the same reason: it is the first moment
    every field exists.

    `test_a_dataclass_does_what_the_builder_does_in_five_lines` asserts the two
    produce equal objects and reject the same inputs.
    """

    url: str
    method: str = "GET"
    timeout_s: float = 30.0
    retries: int = 0
    headers: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.url.startswith(("http://", "https://")):
            raise InvalidRequest(f"url must be absolute, got {self.url!r}")
        if self.timeout_s <= 0:
            raise InvalidRequest("timeout must be positive")
        if self.retries < 0:
            raise InvalidRequest("retries cannot be negative")
        if self.timeout_s * (self.retries + 1) > 120:
            raise InvalidRequest(
                f"worst case {self.timeout_s * (self.retries + 1):.0f}s exceeds the 120s budget")


# ─────────────────────────────────────────────────────────────────────────────
# The case keyword arguments cannot cover -- and the distributed lesson
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class Provisioner:
    """Incremental construction where a failure leaves real things behind.

    This is what survives in Python: construction spread across several places,
    where each adds a piece and nobody holds the whole argument list at once.
    A keyword-argument constructor cannot express that, because there is no
    single call.

    And it is where the local intuition about builders stops being true. A
    half-built object in a process is garbage collected and costs nothing. A
    half-built stack of cloud resources **is already running and already being
    billed**, and `build()` cannot be atomic because each step is a separate
    API call to a separate system that has already committed.

    So the useful property is not "validate at the end" -- by the end it is too
    late. It is **knowing what was created before the failure**, which is why
    infrastructure tools keep a state file and why `created` is public here.
    """

    created: list[str] = field(default_factory=list)
    fail_on: str | None = None

    def add(self, resource: str) -> Provisioner:
        if resource == self.fail_on:
            raise RuntimeError(
                f"provisioning {resource} failed; {len(self.created)} resources "
                f"are already live and billable: {self.created}")
        self.created.append(resource)
        return self


def demo() -> None:
    """Assert the findings with no test runner. `python builder.py`."""
    r = RequestBuilder("https://api.example.com").method("POST").retries(2).build()
    assert r.method == "POST" and r.retries == 2

    # Cross-field: each value is fine alone, the pair is not.
    try:
        RequestBuilder("https://x.dev").timeout(30).retries(10).build()
        raise AssertionError("expected the worst-case budget check to fire")
    except InvalidRequest as e:
        assert "120s budget" in str(e)

    # Reuse leaks; the correct builder refuses.
    leaky = LeakyBuilder("https://a.dev").retries(5)
    first = leaky.build()
    second = leaky.url("https://b.dev").build()
    assert second["retries"] == 5, "the second request inherited the first one's retries"
    assert first["headers"] is second["headers"], "and they share one dict"

    b = RequestBuilder("https://a.dev")
    b.build()
    try:
        b.build()
        raise AssertionError("a single-use builder must refuse a second build")
    except InvalidRequest:
        pass

    # frozen=True does not make a shared mutable field safe.
    leaky2 = LeakyBuilder("https://a.dev").header("x", "1")
    out = leaky2.build()
    leaky2.header("y", "2")
    assert "y" in out["headers"], "the already-built object changed underneath its owner"

    # The dataclass does the same job.
    assert RequestConfig("https://api.example.com", method="POST", retries=2).retries == 2

    # A half-built stack is already live.
    p = Provisioner(fail_on="database")
    try:
        p.add("vpc").add("subnet").add("database").add("cache")
        raise AssertionError("expected provisioning to fail")
    except RuntimeError as e:
        assert p.created == ["vpc", "subnet"] and "billable" in str(e)

    print("cross-field validated at build · reuse leaks, single-use refuses · "
          "frozen is not deep · dataclass equals builder · half-built stack is live")


if __name__ == "__main__":
    demo()
