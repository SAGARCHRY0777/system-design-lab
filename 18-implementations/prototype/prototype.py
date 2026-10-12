"""Prototype: what a clone must NOT inherit.

Copying state is easy. The pattern's entire difficulty is deciding what the
copy must *not* carry over, and the list is always the same four things:
**identity, connections, locks, caches.**

Python appears to protect you here, and the protection is an accident. Ask it
to copy a `threading.Lock` or a `socket` and it refuses outright --
`TypeError: cannot pickle '_thread.lock' object`, for shallow and deep copies
alike. One unpicklable field makes the **whole object** uncopyable, so a class
that happens to hold a lock is guarded and a class that does not is wide open.

Worth stating plainly, because the first draft of this file got it wrong.
`Document` originally carried a `_lock` field, `copy.deepcopy(doc)` raised, and
the headline claim -- that the dangerous clone is the one that *succeeds* --
was false of the very object written to demonstrate it. The guard was never a
property of the design. It came from an unrelated field, and a refactor that
moves locking up a layer removes it silently, with no test failing.

So the two classes below are split deliberately. `Document` holds a row id, a
connection and a warm cache, nothing unpicklable, and copies **silently**: two
objects, one primary key, no error anywhere. `ConcurrentDocument` adds a lock
and suddenly refuses. Nothing about which one is more dangerous changed.

The other half is shallow against deep, which everyone can recite and few
check. `copy.copy` copies the attribute *bindings*, so a nested list is shared
-- mutate the clone and the original changes. `copy.deepcopy` fixes that and
brings two new problems: it is slow, and it faithfully duplicates the things
you most wanted dropped.

`Document.clone` is the answer, and the shape is always the same: deep-copy the
payload, then **explicitly reset the rest**. A `clone()` whose body is
`return deepcopy(self)` has not made a decision, it has deferred one.

The registry at the bottom is why the pattern exists at all. When construction
is expensive and the state you want only exists at runtime -- a parsed
template, a warmed model, an entity configured by a level designer rather than
by a constructor -- you clone a prepared instance instead of running setup
again. `BUILDS` counts the setup that cloning skips.

Stdlib only.
"""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from itertools import count

_ids = count(1)
BUILDS: list[str] = []
"""Every expensive construction appends here, so a test can assert that
cloning skipped it rather than take the claim on faith."""


class Connection:
    """Stands in for anything holding a live handle: a cursor, a channel, a
    pooled session, a client carrying an auth token.

    Deliberately picklable, because the dangerous clone is the one that
    succeeds. A raw socket would raise and save you; a connection *wrapper*
    usually will not.
    """

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.open = True

    def __repr__(self) -> str:
        return f"<Connection {self.dsn} open={self.open}>"


@dataclass
class Document:
    """A prototype. Expensive to build, cheap to copy -- and full of traps.

    Three fields that must not be inherited by a copy, one of each kind:

        id             IDENTITY. Two objects with one primary key is the
                       classic production bug, and it surfaces as a constraint
                       violation on a table that has been quietly collecting
                       duplicates for weeks
        conn           a CONNECTION. The clone would share the original's
                       handle, so closing one closes both, and whichever is
                       collected first takes the other's transport with it
        _render_cache  a CACHE keyed to the original's content. Inheriting it
                       means the clone serves the prototype's rendering of a
                       document it is no longer the same as

    The fourth, a LOCK, lives on `ConcurrentDocument` below rather than here,
    because adding it changes whether this class can be copied at all -- and
    hiding that inside the realistic example is what made the first draft of
    this file wrong.

    One field must be deep-copied rather than shared: `sections`.
    """

    title: str
    sections: list[str] = field(default_factory=list)
    id: int = field(default_factory=lambda: next(_ids))
    conn: Connection | None = None
    _render_cache: dict[str, str] = field(default_factory=dict, repr=False)

    @classmethod
    def expensive(cls, title: str, sections: list[str]) -> Document:
        """The construction worth avoiding. Parsing, validation, a network
        fetch -- whatever makes cloning preferable to building again."""
        BUILDS.append(title)
        return cls(title=title, sections=list(sections), conn=Connection("db://primary"))

    def clone(self, **overrides: object) -> Document:
        """Copy the payload; reset the rest; apply any overrides.

        The decision this pattern is actually about is which lines appear
        below `reset`. A `clone()` whose body is `return deepcopy(self)` has
        not made that decision -- it has deferred it to whoever first notices
        two rows with the same id.

        `_render_cache` is not copied at all: an empty cache is the only
        correct value for a new object. `conn` is dropped rather than shared,
        so the clone must be given one explicitly -- failing loudly beats
        sharing a handle silently.
        """
        new = type(self)(
            title=self.title,
            sections=copy.deepcopy(self.sections),   # deep: the payload is the point
            id=next(_ids),                           # reset: IDENTITY
            conn=None,                               # reset: CONNECTION
        )                                            # _render_cache: empty by default
        for k, v in overrides.items():
            setattr(new, k, v)
        return new

    def render(self) -> str:
        """Cached on purpose, so a test can prove the cache is not inherited."""
        key = f"{self.title}:{len(self.sections)}"
        if key not in self._render_cache:
            self._render_cache[key] = f"{self.title} [{', '.join(self.sections)}]"
        return self._render_cache[key]


@dataclass
class ConcurrentDocument(Document):
    """`Document` plus a lock, which changes whether it can be copied at all.

    Nothing here is about documents. The point is that `copy.deepcopy` works on
    the parent and raises on the child, and the only difference is one field
    whose purpose is thread-safety rather than copy semantics. **The protection
    is incidental**: you get it by accident if your class happens to hold a
    lock, and you lose it by accident the day someone moves locking up a layer.

    A lock is also the one member where both obvious answers are wrong. Sharing
    it makes two logically independent objects serialise against each other;
    copying it would leave neither protected. The only correct value for a new
    object is a new lock -- which is what `clone` gets, for free, from the
    default factory.
    """

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


# ─────────────────────────────────────────────────────────────────────────────
# The registry -- why the pattern exists
# ─────────────────────────────────────────────────────────────────────────────


class PrototypeRegistry:
    """Named templates, built once, cloned per use.

    This is the case Prototype genuinely wins: construction is expensive and
    the state you want only exists at runtime. You cannot write a parsed
    template or a warmed model as a literal, so you prepare one instance and
    copy it.

    Container images, VM templates and database snapshots are the same idea at
    a larger scale, with exactly the same caveat: the image must not bake in
    the identity of the machine that produced it. A golden image carrying the
    original host's SSH host key or machine-id is this file's `id` bug, at
    fleet scale.
    """

    def __init__(self) -> None:
        self._templates: dict[str, Document] = {}

    def register(self, name: str, prototype: Document) -> None:
        self._templates[name] = prototype

    def spawn(self, name: str, **overrides: object) -> Document:
        return self._templates[name].clone(**overrides)


def demo() -> None:
    """Assert the findings with no test runner. `python prototype.py`."""
    doc = Document.expensive("Report", ["intro", "body"])

    # Shallow copy shares the nested list.
    shallow = copy.copy(doc)
    shallow.sections.append("appendix")
    assert doc.sections == ["intro", "body", "appendix"], "the original changed"

    # The dangerous clone is the one that succeeds.
    doc2 = Document.expensive("Report", ["intro"])
    twin = copy.deepcopy(doc2)
    assert twin.id == doc2.id, "two objects, one primary key, no error"
    assert twin.conn is not None and twin.conn.dsn == doc2.conn.dsn

    # One unpicklable field guards the whole object -- and only that object.
    try:
        copy.deepcopy(ConcurrentDocument("Locked", ["a"]))
        raise AssertionError("expected the lock-bearing document to refuse copying")
    except TypeError as e:
        assert "pickle" in str(e)
    assert copy.deepcopy(Document("Unlocked", ["a"])), "its parent copies silently"

    # An explicit clone resets what must not be inherited.
    c = doc2.clone(title="Report (draft)")
    assert c.id != doc2.id and c.conn is None
    cd = ConcurrentDocument("Locked", ["a"])
    assert cd.clone()._lock is not cd._lock, "a fresh lock, neither shared nor copied"
    doc2.render()
    assert c._render_cache == {}, "the clone did not inherit a stale rendering"
    c.sections.append("new")
    assert "new" not in doc2.sections, "and the payload is not shared"

    # Cloning skips the expensive construction.
    reg = PrototypeRegistry()
    reg.register("report", Document.expensive("Template", ["a", "b"]))
    before = len(BUILDS)
    spawned = [reg.spawn("report", title=f"doc-{i}") for i in range(5)]
    assert len(BUILDS) == before, "five documents, zero expensive constructions"
    assert len({d.id for d in spawned}) == 5, "and five distinct identities"

    print("shallow shares the payload · deepcopy duplicates identity silently · "
          "one lock field guards the whole object · clone resets id/conn/cache · "
          "5 spawns, 0 builds")


if __name__ == "__main__":
    demo()
