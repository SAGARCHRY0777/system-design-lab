"""Tests that assert the *defining properties*, not just that the code runs.

The headline pair is `test_ring_moves_about_one_over_n_when_a_node_joins` and
`test_modulo_moves_almost_everything_when_a_node_joins`, sitting next to each
other on purpose. Same keys, same rebalance, 20% against 80%. Everything else
in this file supports that contrast.

No sleeps and no randomness: `stable_hash` is deterministic, so every figure
below is reproducible byte for byte on any machine and any Python build. The
statistical assertions are therefore assertions about a fixed computation, not
about a probability.
"""

from __future__ import annotations

import pytest

from consistent_hashing import (
    HashRing,
    ModuloSharder,
    remap_fraction,
    spread,
    stable_hash,
)

KEYS = [f"user:{i}" for i in range(20_000)]


class Snapshot:
    """A frozen key -> node map, so a sharder can be compared with its own past.

    `remap_fraction` needs a *before* and an *after*, but mutating a ring
    destroys the before. Recording the answers first is the only honest way to
    measure what a rebalance actually did.
    """

    def __init__(self, sharder, keys) -> None:
        self._map = {k: sharder.get(k) for k in keys}

    def get(self, key: str) -> str:
        return self._map[key]


# --------------------------------------------------------------------------- #
# The whole reason consistent hashing exists                                   #
# --------------------------------------------------------------------------- #

def test_ring_moves_about_one_over_n_when_a_node_joins():
    """Four nodes become five; only the keys in the new node's arc move.

    1/5 = 20% is the theoretical share, and the ring lands on 20.2%. The other
    80% of the keyspace is not touched -- those cache entries stay warm and
    those rows stay put."""
    ring = HashRing([f"node-{i}" for i in range(4)])
    before = Snapshot(ring, KEYS)

    ring.add("node-4")

    moved = remap_fraction(before, ring, KEYS)
    assert moved == pytest.approx(0.2022, abs=0.0001)  # exact: the hash is fixed
    assert moved < 0.25


def test_modulo_moves_almost_everything_when_a_node_joins():
    """Same four-to-five rebalance under `hash(key) % N`: 80% of keys move.

    This is the test that justifies the whole file. Four times the disruption
    for the identical membership change -- and at 16 nodes it is 94%, because
    the modulo penalty gets *worse* as the cluster gets bigger, which is
    precisely backwards from what you want."""
    mod = ModuloSharder([f"node-{i}" for i in range(4)])
    before = Snapshot(mod, KEYS)

    mod.add("node-4")

    moved = remap_fraction(before, mod, KEYS)
    assert moved == pytest.approx(0.7965, abs=0.0001)
    assert moved > 0.75


def test_the_gap_between_them_widens_as_the_cluster_grows():
    """Ring disruption falls as 1/(N+1). Modulo disruption rises as N/(N+1).

    The two lines diverge, so the argument for a ring is strongest exactly
    where the stakes are highest: the big cluster."""
    for n in (4, 8, 16):
        names = [f"node-{i}" for i in range(n)]

        ring = HashRing(names)
        ring_before = Snapshot(ring, KEYS)
        ring.add(f"node-{n}")
        ring_moved = remap_fraction(ring_before, ring, KEYS)

        mod = ModuloSharder(names)
        mod_before = Snapshot(mod, KEYS)
        mod.add(f"node-{n}")
        mod_moved = remap_fraction(mod_before, mod, KEYS)

        # Ring tracks the ideal 1/(N+1); modulo tracks the worst case N/(N+1).
        assert ring_moved == pytest.approx(1 / (n + 1), abs=0.02)
        assert mod_moved > 1 - (1 / (n + 1)) - 0.02
        assert mod_moved / ring_moved > 3.5


def test_removing_a_node_moves_only_that_nodes_keys():
    """The other half of the property, and the one people forget to check.

    Bounding the *fraction* that moves is not enough -- a shard map could move
    20% of keys and still shuffle keys between two nodes that were both
    perfectly healthy. It must move the departing node's keys and touch
    nothing else, or a node leaving would invalidate unrelated caches."""
    ring = HashRing([f"n{i}" for i in range(5)])
    before = Snapshot(ring, KEYS)

    ring.remove("n2")

    for key in KEYS:
        if before.get(key) == "n2":
            assert ring.get(key) != "n2"      # rehomed, necessarily
        else:
            assert ring.get(key) == before.get(key)   # untouched, crucially

    assert remap_fraction(before, ring, KEYS) == pytest.approx(1 / 5, abs=0.02)


def test_removing_then_re_adding_restores_the_exact_same_mapping():
    """A node flapping must not leave the ring permanently rearranged."""
    ring = HashRing([f"n{i}" for i in range(6)])
    before = Snapshot(ring, KEYS)

    ring.remove("n3")
    ring.add("n3")

    assert remap_fraction(before, ring, KEYS) == 0.0


# --------------------------------------------------------------------------- #
# Virtual nodes -- why a plain ring is not good enough                         #
# --------------------------------------------------------------------------- #

def test_one_vnode_per_node_distributes_appallingly():
    """A ring is only as even as its cuts, and eight random cuts are not even.

    With one point per node, `node-2` owns **55% of the keyspace** and 4.4x its
    fair share while `node-6` owns a fifth of its share. In a cache tier that
    is one machine holding all the hot data and paging someone at 3am. This is
    the failure that virtual nodes exist to fix, and it is why "put the servers
    on a circle" is not by itself a working design."""
    ring = HashRing([f"node-{i}" for i in range(8)], vnodes=1)
    counts = ring.distribution(KEYS)
    fair_share = len(KEYS) / 8

    assert max(counts.values()) / fair_share > 4.0
    assert min(counts.values()) / fair_share < 0.25
    assert spread(counts.values()) > 1.0


def test_spread_improves_monotonically_with_more_vnodes():
    """Relative spread falls as roughly 1/sqrt(vnodes). Measured, not asserted
    from theory: 1.30 -> 0.31 -> 0.07 -> 0.04."""
    measured = {}
    for vnodes in (1, 10, 100, 500):
        ring = HashRing([f"node-{i}" for i in range(8)], vnodes=vnodes)
        measured[vnodes] = spread(ring.distribution(KEYS).values())

    series = [measured[v] for v in (1, 10, 100, 500)]
    assert series == sorted(series, reverse=True), measured

    assert measured[1] > 0.5      # unusable
    assert measured[100] < 0.10   # fine
    assert measured[500] < 0.05   # excellent, and 500x the ring to hold


def test_the_default_vnode_count_keeps_every_node_within_a_quarter_of_fair():
    """150 vnodes is the common default. This is what it actually buys."""
    ring = HashRing([f"node-{i}" for i in range(8)])
    counts = ring.distribution(KEYS)
    fair_share = len(KEYS) / 8

    for node, count in counts.items():
        assert 0.75 < count / fair_share < 1.25, (node, count)


def test_more_vnodes_costs_ring_size_which_is_the_trade():
    """Nothing is free: the smoothing is bought with memory and rebuild time."""
    assert HashRing(["a", "b"], vnodes=10).points == 20
    assert HashRing(["a", "b"], vnodes=1000).points == 2000


@pytest.mark.parametrize("vnodes", [0, -1])
def test_invalid_vnode_count_is_rejected(vnodes):
    with pytest.raises(ValueError):
        HashRing(["a"], vnodes=vnodes)


# --------------------------------------------------------------------------- #
# Determinism -- a ring that is not identical everywhere is not a shard map    #
# --------------------------------------------------------------------------- #

def test_insertion_order_does_not_affect_the_mapping():
    """Two servers learning the same membership by different paths must agree.

    If they do not, two nodes believe they own the same key and you have two
    writers for one row. This is why `_rebuild` sorts rather than patching."""
    forward = HashRing([])
    for n in ["alpha", "bravo", "charlie", "delta"]:
        forward.add(n)

    backward = HashRing([])
    for n in ["delta", "charlie", "bravo", "alpha"]:
        backward.add(n)

    at_once = HashRing(["charlie", "alpha", "delta", "bravo"])

    for key in KEYS[:2000]:
        owner = forward.get(key)
        assert backward.get(key) == owner
        assert at_once.get(key) == owner


def test_adding_a_node_that_is_already_present_is_a_no_op():
    ring = HashRing(["a", "b", "c"])
    before = Snapshot(ring, KEYS)
    ring.add("b")
    assert len(ring) == 3
    assert remap_fraction(before, ring, KEYS) == 0.0


def test_stable_hash_is_pinned_not_merely_repeatable():
    """`hash()` is repeatable within a process too -- that is the trap.

    Pinning a literal digest is the only assertion that fails if someone swaps
    the hash for the built-in, because the built-in is salted per interpreter
    and would silently remap every key in the cluster on the next restart.
    Verified identical on CPython 3.11 and 3.14 -- blake2b is a fixed
    algorithm, which is exactly the property being relied on."""
    assert stable_hash("user:1") == 15310966450534750738
    assert stable_hash("") == 16476032584258269876


def test_the_hash_function_is_pluggable_but_must_still_be_stable():
    """A custom hash is fine; the ring only requires that it is a function."""
    ring = HashRing(["a", "b", "c"], vnodes=4, hash_fn=lambda s: len(s) * 7919)
    assert ring.get("xy") == ring.get("zw")  # same length, therefore same point


# --------------------------------------------------------------------------- #
# Lookup mechanics                                                             #
# --------------------------------------------------------------------------- #

def test_lookup_wraps_around_the_top_of_the_ring():
    """A key hashing past the last vnode belongs to the first. The circle has
    no end -- the sorted list is a representation, not the model."""
    ring = HashRing(["a", "b"], vnodes=2, hash_fn=lambda s: {"a#0": 10, "a#1": 20,
                                                             "b#0": 30, "b#1": 40}.get(s, 99))
    assert ring.get("past-the-end") == "a"  # hashes to 99, wraps to point 10


def test_empty_ring_raises_rather_than_returning_none():
    ring = HashRing([])
    with pytest.raises(KeyError):
        ring.get("anything")


def test_replicas_are_distinct_physical_nodes():
    """The bug this guards against looks exactly like working replication.

    Three consecutive ring positions can easily be three vnodes of one machine.
    That is one machine, one failure domain, and zero replication -- while the
    code returns a list of length three and every test that only checks the
    length passes."""
    ring = HashRing([f"n{i}" for i in range(6)])
    for key in KEYS[:3000]:
        replicas = ring.get_replicas(key, 3)
        assert len(replicas) == 3
        assert len(set(replicas)) == 3
        assert replicas[0] == ring.get(key)  # the primary is the plain lookup


def test_replica_lists_are_stable_across_unrelated_membership_changes():
    """Adding a sixth node must not reshuffle replicas for most keys."""
    ring = HashRing([f"n{i}" for i in range(5)])
    before = {k: ring.get_replicas(k, 2) for k in KEYS[:5000]}
    ring.add("n5")
    unchanged = sum(1 for k in before if ring.get_replicas(k, 2) == before[k])
    assert unchanged / len(before) > 0.65


def test_asking_for_more_replicas_than_nodes_is_an_error():
    """Silently returning fewer would let a caller believe it had three copies."""
    ring = HashRing(["a", "b"])
    with pytest.raises(ValueError):
        ring.get_replicas("k", 3)


def test_distribution_reports_nodes_that_own_nothing():
    """A node owning zero keys is the interesting case; dropping it from the
    report is how an unbalanced ring looks balanced."""
    ring = HashRing([f"n{i}" for i in range(8)], vnodes=1)
    counts = ring.distribution(KEYS[:5])
    assert len(counts) == 8
    assert 0 in counts.values()


def test_spread_of_a_perfectly_even_split_is_zero():
    assert spread([100, 100, 100]) == 0.0
    assert spread([]) == 0.0
