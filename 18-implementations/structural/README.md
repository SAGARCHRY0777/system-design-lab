---
topic: Bridge, Composite, Flyweight
category: Implementation
difficulty: Intermediate
concepts: [bridge, composite, flyweight, scatter-gather, tail-latency, dictionary-encoding]
---

# Bridge, Composite, Flyweight — implementation

The other four structural patterns are [wrappers](../wrappers/) and share a page because telling
them apart *is* the content. These three are not wrappers and are not confused with each other.
What they share is a problem shape — **each exists because some multiplicity got out of hand:**

```
Bridge      too many CLASSES     N abstractions × M implementations
Composite   too many NODES       a tree the caller should not have to walk
Flyweight   too many INSTANCES   a million objects holding ten distinct values
```

```bash
pytest test_structural.py -q     # 19 tests
python structural.py             # the same assertions, no test runner
```

Each one is sold on a claim that is arithmetic or a failure mode rather than taste, so every test
checks the claim.

## Bridge — and where it stops paying

N×M against N+M is the whole pitch. The interesting result is the **crossover**:

| | explicit (N×M) | bridge (N+M) | |
|---|---|---|---|
| 1 × M | M | M + 1 | **bridge is worse, at every M** |
| 2 × 2 | 4 | 4 | a tie, plus an indirection |
| 2 × 3 | 6 | 5 | it starts paying |
| 4 × 5 | 20 | 9 | |
| 10 × 10 | 100 | 20 | |

```python
assert crossover(1) is None          # one abstraction: a bridge NEVER pays
assert crossover(2) == 3             # two: from the third implementation
```

> **With a single abstraction or a single implementation, a bridge is not "a bit speculative" — it
> is strictly more classes than not having it, at every size, with an indirection on top.** That is
> the arithmetic behind the catalogue's advice to reach for it only when both axes actually vary.
> Most codebases have one backend and always will.

Worth knowing before a code review: **Bridge and Strategy are structurally identical** — an object
holding an interface it delegates to. They differ only in intent (two hierarchies evolving
separately, against swapping one algorithm), and no test can tell them apart.

## Composite — two guards, and the one with real teeth

### The uniformity, and what it costs

One call works whether you hold a file or a thousand-node tree. The price is that **the interface
becomes the union of both needs** — `add` is meaningless on a leaf, and the three ways out (raise,
no-op, or drop the method and lose the uniformity) are all compromises. This one raises, because a
silent no-op loses data and the caller never finds out.

### Depth and cycles are reachable from user input

```python
with pytest.raises(CompositeError, match="nesting exceeds"):
    total_size(deeply_nested)      # not RecursionError from an arbitrary frame

with pytest.raises(CompositeError, match="cycle detected"):
    total_size(cyclic)             # not an infinite loop
```

The three-line recursive version of `total_size` is a denial of service. A document, a JSON body or
a synced folder nests as deeply as whoever produced it chose — **deeply nested input is a CVE class,
not a hypothetical** — and a tree is a promise, not a type: one symlink and the recursion never
ends.

`MAX_DEPTH` sits below `sys.getrecursionlimit()` on purpose, so the guard fires first and names the
node. `RecursionError` tells you nothing about which input caused it.

### Two details the break harness found

Both of these passed the original suite, which meant two docstring claims were unverified:

**Cycle detection must key on identity, not name.** But the obvious test for it proves nothing:
siblings sharing a name never collide, because the path is scoped per branch. It only breaks when a
node repeats one of its own **ancestors** — `src/lib/src/index.js`, or anything vendored.

**It must track the ancestor path, not every node visited.** A single accumulating `seen` set
rejects a *diamond* — one node legitimately reachable by two routes — and calls it a cycle. That
was a real bug in the first version here, and the docstring explicitly claimed the opposite.
Passing a fresh `frozenset` down each level scopes the check and drops it on the way back up.

```python
shared = Node("shared", size=7)
tree = Node("root").add(Node("left").add(shared)).add(Node("right").add(shared))

assert total_size(tree) == 14      # reached twice, counted twice, not rejected
```

### The distributed one, and it is the number to remember

A scatter-gather returns when its **slowest** member does, so it is slow whenever *any* member is:

```
  1 member     1.0%
 10            9.6%
100           63.4%     ← each member's p99 is the composite's median
1000         100.0%
```

```python
assert round(prob_any_slow(100), 3) == 0.634      # 1 - 0.99**100
assert scatter_gather_latency([5, 6, 7, 900]) == 900   # the mean says 230
```

**A per-shard 99th percentile everyone is pleased with becomes the typical experience of the
aggregate.** This is *The Tail at Scale*, it is why fan-out width is an availability decision and
not only a throughput one, and it is why hedged requests exist. It is also why reporting the mean
of a fan-out is reporting nothing.

## Flyweight — memory, and the requirement that makes sharing safe

```python
a, b = style("Inter", 12), style("Inter", 12)
assert a is b                                        # the same object, not an equal one

glyphs = [Glyph(c, i, style("Inter", 12)) for i, c in enumerate("hello world" * 1000)]
assert len({id(g.style) for g in glyphs}) == 1       # 11,000 glyphs, one style object
```

Splitting **intrinsic** (shared) from **extrinsic** (per-use) state is the design work. Put
`position` in the flyweight and you have a million flyweights and no saving; leave `font` out and
two glyphs share a position.

**`frozen=True` is not tidiness, it is the pattern's one hard requirement.** A flyweight is shared
by construction, so a mutable one lets any holder change every other holder's data — and the bug
surfaces arbitrarily far from the mutation, in code that never touched the object.

### Python already does this

```python
s1, s2 = "".join(["ab", "cd"]), "".join(["ab", "cd"])
assert s1 == s2 and s1 is not s2          # equal, two objects
assert sys.intern(s1) is sys.intern(s2)   # and now one
```

Note what is deliberately **not** asserted: integer identity. `1000 is 1000` is `True` inside one
code object because the compiler folds equal constants — which looks like interning and isn't.
Built strings are the honest demonstration, because they are genuinely distinct objects.

### The version you will actually meet

```python
rows = ["GET", "POST", "GET", "GET", "DELETE"] * 2000
dictionary, codes = dictionary_encode(rows)     # ["GET","POST","DELETE"], [0,1,0,0,2, ...]

assert encoded_bytes(dictionary, codes) * 3 < sum(len(r) for r in rows)
```

**Dictionary encoding in a columnar store is Flyweight at the storage layer.** Parquet, ORC and
ClickHouse all store a low-cardinality column as a dictionary of distinct values plus an array of
small integers — intrinsic state once, extrinsic state holding a reference. It is the single
largest reason columnar formats beat row formats on categorical data.

`encoded_bytes` asserts `len(dictionary) <= 256`, because one byte per code is only honest for low
cardinality. Above that the real engines switch strategy, and a size calculation still quoting one
byte would be reporting a saving that does not exist.

## Verified by breaking it

Seven deliberate breaks, each expected to fail a named test:

| Break | Caught by |
|---|---|
| Depth guard removed | `test_unbounded_nesting_is_a_denial_of_service` |
| Cycle guard removed | `test_a_cycle_is_detected_rather_than_hung` |
| Cycle keyed on **name** | `test_a_node_may_share_a_name_with_its_own_ancestor` |
| Cycle **accumulates** instead of scoping to the path | `test_a_diamond_is_not_a_cycle` |
| Flyweight factory stops sharing | two tests |
| Flyweight becomes mutable | `test_a_mutable_flyweight_would_be_a_disaster` |
| Low-cardinality assertion dropped | `test_the_encoding_only_claims_what_low_cardinality_supports` |

**Rows 3 and 4 initially slipped through**, which is how both defects were found. Row 4 was a real
bug — the diamond rejection — and row 3's first test put the duplicate names in sibling branches,
where they can never collide.

## What this deliberately does NOT implement

- **The four wrappers.** [Their own page](../wrappers/), because telling them apart is the content.
- **A real scatter-gather.** `prob_any_slow` is exact arithmetic and `scatter_gather_latency` is one
  `max`; threads would add noise and prove less.
- **Hedged requests.** The mitigation for the tail problem, and a [resilience pattern](../../13-design-patterns/CATALOGUE.md#resilience-patterns)
  rather than a structural one.
- **An iterative `total_size`.** It would remove the recursion limit and keep the cycle problem,
  which is the more interesting half.

## Related

- **[Bridge, Composite, Flyweight — the pattern page](../../13-design-patterns/structural/)**
- [Wrappers](../wrappers/) — Adapter, Decorator, Proxy, Facade: the other four
- [LRU cache](../lru-cache/) — where intrinsic/extrinsic shows up as what is worth keeping
- [Pattern catalogue](../../13-design-patterns/CATALOGUE.md#bridge)
- [Latency](../../00-foundations/latency/) — the foundation behind the tail-at-scale arithmetic
