"""Tests that assert the defining properties, not that the code runs.

The headline is `test_the_dangerous_clone_is_the_one_that_does_not_raise`, and
its partner `test_one_unpicklable_field_guards_the_whole_object` is the reason
it needed writing twice.

Python looks like it protects you here. Copying a `threading.Lock` or a
`socket` raises immediately, shallow and deep alike -- and because one
unpicklable field makes the entire object uncopyable, a class that happens to
hold a lock inherits that guard. The first version of these tests had a lock
on `Document`, so `copy.deepcopy(doc)` raised and the headline claim was false
of the object written to demonstrate it.

That is the real lesson and it is now two tests: the guard is **incidental**.
It comes from a field whose purpose is thread-safety, not copy semantics, and
a refactor that moves locking up a layer removes it with nothing failing.
`Document` has no lock and copies silently -- two objects, one primary key.
`ConcurrentDocument` differs by one field and refuses.

`test_an_explicit_clone_resets_identity_connection_and_cache` is the fix, and
its assertions are the decisions every clone method has to make. A `clone()`
whose body is `return deepcopy(self)` has not made them; it has deferred them
to whoever first notices the duplicate rows.

`test_cloning_skips_the_expensive_construction` is the only test here
asserting a reason to *use* the pattern rather than a hazard, and it counts
rather than claims: five spawns, zero constructions.
"""

from __future__ import annotations

import copy
import socket
import threading

import pytest

from prototype import BUILDS, ConcurrentDocument, Connection, Document, PrototypeRegistry


@pytest.fixture
def doc() -> Document:
    return Document.expensive("Report", ["intro", "body"])


# ── headline pair: what copies silently, and what a clone must reset ───────


def test_the_dangerous_clone_is_the_one_that_does_not_raise(doc):
    """`deepcopy` succeeds and hands back a second object with the same id.

    Nothing in `Document` is unpicklable, so both copy functions work. The
    result is two objects that each believe they are row N, sharing one
    connection handle. In production this surfaces weeks later as a unique
    constraint violation on a table that has been collecting duplicates, and
    the traceback points at the insert rather than at the copy.
    """
    twin = copy.deepcopy(doc)

    assert twin is not doc
    assert twin.id == doc.id, "IDENTITY was inherited, and nothing complained"
    assert twin.conn is not None, "so was the connection"
    assert twin.conn.dsn == doc.conn.dsn


def test_an_explicit_clone_resets_identity_connection_and_cache(doc):
    """The decisions, one assertion each. This is the whole pattern.

    `clone()` is not "make a copy", it is "make a copy and say what does not
    come with it". Deep-copy the payload; reset identity, connection and
    cache. Every clone method in any codebase answers these questions, whether
    or not its author noticed.
    """
    doc.render()                                  # warm the cache first
    assert doc._render_cache, "precondition: the prototype has a cached rendering"

    c = doc.clone(title="Report (draft)")

    assert c.id != doc.id, "IDENTITY: a new row, not a duplicate"
    assert c.conn is None, "CONNECTION: dropped, so the clone must be given one"
    assert c._render_cache == {}, "CACHE: empty, not the prototype's rendering"
    assert c.title == "Report (draft)", "and the override applied"


def test_a_clone_that_is_just_deepcopy_has_not_decided_anything(doc):
    """Stated as a contrast, because `return deepcopy(self)` is what gets written.

    Not that deepcopy is wrong -- that it answers none of the questions above,
    and answers them all the same way: inherit everything.
    """
    lazy = copy.deepcopy(doc)
    deliberate = doc.clone()

    assert lazy.id == doc.id and deliberate.id != doc.id
    assert lazy.conn is not None and deliberate.conn is None


# ── the guard that is an accident ──────────────────────────────────────────


def test_one_unpicklable_field_guards_the_whole_object():
    """Two classes, one field apart. One copies silently, one refuses.

    The difference is `_lock`, whose purpose is thread-safety and which has
    nothing to do with copy semantics. So the protection is not something the
    design earned -- it is a side effect of a field type, and the day someone
    moves locking up a layer it disappears with no test failing.

    This file's first draft had the lock on `Document` and therefore proved
    the opposite of what it claimed.
    """
    plain = copy.deepcopy(Document("Unlocked", ["a"]))
    assert plain.id == 1 or plain.title == "Unlocked", "the parent copies fine"

    with pytest.raises(TypeError, match="pickle"):
        copy.deepcopy(ConcurrentDocument("Locked", ["a"]))


def test_a_lock_is_never_shared_and_never_copied():
    """Both obvious answers are wrong; only a fresh lock is correct.

    Sharing one makes two logically independent objects serialise against each
    other. Copying one -- if Python allowed it -- would leave neither
    protected. `clone` gets a new lock from the default factory, which is the
    only value that is right.
    """
    cd = ConcurrentDocument("Locked", ["a"])
    c = cd.clone()

    assert isinstance(c, ConcurrentDocument), "clone preserves the subclass"
    assert c._lock is not cd._lock
    assert c.id != cd.id


@pytest.mark.parametrize("make", [threading.Lock, threading.RLock, socket.socket],
                         ids=["Lock", "RLock", "socket"])
@pytest.mark.parametrize("fn", [copy.copy, copy.deepcopy], ids=["shallow", "deep"])
def test_python_refuses_to_copy_a_live_handle(make, fn):
    """Both copy functions raise, for all three -- shallow included.

    Worth pinning precisely, because "you can't copy objects with handles" is
    often remembered as a general safety net. It is a net with one specific
    hole, and the next test is the hole.
    """
    obj = make()
    try:
        with pytest.raises(TypeError, match="pickle"):
            fn(obj)
    finally:
        if isinstance(obj, socket.socket):
            obj.close()


def test_a_connection_held_as_a_plain_object_copies_happily():
    """The hole in that net, isolated.

    A raw socket raises and saves you. A connection *wrapper*, a pool handle,
    a cursor proxy or a client object holding a session token usually will not.
    """
    c = Connection("db://primary")
    twin = copy.deepcopy(c)

    assert twin is not c
    assert twin.dsn == c.dsn and twin.open is True, "a second object claiming one session"


# ── shallow against deep ───────────────────────────────────────────────────


def test_a_shallow_copy_shares_the_payload(doc):
    """`copy.copy` copies the bindings. The list behind one of them is shared."""
    shallow = copy.copy(doc)
    shallow.sections.append("appendix")

    assert doc.sections == ["intro", "body", "appendix"], "the original changed"
    assert shallow.sections is doc.sections, "because it is literally one list"


def test_a_deep_copy_and_a_clone_both_separate_the_payload(doc):
    """The half everyone gets right, kept so the contrast above is honest."""
    for other in (copy.deepcopy(doc), doc.clone()):
        other.sections.append("appendix")
        assert doc.sections == ["intro", "body"], "the original is untouched"
        assert other.sections is not doc.sections


# ── why the pattern exists at all ──────────────────────────────────────────


def test_cloning_skips_the_expensive_construction():
    """Five documents, zero constructions. Counted, not claimed.

    Construction is expensive and the state you want only exists at runtime --
    a parsed template, a warmed model, an entity configured by a level
    designer rather than by a constructor. You cannot write that as a literal,
    so you prepare one and copy it.
    """
    reg = PrototypeRegistry()
    reg.register("report", Document.expensive("Template", ["a", "b"]))

    before = len(BUILDS)
    spawned = [reg.spawn("report", title=f"doc-{i}") for i in range(5)]

    assert len(BUILDS) == before, "no expensive construction ran"
    assert len({d.id for d in spawned}) == 5, "and every spawn has its own identity"
    assert all(d.sections == ["a", "b"] for d in spawned)

    spawned[0].sections.append("extra")
    assert spawned[1].sections == ["a", "b"], "siblings do not share the payload"


def test_the_template_itself_is_never_mutated_by_a_spawn():
    """A registry whose prototypes drift is worse than no registry.

    If a spawn can reach back into the template, every later spawn inherits
    the change -- and the symptom is that documents created after lunch differ
    from documents created before it, with nothing in any diff to explain why.
    """
    reg = PrototypeRegistry()
    template = Document.expensive("Template", ["a"])
    reg.register("t", template)

    reg.spawn("t").sections.append("contaminated")

    assert template.sections == ["a"]
    assert reg.spawn("t").sections == ["a"], "the next spawn is still clean"
