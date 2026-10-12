"""Tests that assert the defining properties, not that the code runs.

Three pairs, each contrasting the correct builder with the wrong one that
people actually ship, because every bug here looks fine by inspection.

**Where validation lives.** `test_a_cross_field_invariant_cannot_be_checked_in
_a_setter` is the argument for `build()` in executable form: `timeout` and
`retries` are individually valid at every value this test uses, and together
they are not. A setter cannot see the field that has not been set yet, so a
per-setter check either rejects a legal call or makes call order significant.

**What reuse leaks.** `test_a_reusable_builder_leaks_the_previous_build`
against `test_a_single_use_builder_refuses_the_second_build`. Same two builds,
same change in between: one silently inherits the first request's retries, the
other raises.

**What `frozen=True` does not do.** `test_handing_over_the_mutable_object
_defeats_frozen` -- a frozen dataclass holding a shared dict is not immutable,
and the already-built object changes under its owner after it was handed out.
That one is the nastiest, because the type says the object cannot change.
"""

from __future__ import annotations

import dataclasses

import pytest

from builder import (
    InvalidRequest,
    LeakyBuilder,
    Provisioner,
    Request,
    RequestBuilder,
    RequestConfig,
    variant_of,
)

URL = "https://api.example.com"


# ── where validation lives ──────────────────────────────────────────────────


def test_a_cross_field_invariant_cannot_be_checked_in_a_setter():
    """30s and 10 retries are each perfectly legal. The pair is not.

    This is the whole argument for validating in `build()`. Whichever setter
    runs first cannot see the other field, so a per-setter check has two
    options and both are wrong: reject a legal call because the partner field
    has not arrived yet, or let it through and make call order significant.

    `build()` is the first moment every field exists simultaneously, which
    makes it the only place a complete invariant can be enforced.
    """
    assert RequestBuilder(URL).timeout(30).build().timeout_s == 30
    assert RequestBuilder(URL).retries(10).timeout(1).build().retries == 10

    with pytest.raises(InvalidRequest) as e:
        RequestBuilder(URL).timeout(30).retries(10).build()
    assert "120s budget" in str(e.value)

    # And order does not matter, which is the property per-setter checks lose.
    with pytest.raises(InvalidRequest):
        RequestBuilder(URL).retries(10).timeout(30).build()


def test_per_setter_validation_catches_only_the_single_field_cases():
    """The leaky builder's setter check is not useless -- it is insufficient.

    Worth separating, because "validate in build()" is often read as "setter
    validation is wrong". It is not wrong, it is partial: a single-field rule
    works fine in a setter and gives a faster error. It simply cannot be the
    only place, and the fields that matter most are usually the paired ones.
    """
    with pytest.raises(InvalidRequest):
        LeakyBuilder(URL).retries(-1)                    # single field: caught

    assert LeakyBuilder(URL).retries(10).build()["retries"] == 10   # the pair: not


def test_the_builder_rejects_what_the_dataclass_rejects():
    """Two implementations of the same rules must not drift apart."""
    bad = [("ftp://x", 30, 0), (URL, 0, 0), (URL, -1, 0), (URL, 30, 10)]
    for url, timeout, retries in bad:
        with pytest.raises(InvalidRequest):
            RequestBuilder(url).timeout(timeout).retries(retries).build()
        with pytest.raises(InvalidRequest):
            RequestConfig(url, timeout_s=timeout, retries=retries)


# ── what reuse leaks ────────────────────────────────────────────────────────


def test_a_reusable_builder_leaks_the_previous_build():
    """Change the url, build again, and inherit everything you did not set.

    The documented footgun of this pattern, and it is quiet: the second
    request is a perfectly valid object that nobody asked for. Nothing raises,
    nothing logs, and the retry count came from a request built somewhere
    else entirely.
    """
    leaky = LeakyBuilder("https://a.dev").retries(5).header("auth", "token-a")
    first = leaky.build()

    second = leaky.url("https://b.dev").build()

    assert second["url"] == "https://b.dev", "the part that was intended"
    assert second["retries"] == 5, "and the part that was not"
    assert second["headers"]["auth"] == "token-a", "including someone's credential"


def test_a_single_use_builder_refuses_the_second_build():
    """Same two builds. This one is an error instead of a surprise."""
    b = RequestBuilder("https://a.dev").timeout(5).retries(5)   # 30s worst case, within budget
    assert b.build().retries == 5

    with pytest.raises(InvalidRequest) as e:
        b.build()
    assert "already produced" in str(e.value)


def test_replace_is_what_people_actually_wanted_from_reuse():
    """An immutable product makes the safe version a one-liner.

    `dataclasses.replace` gives a new object with some fields changed, sharing
    nothing mutable, with no builder left in a dirty state. If the product is
    frozen this is strictly better than reusing a builder, which is most of
    why the product should be frozen.
    """
    base = RequestBuilder(URL).retries(2).header("auth", "t").build()
    other = variant_of(base, url="https://b.dev")

    assert other.url == "https://b.dev"
    assert other.retries == 2 and other.header("auth") == "t", "carried deliberately"
    assert base.url == URL, "and the original is untouched"
    assert base is not other


# ── what frozen=True does not do ────────────────────────────────────────────


def test_handing_over_the_mutable_object_defeats_frozen():
    """The object was built, handed out, and then changed. By its builder.

    The nastiest bug in this file, because every signal says it cannot happen:
    the product is "immutable", the caller holds it, nobody else has a
    reference. Except the builder does -- it passed its own dict rather than a
    copy, so the two share one object and the builder is still alive.

    `frozen=True` freezes the *bindings*, not the objects behind them.
    """
    leaky = LeakyBuilder(URL).header("x", "1")
    built = leaky.build()
    assert set(built["headers"]) == {"x"}

    leaky.header("y", "2")                      # nobody touched `built`

    assert set(built["headers"]) == {"x", "y"}, "it changed anyway"


def test_copying_on_the_way_out_is_what_makes_the_product_immutable():
    """One `tuple(...)` in `build()`, and the seam closes."""
    b = RequestBuilder(URL).header("x", "1")
    built = b.build()

    b.header("y", "2")                          # the builder moves on

    assert built.headers == (("x", "1"),), "the product did not"
    with pytest.raises(dataclasses.FrozenInstanceError):
        built.url = "https://evil.dev"          # type: ignore[misc]
    assert isinstance(built.headers, tuple), "immutable all the way down"


# ── what Python needs instead ───────────────────────────────────────────────


def test_a_dataclass_does_what_the_builder_does_in_five_lines():
    """Same object, same rules, no builder.

    Java needs Builder because it has neither keyword arguments nor default
    parameter values. Python has both, so the call site is already readable
    and the optionality is already expressed. `__post_init__` validates at the
    same moment `build()` does, and for the same reason -- it is the first
    point where every field exists.
    """
    built = RequestBuilder(URL).method("POST").timeout(5).retries(2).build()
    direct = RequestConfig(URL, method="POST", timeout_s=5, retries=2)

    assert dataclasses.asdict(built) == dataclasses.asdict(direct)
    assert isinstance(built, Request) and isinstance(direct, RequestConfig)


# ── the distributed lesson ──────────────────────────────────────────────────


def test_a_half_built_stack_is_already_live():
    """By the time `build()` could validate, the money is already being spent.

    The local intuition -- accumulate, check at the end, produce an object --
    does not survive the network. Each step is a separate API call to a system
    that has already committed, so there is no end to validate at. A failure
    leaves real resources running.

    Which is why the useful property here is not "validate last" but **know
    what was created before the failure**, and why infrastructure tools keep a
    state file instead of a builder.
    """
    p = Provisioner(fail_on="database")

    with pytest.raises(RuntimeError) as e:
        p.add("vpc").add("subnet").add("database").add("cache")

    assert p.created == ["vpc", "subnet"], "two resources are live and billable"
    assert "cache" not in p.created, "and the rest never happened"
    assert "billable" in str(e.value), "the error has to say what was left behind"


def test_the_successful_path_still_builds_everything_in_order():
    """A failure test that never passes is as useless as one that never fails."""
    p = Provisioner()
    p.add("vpc").add("subnet").add("database").add("cache")
    assert p.created == ["vpc", "subnet", "database", "cache"]
