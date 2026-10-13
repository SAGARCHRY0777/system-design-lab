"""Tests that assert the defining properties, not that the code runs.

Each of these three patterns is sold on a claim, and each claim is arithmetic
or a failure mode rather than a matter of taste. So the tests check the claim.

**Bridge is sold on N+M against NxM**, and the interesting result is where
that stops being true: `test_a_bridge_never_pays_with_a_single_abstraction`
and `test_two_by_two_is_a_tie` are the pair. Below the crossover the pattern
costs a class and an indirection and saves nothing, which is the arithmetic
behind "most codebases have one backend and always will".

**Composite is sold on uniformity** and its hazards are a stack overflow and
a cycle, both reachable from user-supplied input. Both are tested against the
guard *and* without it, because a guard nobody has seen fire is a guess.

Then the one with real teeth:
`test_a_hundred_shards_at_p99_are_slow_most_of_the_time`. A scatter-gather
returns when its slowest member does, so each member's 99th percentile is
roughly the composite's median. 63.4%, from 0.99^100, which is why fan-out
width is an availability decision.

**Flyweight is sold on memory**, and its one hard requirement is immutability
-- `test_a_mutable_flyweight_would_be_a_disaster` shows what sharing costs
without it. `test_dictionary_encoding_is_flyweight_at_the_storage_layer`
measures the version you will actually meet.
"""

from __future__ import annotations

import sys

import pytest

from structural import (
    MAX_DEPTH,
    AsciiRenderer,
    CompositeError,
    Glyph,
    Node,
    Square,
    SvgRenderer,
    Triangle,
    bridge_class_count,
    crossover,
    dictionary_encode,
    encoded_bytes,
    explicit_class_count,
    prob_any_slow,
    scatter_gather_latency,
    style,
    total_size,
)


# ── BRIDGE: the arithmetic, and where it stops working ─────────────────────


def test_a_bridge_never_pays_with_a_single_abstraction():
    """1 x M is M; 1 + M is M + 1. Worse at every size, forever.

    The most useful result about this pattern. A bridge with one abstraction
    or one implementation is not "a bit speculative" -- it is strictly more
    classes than not having it, at every M, with an indirection on top.
    """
    assert crossover(1) is None

    for m in (1, 2, 10, 100):
        assert bridge_class_count(1, m) > explicit_class_count(1, m)


def test_two_by_two_is_a_tie():
    """2x2 is 4 classes either way, so the bridge is pure indirection there."""
    assert explicit_class_count(2, 2) == bridge_class_count(2, 2) == 4
    assert crossover(2) == 3, "it starts paying at the third implementation"


def test_the_saving_is_real_once_both_axes_genuinely_vary():
    """And then it is large: 20 classes against 9, growing quadratically."""
    assert explicit_class_count(4, 5) == 20
    assert bridge_class_count(4, 5) == 9
    assert explicit_class_count(10, 10) - bridge_class_count(10, 10) == 80


def test_the_two_hierarchies_compose_without_knowing_each_other():
    """Four combinations from four classes, none of which names another."""
    combos = {(s.__name__, type(r).__name__): s(r).draw()
              for s in (Triangle, Square) for r in (SvgRenderer(), AsciiRenderer())}

    assert len(combos) == 4
    assert combos[("Triangle", "AsciiRenderer")] == "a---b"
    assert combos[("Square", "SvgRenderer")].startswith("<line")


# ── COMPOSITE: uniformity, and the two things that kill it ─────────────────


def test_a_caller_need_not_know_whether_it_holds_one_or_a_thousand():
    """The pattern working. One call, whatever the shape underneath."""
    leaf = Node("a", size=10)
    tree = Node("root").add(Node("a", size=10)).add(
        Node("sub").add(Node("b", size=3)).add(Node("c", size=2)))

    assert total_size(leaf) == 10
    assert total_size(tree) == 15, "same call, same answer shape"


def test_the_interface_is_the_union_of_leaf_and_container_needs():
    """The cost of that uniformity, which the pattern cannot avoid.

    `add` is meaningless on a file. Three options exist -- raise, no-op, or
    drop the method and lose the uniformity -- and this implementation raises,
    because a silent no-op loses data and the caller never learns.
    """
    leaf = Node("report.pdf", size=100)

    with pytest.raises(CompositeError, match="is a leaf"):
        leaf.add(Node("impossible"))

    assert leaf.is_leaf
    assert hasattr(leaf, "children"), "and it carries the field anyway"


def test_unbounded_nesting_is_a_denial_of_service():
    """Deeply nested input is a CVE class, and the guard is why it is not one here.

    A document, a JSON body, a synced folder structure: all nest as deeply as
    whoever produced them chose. The three-line recursive version of
    `total_size` raises `RecursionError` from an arbitrary frame -- and in a
    language without a recursion limit, segfaults.
    """
    root = Node("d0")
    cur = root
    for i in range(MAX_DEPTH + 2):
        child = Node(f"d{i + 1}", size=1)
        cur.children.append(child)
        cur = child

    with pytest.raises(CompositeError, match="nesting exceeds"):
        total_size(root)


def test_the_guard_fires_before_pythons_own_limit():
    """So the error names the node rather than exploding somewhere deep.

    `MAX_DEPTH` is set below `sys.getrecursionlimit()` on purpose. A
    `RecursionError` tells you nothing about which input caused it; a
    `CompositeError` naming the node tells you everything.
    """
    assert MAX_DEPTH < sys.getrecursionlimit()

    ok = Node("d0", size=1)
    cur = ok
    for i in range(MAX_DEPTH - 2):
        child = Node(f"d{i + 1}", size=1)
        cur.children.append(child)
        cur = child

    assert total_size(ok) == MAX_DEPTH - 1, "legitimate depth still works"


def test_a_cycle_is_detected_rather_than_hung():
    """A tree is a promise, not a type. One symlink and the recursion never ends.

    `seen` holds object identities, not names: two distinct nodes may share a
    name, and the same node may be legitimately reachable twice in a DAG, so
    name-based detection would both miss cycles and invent them.
    """
    a, b = Node("a", size=1), Node("b", size=1)
    a.children.append(b)
    b.children.append(a)

    with pytest.raises(CompositeError, match="cycle detected"):
        total_size(a)


def test_a_node_may_share_a_name_with_its_own_ancestor():
    """`src/lib/src/index.js` is a path, not a cycle. Name-keying says otherwise.

    This test took two attempts, and the first one was useless. Siblings
    sharing a name -- two folders each holding an `index.html` -- never
    collide, because the path is scoped per branch and the two never appear
    on one path together. Name-keying only breaks when a node repeats one of
    its own **ancestors**, which is what nested packages, vendored trees and
    `node_modules` look like.

    Both versions were run against a deliberate break swapping `id(node)` for
    `node.name`. The sibling version passed it; this one fails it.
    """
    tree = Node("src").add(Node("lib").add(Node("src").add(Node("index.js", size=30))))

    assert total_size(tree) == 30, "a repeated name on one path is not a cycle"


def test_a_diamond_is_not_a_cycle():
    """One node reachable by two routes is a DAG, and must not be rejected.

    This is the bug the same break hunt turned up. A single accumulating
    `seen` set rejects a diamond and calls it a cycle, because it cannot tell
    "visited before" from "is an ancestor of the node I am at". Cycle
    detection is about the **ancestor path**, so the set has to be dropped on
    the way back up.

    Note the shared node is counted twice, which is correct for a size sum
    over a DAG and is a separate question from cycle detection.
    """
    shared = Node("shared", size=7)
    tree = Node("root").add(Node("left").add(shared)).add(Node("right").add(shared))

    assert total_size(tree) == 14, "reached twice, counted twice, not rejected"


def test_a_hundred_shards_at_p99_are_slow_most_of_the_time():
    """The number worth remembering from this whole file.

    A scatter-gather returns when its **slowest** member does, so it is slow
    whenever *any* member is. At 100 members each with a 1% chance of being
    slow, that is 1 - 0.99^100 = 63.4%: **each member's 99th percentile is
    roughly the composite's median**.

    A per-shard p99 everyone is happy with becomes the typical experience of
    the aggregate, which is why fan-out width is an availability decision and
    not only a throughput one, and why hedged requests exist at all.
    """
    assert round(prob_any_slow(1), 3) == 0.010
    assert round(prob_any_slow(10), 3) == 0.096
    assert round(prob_any_slow(100), 3) == 0.634
    assert prob_any_slow(1000) > 0.9999

    assert prob_any_slow(100) > 50 * prob_any_slow(1), "it is not linear in N"


def test_a_composite_call_costs_its_slowest_member_not_its_average():
    """Which is why reporting the mean of a fan-out is reporting nothing."""
    latencies = [5.0, 6.0, 7.0, 900.0]

    assert scatter_gather_latency(latencies) == 900.0
    assert sum(latencies) / len(latencies) < 240, "the mean says 230ms"


# ── FLYWEIGHT: memory, and the requirement that makes it safe ──────────────


def test_the_factory_returns_the_identical_object_not_an_equal_one():
    """Identity is the saving. Equality would mean two objects still existed."""
    a, b = style("Inter", 12), style("Inter", 12)

    assert a is b
    assert style("Inter", 12, bold=True) is not a, "different intrinsic state"


def test_eleven_thousand_glyphs_share_one_style_object():
    """Intrinsic state stored once; extrinsic state per use.

    Splitting the two is the design work. Put `position` in the flyweight and
    you have a million flyweights and no saving; leave `font` out of it and
    two glyphs share a position.
    """
    glyphs = [Glyph(c, i, style("Inter", 12)) for i, c in enumerate("hello world" * 1000)]

    assert len(glyphs) == 11_000
    assert len({id(g.style) for g in glyphs}) == 1
    assert len({g.position for g in glyphs}) == 11_000, "extrinsic state still varies"


def test_a_mutable_flyweight_would_be_a_disaster():
    """Immutability is the pattern's one hard requirement, not tidiness.

    A flyweight is shared by construction, so a mutable one lets any holder
    change every other holder's data -- and the bug surfaces arbitrarily far
    from the mutation, in code that never touched the object.
    """
    shared = style("Inter", 12)
    glyphs = [Glyph("x", i, shared) for i in range(100)]

    with pytest.raises(Exception):               # FrozenInstanceError
        shared.size = 99                         # type: ignore[misc]

    assert all(g.style.size == 12 for g in glyphs)


def test_python_already_does_this_for_strings_you_intern():
    """`sys.intern` is a flyweight factory in the standard library.

    Note what is *not* asserted: integer identity. `1000 is 1000` is True
    inside one code object because the compiler folds equal constants, which
    looks like interning and is not. Built strings are the honest
    demonstration, because they are genuinely distinct objects.
    """
    s1, s2 = "".join(["ab", "cd"]), "".join(["ab", "cd"])

    assert s1 == s2 and s1 is not s2, "equal, two objects"
    assert sys.intern(s1) is sys.intern(s2), "and now one"


def test_dictionary_encoding_is_flyweight_at_the_storage_layer():
    """Parquet, ORC and ClickHouse all do this, and it is the same pattern.

    A low-cardinality column is stored as a dictionary of distinct values plus
    an array of small integers: intrinsic state once, extrinsic state (the
    row) holding a reference. It is the single largest reason columnar formats
    beat row formats on categorical data.
    """
    rows = ["GET", "POST", "GET", "GET", "DELETE"] * 2000
    dictionary, codes = dictionary_encode(rows)

    assert dictionary == ["GET", "POST", "DELETE"], "insertion order, distinct only"
    assert len(codes) == len(rows), "one code per row"
    assert [dictionary[c] for c in codes] == rows, "lossless"

    raw = sum(len(r) for r in rows)
    encoded = encoded_bytes(dictionary, codes)
    assert encoded * 3 < raw, f"{encoded} bytes against {raw}"


def test_the_encoding_only_claims_what_low_cardinality_supports():
    """One byte per code is honest to 256 values, and the assert says so.

    Above that the real engines switch strategy, and a size calculation that
    kept quoting one byte would be reporting a saving that does not exist.
    """
    with pytest.raises(AssertionError, match="low cardinality"):
        encoded_bytes([str(i) for i in range(300)], list(range(300)))
