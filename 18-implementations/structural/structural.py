"""Bridge, Composite, Flyweight: three answers to "there are too many of these".

The other four structural patterns are wrappers and share a page because
telling them apart *is* the content. These three are not wrappers and are not
confused with each other. What they share is a problem shape: each one exists
because some multiplicity got out of hand.

    Bridge      too many CLASSES    -- N abstractions x M implementations
    Composite   too many NODES      -- a tree the caller should not have to walk
    Flyweight   too many INSTANCES  -- a million objects holding ten distinct values

Each one's interesting part is the thing that goes wrong, and all three are
measurable rather than arguable.

**Bridge has a crossover, and below it the pattern is pure cost.** N x M
against N + M is the whole pitch, and at 2x2 those are both 4 -- identical
class count, plus indirection. With a single implementation it is strictly
worse, always, which is the arithmetic behind "most codebases have one backend
and always will". `crossover` computes where it starts paying.

**Composite's hazards are a stack overflow and a cycle**, both reachable from
user-supplied input, and both are why `total_size` takes a depth budget and a
visited set rather than being three lines of elegant recursion. Deeply nested
JSON is this bug with a CVE number.

**And distributed, a composite costs the slowest member every time.** That is
the one with real teeth: a scatter-gather over 100 shards where each has a 1%
chance of being slow is slow **63%** of the time, because 0.99^100 is 0.366.
The composite's median is roughly its members' 99th percentile. Arithmetic,
not a simulation -- see `prob_any_slow`.

**Flyweight's hazard is mutability**, and the modern incarnation is not an
object pool at all: dictionary encoding in a columnar store is flyweight at
the storage layer, and `dictionary_encode` measures what it saves.

Stdlib only.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

# ─────────────────────────────────────────────────────────────────────────────
# 1. BRIDGE -- too many classes
# ─────────────────────────────────────────────────────────────────────────────


def explicit_class_count(abstractions: int, implementations: int) -> int:
    """Without a bridge: one class per combination. SvgCircle, CanvasCircle, ..."""
    return abstractions * implementations


def bridge_class_count(abstractions: int, implementations: int) -> int:
    """With a bridge: the two hierarchies are independent, so they add."""
    return abstractions + implementations


def crossover(abstractions: int) -> int | None:
    """Fewest implementations at which a bridge is strictly fewer classes.

    Returns None when no number of implementations helps, which happens for
    exactly one input and is the useful result: with a **single abstraction**,
    1 x M is M and 1 + M is M + 1, so the bridge is worse at every size. The
    same holds mirrored for a single implementation.

    That is the arithmetic behind the catalogue's advice -- reach for it only
    when both axes are actually varying. Most codebases have one backend and
    always will, and a bridge there costs a class and an indirection to save
    nothing.
    """
    for m in range(1, 1000):
        if bridge_class_count(abstractions, m) < explicit_class_count(abstractions, m):
            return m
    return None


class Renderer:
    """The implementation hierarchy. Varies independently of the shapes."""

    def line(self, a: str, b: str) -> str:
        raise NotImplementedError


class SvgRenderer(Renderer):
    def line(self, a: str, b: str) -> str:
        return f"<line from={a} to={b}/>"


class AsciiRenderer(Renderer):
    def line(self, a: str, b: str) -> str:
        return f"{a}---{b}"


class Shape:
    """The abstraction hierarchy. Holds a renderer; does not inherit from one.

    That containment is the entire pattern, and it is also exactly Strategy's
    shape -- an object holding an interface it delegates to. The two are
    structurally identical and differ in intent: Strategy swaps one algorithm
    at runtime, Bridge lets two hierarchies evolve separately. No test can
    tell them apart, which is worth knowing before arguing about it in review.
    """

    def __init__(self, renderer: Renderer) -> None:
        self._renderer = renderer

    def draw(self) -> str:
        raise NotImplementedError


class Triangle(Shape):
    def draw(self) -> str:
        return self._renderer.line("a", "b")


class Square(Shape):
    def draw(self) -> str:
        return self._renderer.line("p", "q")


# ─────────────────────────────────────────────────────────────────────────────
# 2. COMPOSITE -- too many nodes
# ─────────────────────────────────────────────────────────────────────────────


class CompositeError(Exception):
    """Raised for depth and cycle violations.

    A distinct type because both conditions are reachable from user-supplied
    input -- an uploaded document, a JSON body, a folder structure someone
    synced -- which makes them input validation rather than internal errors.
    """


@dataclass
class Node:
    """Leaf and container in one type, which is the pattern and also its cost.

    The Gang of Four describe a shared interface so callers need not know
    whether they hold one thing or a thousand. The price is that **the
    interface becomes the union of both needs**: `children` is meaningless on
    a file, and `size` is derived rather than stored on a folder. Every
    composite pays this somewhere, and the three ways out -- raise on a leaf,
    no-op on a leaf, or drop the method and lose the uniformity -- are all
    compromises.
    """

    name: str
    size: int = 0
    children: list[Node] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return not self.children

    def add(self, child: Node) -> Node:
        if self.size:
            raise CompositeError(f"{self.name} is a leaf; it cannot have children")
        self.children.append(child)
        return self


MAX_DEPTH = 64
"""Below Python's recursion limit on purpose, so the guard fires first and
says something useful instead of raising RecursionError from somewhere deep."""


def total_size(node: Node, depth: int = 0, path: frozenset[int] = frozenset()) -> int:
    """Sum a tree, with the two guards that elegant recursion leaves out.

    The three-line version of this function is a denial of service. Both
    hazards arrive from input nobody validated:

    **Depth.** A document, a JSON body or a synced folder structure nests as
    deeply as whoever made it chose. Unguarded recursion hits Python's limit
    and raises `RecursionError` from an arbitrary frame; in a language without
    that limit it is a segfault. Deeply nested input is a CVE class, not a
    hypothetical.

    **Cycles.** A tree is a promise, not a type. One symlink, one reparented
    folder, one object graph deserialised from a payload that referenced
    itself, and the recursion never terminates.

    Two details in `path` that the obvious version gets wrong, and this one
    did until a deliberate break exposed them:

    It holds **object identities, not names**. A node may legitimately repeat
    one of its own ancestors' names -- `src/lib/src/index.js`, or anything
    vendored -- and a name-keyed check calls that a cycle. Note it has to be
    an *ancestor*: two siblings sharing a name never collide, because the path
    is scoped per branch, which is why the first version of
    `test_a_node_may_share_a_name_with_its_own_ancestor` proved nothing.

    It is the **ancestor path, not every node visited** -- which is what
    "cycle" means. A single accumulating set rejects a diamond, where one node
    is legitimately reachable by two routes, and calls it a cycle when it is
    not one. Passing a new frozenset down each level scopes the check to the
    current path and drops it on the way back up.
    """
    if depth > MAX_DEPTH:
        raise CompositeError(f"nesting exceeds {MAX_DEPTH} at {node.name!r}")
    if id(node) in path:
        raise CompositeError(f"cycle detected at {node.name!r}")
    path = path | {id(node)}

    return node.size + sum(total_size(c, depth + 1, path) for c in node.children)


def prob_any_slow(members: int, p_slow: float = 0.01) -> float:
    """P(at least one of `members` is slow), for independent members.

    The arithmetic behind *The Tail at Scale*, and the most useful number in
    this file. A scatter-gather returns when its **slowest** member does, so
    the composite is slow whenever *any* member is:

        1 member    1.0%
        10          9.6%
        100        63.4%     <- each member's p99 is the composite's median
        1000      100.0%

    A per-shard 99th percentile that everyone is pleased with becomes the
    typical experience of the aggregate. This is why fan-out width is an
    availability decision and not only a throughput one, and why hedged
    requests exist.
    """
    return 1 - (1 - p_slow) ** members


def scatter_gather_latency(member_latencies: list[float]) -> float:
    """A composite call costs its slowest member. Not the mean. Every time."""
    return max(member_latencies)


# ─────────────────────────────────────────────────────────────────────────────
# 3. FLYWEIGHT -- too many instances
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CharStyle:
    """The intrinsic state -- shared by every user, and therefore immutable.

    `frozen=True` is not tidiness here, it is the pattern's one hard
    requirement. A flyweight is shared by construction, so a mutable one lets
    any holder change every other holder's data, and the bug surfaces
    arbitrarily far from the mutation. Immutability is what makes sharing
    safe, and `test_a_mutable_flyweight_would_be_a_disaster` shows what the
    alternative costs.
    """

    font: str
    size: int
    bold: bool = False


_STYLES: dict[tuple, CharStyle] = {}


def style(font: str, size: int, bold: bool = False) -> CharStyle:
    """The factory. Identical arguments return the identical object.

    Returning *the same object* rather than an equal one is the whole saving:
    a million characters in three styles hold three objects between them, and
    an identity check replaces a field comparison.
    """
    key = (font, size, bold)
    if key not in _STYLES:
        _STYLES[key] = CharStyle(font, size, bold)
    return _STYLES[key]


@dataclass
class Glyph:
    """Extrinsic state -- the part that differs per use and cannot be shared.

    Splitting intrinsic from extrinsic is the design work. Get it wrong by
    putting position in the flyweight and you have a million flyweights and no
    saving; get it wrong the other way and two characters share a position.
    """

    char: str
    position: int
    style: CharStyle


def dictionary_encode(values: list[str]) -> tuple[list[str], list[int]]:
    """Flyweight at the storage layer, which is where you will actually meet it.

    Parquet, ORC and ClickHouse all store a low-cardinality column as a
    dictionary of distinct values plus an array of small integers. That is
    exactly this pattern -- intrinsic state stored once, extrinsic state (the
    row) holding a reference -- and it is the single largest reason columnar
    formats are smaller than row formats for categorical data.

    `test_dictionary_encoding_is_flyweight_at_the_storage_layer` measures it.
    """
    table: dict[str, int] = {}
    codes = []
    for v in values:
        if v not in table:
            table[v] = len(table)
        codes.append(table[v])
    return list(table), codes


def encoded_bytes(dictionary: list[str], codes: list[int]) -> int:
    """Size of the encoded form: the distinct values once, plus one byte a row.

    One byte per code is honest for up to 256 distinct values, which is what
    "low cardinality" means and is the only case where this encoding is
    chosen. Above that the engines switch strategy, and so should the
    arithmetic.
    """
    assert len(dictionary) <= 256, "one byte per code only holds for low cardinality"
    return sum(len(v) for v in dictionary) + len(codes)


def demo() -> None:
    """Assert the findings with no test runner. `python structural.py`."""
    # Bridge: below the crossover it is pure cost.
    assert crossover(1) is None, "one abstraction: a bridge never pays"
    assert explicit_class_count(2, 2) == bridge_class_count(2, 2) == 4, "2x2 is a tie"
    assert crossover(2) == 3, "two abstractions: it pays from three implementations"
    assert explicit_class_count(4, 5) == 20 and bridge_class_count(4, 5) == 9
    assert Triangle(SvgRenderer()).draw().startswith("<line")
    assert Triangle(AsciiRenderer()).draw() == "a---b"

    # Composite: the guards, and the tail.
    root = Node("root").add(Node("a", size=10)).add(Node("b", size=5))
    assert total_size(root) == 15

    deep = Node("d0")
    cur = deep
    for i in range(MAX_DEPTH + 2):
        nxt = Node(f"d{i + 1}")
        cur.children.append(nxt)
        cur = nxt
    try:
        total_size(deep)
        raise AssertionError("expected the depth guard to fire")
    except CompositeError as e:
        assert "nesting exceeds" in str(e)

    cyclic = Node("x")
    cyclic.children.append(cyclic)
    try:
        total_size(cyclic)
        raise AssertionError("expected the cycle guard to fire")
    except CompositeError as e:
        assert "cycle" in str(e)

    assert round(prob_any_slow(100), 3) == 0.634, "p99 members, median-slow composite"
    assert scatter_gather_latency([5, 7, 900, 6]) == 900

    # Flyweight: identity, not equality.
    a, b = style("Inter", 12), style("Inter", 12)
    assert a is b, "the same object, not an equal one"
    glyphs = [Glyph(c, i, style("Inter", 12)) for i, c in enumerate("hello world" * 1000)]
    assert len({id(g.style) for g in glyphs}) == 1, "11000 glyphs, one style object"

    # Python already does this, for strings you intern.
    s1, s2 = "".join(["ab", "cd"]), "".join(["ab", "cd"])
    assert s1 == s2 and s1 is not s2
    assert sys.intern(s1) is sys.intern(s2)

    # And at the storage layer.
    rows = ["GET", "POST", "GET", "GET", "DELETE"] * 2000
    dic, codes = dictionary_encode(rows)
    raw = sum(len(r) for r in rows)
    assert encoded_bytes(dic, codes) * 3 < raw, f"{encoded_bytes(dic, codes)} vs {raw}"

    print("bridge: never pays at N=1, ties at 2x2, 20 vs 9 at 4x5 · "
          "composite: depth and cycle guarded, 63.4% slow at N=100 · "
          "flyweight: 11000 glyphs share 1 style, dictionary encoding 3x smaller")


if __name__ == "__main__":
    demo()
