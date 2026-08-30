---
topic: Consistent Hashing
category: Implementation
difficulty: Advanced
concepts: [partitioning, sharding, rebalancing, hot-keys]
---

# Consistent Hashing — implementation

A hash ring, and the one-line arithmetic it replaces, in one file — because the interesting thing is
not how a ring works. It is **how much less damage it does when the cluster changes size**. Both
answer "which node owns this key?". They differ by a factor of four at eight nodes and a factor of
thirty-two at thirty-two, and that divergence is the entire basis for choosing.

```bash
pytest test_consistent_hashing.py -q   # 22 tests
python bench.py                        # real measurements, run them yourself
```

## What this demonstrates

| | Keys moved when one node joins | Load spread | Lookup |
|---|---|---|---|
| `HashRing` (150 vnodes) | **~1/N** — 10.7% at eight nodes | 0.078 relative stdev | O(log(N·V)) — a `bisect` |
| `HashRing` (1 vnode) | ~1/N | **1.285** — one node owns 4.3× its share | O(log N) |
| `ModuloSharder` | **~(N−1)/N** — 89% at eight nodes | 0.000 — perfectly even | O(1) — one modulo |

Two separate lessons sit in that table, and they pull in opposite directions.

**The modulus is not a strawman.** Its distribution is *better* than a ring's — perfectly even by
construction, no ring to hold, no rebuild. If your node count is fixed forever, it is the right
answer. It has exactly one failure mode, and the failure mode is called "scaling up".

**A plain ring is not a design either.** Put eight nodes on a circle and the arcs between them are
not equal — they are eight random cuts. The test asserts what that costs:

```python
def test_one_vnode_per_node_distributes_appallingly():
    ring = HashRing([f"node-{i}" for i in range(8)], vnodes=1)
    counts = ring.distribution(KEYS)
    assert max(counts.values()) / fair_share > 4.0    # node-2 owns 55% of the keyspace
    assert min(counts.values()) / fair_share < 0.25
```

Virtual nodes are what make the circle usable, and the improvement is measurable rather than
folklore — relative spread falls as roughly 1/√vnodes.

The headline contrast is a pair of adjacent tests running the identical four-to-five rebalance:

```python
def test_ring_moves_about_one_over_n_when_a_node_joins():
    ...
    assert moved == pytest.approx(0.2022, abs=0.0001)     # 20% — the theoretical 1/5

def test_modulo_moves_almost_everything_when_a_node_joins():
    ...
    assert moved == pytest.approx(0.7965, abs=0.0001)     # 80% — four times the damage
```

Both figures are exact, not statistical, because `stable_hash` is pinned. Which brings up the
subtlety that costs people a day of debugging: **Python's built-in `hash()` is salted per
interpreter**. A ring built on it maps a key to a different node in every process and after every
restart. Consistent hashing is only consistent if the hash is, and `test_stable_hash_is_pinned_not_
merely_repeatable` asserts a literal digest for exactly that reason — `hash()` is repeatable *within*
a process too, so nothing weaker catches the substitution.

## Measured

Run on the machine below by `bench.py`. **These are real; nothing here is estimated.** The remap and
spread figures are properties of the algorithm and will reproduce byte for byte anywhere; only the
throughput belongs to this hardware.

```
machine : Intel64 Family 6 Model 183 Stepping 1, GenuineIntel
python  : 3.14.6 (Windows 11)
keys    : 100,000

KEYS REMAPPED when one node joins  (the whole point)
  cluster            ring     modulo   ideal 1/N+1   damage
  4 -> 5           19.8%      80.2%        20.0%    4.0x worse
  8 -> 9           10.7%      89.0%        11.1%    8.3x worse
  16 -> 17          6.3%      94.1%         5.9%   14.9x worse
  32 -> 33          3.0%      97.0%         3.0%   32.2x worse

LOAD SPREAD vs virtual nodes  (8 nodes, relative stdev; 0.0 is perfect)
   vnodes    spread   busiest  quietest   ring points
        1     1.285     4.34x     0.22x             8
        5     0.225     1.39x     0.68x            40
       25     0.160     1.27x     0.72x           200
       50     0.108     1.17x     0.76x           400
      150     0.078     1.13x     0.85x         1,200
      500     0.032     1.05x     0.96x         4,000
     1000     0.033     1.04x     0.95x         8,000

LOOKUP THROUGHPUT (single-threaded, best of 7, measured on a clean heap)
  HashRing 8 nodes (1,200 pts)       0.906 us/op    1,104,335 ops/s
  HashRing 512 nodes (76,800 pts)    1.118 us/op      894,234 ops/s
  ModuloSharder 8 nodes              0.708 us/op    1,411,995 ops/s

  ring / modulo             1.28x
  1,200 pts -> 76,800 pts   1.23x   64x the ring, O(log n) bisect absorbs it

REBUILD COST when membership changes  (best of 7, clean heap)
     8 nodes x  150 vnodes =   1,350 points      1.14 ms
    64 nodes x  150 vnodes =   9,750 points      8.65 ms
   512 nodes x  150 vnodes =  76,950 points     73.62 ms
   512 nodes x 1000 vnodes = 513,000 points    553.79 ms
```

**Read the first table bottom-up.** The modulo column gets *worse* as the cluster grows, which is
precisely backwards from what anyone wants — the bigger and more valuable the cluster, the more
catastrophic adding a machine to it becomes. At thirty-two nodes and 100k cached objects, going to
thirty-three costs **3,000 misses on a ring and 97,000 on a modulus**, arriving at the database
inside the same second. That is a thundering herd you scheduled yourself.

The ring costs 28% more per lookup than a modulo. Nobody has ever cared. A lookup is a sub-microsecond
local computation sitting in front of a network round trip that is three orders of magnitude slower.
A 64× bigger ring costs only 23% more, because a `bisect` is O(log n) and log 64 is 6.

The rebuild table is the honest cost of rebuilding the whole ring on every membership change rather
than patching it — 74ms at 512 nodes. It looks wasteful and is not: membership changes minutes or
hours apart, and rebuilding from a *sorted* node set is what guarantees two servers that learned the
same membership by different paths compute an identical ring. A clever incremental patch that
depends on insertion order gives you two nodes that disagree about who owns a key, which is two
writers for one row.

### A note on how these were measured

Both timed sections run *before* the remap and spread sections and are printed afterwards, and that
ordering is load-bearing rather than cosmetic. Those sections build and discard several
100,000-entry dicts, and running the sub-microsecond lookup loop after them reported **2.2 µs/op
against 0.9 µs on a clean heap** — a 3× error caused entirely by the benchmark's own litter. The
rebuild figures were off by 8× the same way.

The ratios survived both distortions intact while the absolute numbers did not. That is the reason
this page keeps telling you to read the ratios, and a decent argument for asking what else a process
did before any benchmark you are shown started its stopwatch.

**The 1,000-vnode row is where the smoothing stops paying.** Spread is no better than at 500, the
ring is twice the size, and the rebuild goes from 74ms to 554ms. 150 is the common default because
it captures most of the available improvement before any of those costs bite.

## What this deliberately does NOT implement

Everything that makes a shard map hard in production:

- **Agreement.** This is the big one. A ring is only useful if every node computes the *same* ring,
  which means membership has to come from somewhere authoritative — a coordination service, a gossip
  protocol, a config push. Two nodes with different membership sets disagree about who owns a key,
  and that is a split brain with two writers. Sorting on rebuild makes the ring a deterministic
  *function* of membership; getting everyone the same membership is a separate and much harder
  problem.
- **Weighted capacity.** Every node here gets the same 150 vnodes. Real clusters are heterogeneous —
  a machine with twice the RAM should own twice the keyspace, which means vnode counts proportional
  to capacity.
- **Rack and zone awareness.** `get_replicas` returns three distinct *nodes*. It has no idea whether
  those three are in one rack behind one switch, which would make three replicas exactly as durable
  as one.
- **Actually moving the data.** Bounding the fraction of keys that must move is the easy half. The
  hard half is the migration: streaming those keys to the new owner, serving reads from the old owner
  until it completes, and handling writes that land mid-flight. This computes an ownership map, not a
  transfer plan.
- **Bounded loads.** A ring balances *keys*, not *traffic*. One viral key is one key, and consistent
  hashing will faithfully route all of its traffic to a single node. See
  [hot keys](../../GLOSSARY.md#hot-key) — the usual fixes are per-key replication or an explicit
  overflow policy, and both live above the ring.
- **Incremental ring updates.** Rebuilding is O(N·V log N·V) and blocks. At 512 nodes and 1,000
  vnodes that is 554ms during which lookups wait. Production either keeps the rebuild off the request
  path or patches the sorted structure in place.
- **Jump consistent hash.** For the special case where nodes are numbered 0..N−1 and only ever added
  at the end, Lamping and Veach's jump hash gives the same 1/N property in seven lines, with no ring
  to hold at all. It cannot remove an arbitrary node, which is why it is not the general answer.

## Choosing

```
Node count fixed forever, no growth planned  -> ModuloSharder    (genuinely; it is simpler and evener)
Nodes join and leave, arbitrary removal      -> HashRing         <- the usual answer
Nodes only ever appended, numbered 0..N-1    -> jump consistent hash (not implemented here)
Traffic skewed onto a few keys               -> none of these; you have a hot-key problem
```

And once you have chosen a ring, the vnode count:

```
< 25    unusable        one node routinely owns 1.3x its share or worse
150     the default     ~8% spread, 1,200 points at 8 nodes
500     diminishing     ~3% spread, and the last real improvement
1000+   pointless       no better than 500, twice the memory, 8x the rebuild
```

The reason to reach for a ring is never lookup speed — the modulus wins that, and neither matters.
It is that the cluster will change size, and you would like that to be an operation rather than an
incident.

## Related

- [Sharding](../../05-databases/sharding/) — the concept page; consistent hashing is one shard-key
  strategy among several, and the page covers the others
- [LRU cache](../lru-cache/) — the thing that gets destroyed when a rehash sends every key to a new
  node
- [Circuit breaker](../circuit-breaker/) — what protects the database when a bad rebalance does send
  the whole keyspace at it
- [Trade-off framework](../../TRADEOFF-FRAMEWORK.md) — the axes this choice sits on
- [Glossary: sharding](../../GLOSSARY.md#sharding), [hot key](../../GLOSSARY.md#hot-key),
  [thundering herd](../../GLOSSARY.md#thundering-herd)
