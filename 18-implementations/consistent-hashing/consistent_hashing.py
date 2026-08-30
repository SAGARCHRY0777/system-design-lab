"""Consistent hashing, written so the reason it exists is impossible to miss.

`hash(key) % N` is the obvious way to spread keys over N servers and it is
almost always the wrong one. The modulus is a function of N, so changing N
changes the answer for *every* key at once: nearly the whole keyspace remaps.
For a cache that is a total miss storm arriving at the database in the same
second; for a shard map it is a full data migration before anyone can read.

Consistent hashing exists to bound that blast radius. Nodes and keys are both
placed on one circular hash space, and a key belongs to the first node
clockwise of it. Adding a node inserts a single point on that circle, so only
the keys in the arc it now covers move -- roughly 1/N of them -- and every
other key stays exactly where it was.

`ModuloSharder` is here only as the control group. test_consistent_hashing.py
puts the same rebalance through both and asserts the gap: ~20% of keys move on
a ring going from four nodes to five, ~80% under the modulus. That gap is the
entire justification for the extra machinery, and it is the only reason to
prefer this over a line of arithmetic.

Stdlib only, single process. Everything a real shard map needs -- weighted
capacity, rack and zone awareness, and above all a way for every node to
*agree* on the ring -- is deliberately absent; see README.md.
"""

from __future__ import annotations

import bisect
import hashlib
import statistics
from collections import Counter
from typing import Callable, Iterable, Protocol


def stable_hash(label: str) -> int:
    """A hash that means the same thing in every process, forever.

    Python's built-in `hash()` is salted per interpreter for str and bytes
    (PYTHONHASHSEED), so a ring built on it maps a key to a different node in
    every process and after every restart. For a cache cluster that is a
    permanent near-zero hit rate that no amount of staring at the cache code
    will explain. Consistent hashing is only consistent if the hash is.

    blake2b rather than md5 -- Ketama's choice -- purely because it is always
    present; md5 is unavailable on FIPS builds. Cryptographic strength is not
    the point here. Uniformity and stability are.
    """
    digest = hashlib.blake2b(label.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big")


class Sharder(Protocol):
    """What `remap_fraction` needs, so a ring and a modulus are comparable."""

    def get(self, key: str) -> str: ...


class HashRing:
    """Keys map to the first node clockwise on a circular hash space.

    Each physical node is placed at `vnodes` positions rather than one. Without
    that, a ring of four nodes is four random cuts in a circle and the arcs
    between them are wildly unequal -- one node routinely owns two or three
    times its share, which in a cache means one machine holds the hot data and
    the rest hold nothing. Virtual nodes average that out: the relative spread
    of the load falls as roughly 1/sqrt(vnodes), which bench.py measures.

    150 is the common default because it buys most of the smoothing available
    (relative spread around 8%) before the ring gets expensive to hold and to
    rebuild.
    """

    def __init__(
        self,
        nodes: Iterable[str] = (),
        *,
        vnodes: int = 150,
        hash_fn: Callable[[str], int] = stable_hash,
    ) -> None:
        if vnodes < 1:
            raise ValueError("vnodes must be at least 1")
        self.vnodes = vnodes
        self._hash = hash_fn
        self._nodes: set[str] = set(nodes)
        self._ring: list[int] = []
        self._owner: dict[int, str] = {}
        self._rebuild()

    # ----------------------------------------------------------------- build

    def _rebuild(self) -> None:
        """Recompute the whole ring from the current membership set.

        Rebuilt from a *sorted* node set rather than patched incrementally, so
        the result depends only on which nodes are present and never on the
        order they were learned about. Two servers told about the same
        membership by different paths must compute an identical ring or they
        will disagree about where a key lives, and a disagreement about
        ownership is how you get two writers for one key.

        Sorting also makes the rare hash collision between two vnode labels
        resolve the same way everywhere: the later node in sorted order wins.

        Cost is O(N*V log N*V) per membership change. Membership changes
        minutes or hours apart, so this is free in every sense that matters --
        and bench.py prints the actual figure rather than asserting it is.
        """
        owner: dict[int, str] = {}
        for node in sorted(self._nodes):
            for i in range(self.vnodes):
                # The replica index goes through the hash, not around it. It is
                # what scatters one node's vnodes across the whole circle
                # instead of clustering them next to each other, which would
                # defeat the point entirely.
                owner[self._hash(f"{node}#{i}")] = node
        self._owner = owner
        self._ring = sorted(owner)

    def add(self, node: str) -> None:
        """Idempotent: adding a node already present must not perturb the ring."""
        if node in self._nodes:
            return
        self._nodes.add(node)
        self._rebuild()

    def remove(self, node: str) -> None:
        if node not in self._nodes:
            raise KeyError(node)
        self._nodes.remove(node)
        self._rebuild()

    # ---------------------------------------------------------------- lookup

    def get(self, key: str) -> str:
        """The node owning `key`: first vnode clockwise, wrapping at the top."""
        if not self._ring:
            raise KeyError("ring is empty")
        i = bisect.bisect(self._ring, self._hash(key))
        # `% len` is the wrap. A key hashing past the last vnode belongs to the
        # first one -- the circle has no end, only a place we chose to cut it
        # so that a sorted list and a binary search would work.
        return self._owner[self._ring[i % len(self._ring)]]

    def get_replicas(self, key: str, count: int) -> list[str]:
        """The first `count` **distinct physical** nodes clockwise from `key`.

        The distinctness is the whole point and it is the bug people ship:
        walking the ring and taking the next three positions can easily return
        three vnodes of the same machine, which is one machine, which is no
        replication at all while looking exactly like replication.
        """
        if count < 1:
            raise ValueError("count must be at least 1")
        if count > len(self._nodes):
            raise ValueError(f"asked for {count} replicas from {len(self._nodes)} nodes")
        start = bisect.bisect(self._ring, self._hash(key))
        out: list[str] = []
        seen: set[str] = set()
        for step in range(len(self._ring)):
            node = self._owner[self._ring[(start + step) % len(self._ring)]]
            if node not in seen:
                seen.add(node)
                out.append(node)
                if len(out) == count:
                    break
        return out

    # ----------------------------------------------------------- inspection

    @property
    def nodes(self) -> tuple[str, ...]:
        return tuple(sorted(self._nodes))

    @property
    def points(self) -> int:
        """Positions on the ring. Fewer than nodes*vnodes only on a collision."""
        return len(self._ring)

    def distribution(self, keys: Iterable[str]) -> Counter[str]:
        counts: Counter[str] = Counter()
        for node in self.nodes:
            counts[node] = 0  # nodes owning nothing must still appear
        for key in keys:
            counts[self.get(key)] += 1
        return counts

    def __len__(self) -> int:
        return len(self._nodes)

    def __contains__(self, node: object) -> bool:
        return node in self._nodes

    def __repr__(self) -> str:
        return f"HashRing(nodes={len(self._nodes)}, vnodes={self.vnodes}, points={len(self._ring)})"


class ModuloSharder:
    """`hash(key) % N`. The control group, included only to be beaten.

    It is not a strawman -- it is genuinely the right answer when the node
    count is fixed forever, because it is one modulo with no ring to hold, no
    rebuild, and perfectly even distribution by construction. Its distribution
    is *better* than a ring's.

    It has exactly one failure mode, and the failure mode is called "scaling
    up". Changing N moves ~(N-1)/N of the keyspace in a single step.
    """

    def __init__(self, nodes: Iterable[str]) -> None:
        # Sorted for the same reason the ring sorts: the mapping must not
        # depend on the order membership was learned.
        self._nodes = sorted(set(nodes))

    def get(self, key: str) -> str:
        if not self._nodes:
            raise KeyError("no nodes")
        return self._nodes[stable_hash(key) % len(self._nodes)]

    def add(self, node: str) -> None:
        if node not in self._nodes:
            self._nodes = sorted(self._nodes + [node])

    def remove(self, node: str) -> None:
        self._nodes.remove(node)

    @property
    def nodes(self) -> tuple[str, ...]:
        return tuple(self._nodes)

    def distribution(self, keys: Iterable[str]) -> Counter[str]:
        counts: Counter[str] = Counter({n: 0 for n in self._nodes})
        for key in keys:
            counts[self.get(key)] += 1
        return counts

    def __len__(self) -> int:
        return len(self._nodes)


# --------------------------------------------------------------------------- #
# The two measurements that decide whether any of this was worth it            #
# --------------------------------------------------------------------------- #

def remap_fraction(before: Sharder, after: Sharder, keys: Iterable[str]) -> float:
    """Fraction of `keys` whose owning node changed between two shard maps.

    This is *the* number for consistent hashing. Everything else -- the ring,
    the binary search, the virtual nodes -- exists to make this small. Takes
    anything with a `get`, so a ring and a modulus can be measured identically.
    """
    keys = list(keys)
    if not keys:
        return 0.0
    moved = sum(1 for k in keys if before.get(k) != after.get(k))
    return moved / len(keys)


def spread(counts: Iterable[int]) -> float:
    """Relative standard deviation (stdev / mean) of a load distribution.

    Scale-free, so a four-node ring and a forty-node ring are directly
    comparable and so is a run over 10k keys against one over 1M. 0.0 is a
    perfectly even split; 0.30 means a typical node is 30% off its fair share,
    which for a cache tier is the difference between fine and paging someone.
    """
    values = list(counts)
    if not values:
        return 0.0
    mean = statistics.fmean(values)
    if mean == 0:
        return 0.0
    return statistics.pstdev(values) / mean
