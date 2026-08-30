---
topic: Sharding
category: Patterns
difficulty: Advanced
concepts: [partitioning, consistent-hashing, hot-keys]
related: [database, replication, scalability, consistency]
---

# Sharding ★

`[ADVANCED]` · Split data across machines by a key. Buys write scale and unbounded storage. Costs you cross-shard joins — and the shard key is effectively permanent.

---

## 1. One-line definition

Horizontally partitioning a dataset across multiple machines, each holding a disjoint subset.

## 2. Explain like I'm new

One filing cabinet is full. You buy four, and agree a rule: surnames A–F in cabinet one, G–M in two,
and so on.

Now four people can file at once, and you have four times the space. But **"list everyone who joined
in March" now means opening all four cabinets** and merging the results — a question that used to be
one lookup. And if half your customers are called Smith, cabinet four is overflowing while the others
sit empty.

Both of those problems are permanent features of the decision, not teething issues.

## 3. Real-world analogy

The cabinets above.

**Where it breaks:** you can re-label physical cabinets over a weekend. Re-sharding a live database
means moving terabytes while it is serving traffic, without losing writes. That is a project, not a
maintenance window.

## 4. Technical explanation

Sharding is **partitioning across machines**. Partitioning within one machine is a different thing
with a different cost profile — it helps query performance and does nothing for write throughput or
storage limits.

| Strategy | How | Good | Bad |
|---|---|---|---|
| **Range** | A–F, G–M… | Range scans work; easy to reason about | Hotspots — sequential keys all land on one shard |
| **Hash** | `hash(key) % N` | Even distribution | No range scans; **resharding remaps nearly everything** |
| **Consistent hash** | Hash onto a ring | Adding a node remaps only ~1/N | More complex; needs virtual nodes for balance |
| **Directory** | An explicit lookup table | Total flexibility; easy rebalancing | The directory is a new SPOF and a hot path |
| **Geographic** | By region | Data residency, local latency | Uneven population; cross-region queries are slow |

### Why `hash(key) % N` is a trap

With modulo, changing `N` changes the answer for almost every key:

```
N = 4  →  hash % 4        N = 5  →  hash % 5
key A: 3                  key A: 1     moved
key B: 0                  key B: 4     moved
key C: 2                  key C: 2     stayed
```

Adding one machine remaps roughly `(N-1)/N` of all keys — about 80% at N=5. Every one of those rows
must physically move before the system is correct again.

**Consistent hashing** places both keys and nodes on a ring; a key belongs to the next node clockwise.
Adding a node steals a contiguous arc from exactly one neighbour, so only ~1/N of keys move. Virtual
nodes (each physical node appearing many times on the ring) smooth the distribution.

```mermaid
flowchart TD
    ADD["Add one machine: 4 shards becomes 5"]
    ADD --> MOD["hash mod N<br/>N is inside the mapping function"]
    ADD --> RING["Consistent hash ring<br/>N is NOT in the mapping function"]
    MOD --> M1["Every key is now divided by a<br/>different number, so every key<br/>gets a fresh answer"]
    M1 --> M2["Roughly 4 keys in 5 move.<br/>The migration is the entire dataset,<br/>and every cache keyed by shard<br/>is cold in the same instant."]
    RING --> R1["The new machine takes one position<br/>on the ring and owns the arc between<br/>itself and its clockwise neighbour"]
    R1 --> R2["Only that one arc moves, about 1/N.<br/>Every other key keeps its owner,<br/>because no other arc changed at all."]
    style M2 fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style R2 fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
```

**This is the key insight of the whole page, and it is one line of the diagram: whether `N` appears in
the mapping function.** With modulo, the shard of a key is defined relative to how many shards exist,
so changing that count redefines every key at once. On the ring, a key maps to a fixed *position* and
a machine owns a range of positions — adding a machine perturbs one neighbour's range and nothing
else. Same goal, same even distribution; completely different blast radius when the fleet changes.

## 5. Engineering at scale

**The shard key is the most consequential and least reversible decision in the whole design.** It
determines what queries remain possible. Changing it later means rewriting every row and, usually,
part of the application.

A good shard key has three properties, and they pull against each other:

1. **High cardinality** — enough distinct values to spread across shards
2. **Even distribution** — no value dominates
3. **Present in most queries** — otherwise every read is a scatter-gather

That third one is the trap. Shard by `user_id` and any query by `user_id` is a single-shard lookup —
fast, scalable. But "all orders placed today" now hits every shard and takes the slowest shard's
latency, every time. **You have optimised one access pattern and made all the others worse.**

## 6. The problem it solves

One machine's write throughput and storage capacity. These are the only two problems sharding solves,
and it is worth being strict about that, because it is frequently applied to problems it does not
address.

## 7. The problem it does NOT solve

It does not help read latency — [caching](../../04-caching/fundamentals/) and
[replicas](../replication/) do that. It does not improve availability; in the naive form it *reduces*
it, because now `N` machines must be up instead of one. And it does not fix a slow query — it
distributes it.

## 8. Why does this exist?

Because vertical scaling has a ceiling and data volume does not. When the working set exceeds what
one machine can hold, or write throughput exceeds what one machine can commit, there is no
alternative that preserves a single logical dataset.

---

## 9. How it works

```mermaid
flowchart TD
    C[Client] --> R{"Router<br/>shard_key → shard"}
    R -->|"hash(user)=0"| S0[(Shard 0)]
    R -->|"hash(user)=1"| S1[(Shard 1)]
    R -->|"hash(user)=2"| S2[(Shard 2)]
    R -.->|"query WITHOUT the shard key<br/>→ scatter-gather to all"| S0 & S1 & S2

    style R fill:#2a2317,stroke:#d9a441,color:#e4ecea
```

The solid arrows are what sharding is for: one key, one shard, constant work regardless of how many
shards exist. The dashed arrows are what it costs — a query without the shard key must ask every
shard and wait for the slowest.

## 11. What you lose

| Lost | Why | Workaround |
|---|---|---|
| **Cross-shard joins** | Rows live on different machines | Denormalise; or join in the application |
| **Cross-shard transactions** | No single commit point | Saga with compensating actions; 2PC (which blocks) |
| **Global uniqueness** | No shard sees all values | UUIDs, or a dedicated ID service (Snowflake-style) |
| **Global secondary indexes** | An index by a non-shard-key spans shards | A separate index shard; or a search index |
| **`ORDER BY` + `LIMIT` across shards** | Each shard's top-10 is not the global top-10 | Over-fetch from each shard, then merge |
| **`COUNT(*)`** | Requires touching every shard | Maintain approximate counters |

That list is the real price. **Sharding does not make the database bigger; it makes it a distributed
system**, and every convenience that depended on there being one machine is gone.

## 13. When to shard

Only after all of these are true:

- Queries are optimised and indexed
- You have scaled up as far as is reasonable
- Caching absorbs what it can
- Read replicas handle read load
- **Writes or storage still exceed one machine**

## 14. When NOT to

- **Before the above.** Sharding early is the most expensive form of premature optimisation there is,
  because it is close to irreversible.
- When reads are the problem — replicas and cache are simpler and reversible
- When you cannot identify a key with all three properties
- When the dataset would fit on one modern machine, which is a larger number than most people assume
- When the team cannot operate `N` databases, backups, failovers and migrations

## 17. Trade-offs

| Choose | Get | Pay |
|---|---|---|
| Shard | Write scale, unbounded storage | Joins, transactions, global queries, operational load |
| Hash key | Even distribution | No range scans; resharding is expensive |
| Range key | Range scans | Hotspots on sequential keys |
| Consistent hashing | Cheap rebalancing | Complexity, virtual nodes |
| More shards | More headroom | More machines to operate; slower scatter-gather |
| Directory-based | Flexible rebalancing | A lookup on the hot path; a new SPOF |

## 18. Why not?

| Alternative | Why not here | When it WOULD win |
|---|---|---|
| **Scale up** | Hard ceiling | Below the ceiling — **which is higher than most teams think** |
| Read replicas | Do not help writes | The problem is reads |
| Caching | Does not help writes or storage | Reads are skewed |
| Archive cold data | Does not help write throughput | Growth is history, not activity — **frequently the real answer** |
| Multiple databases by domain | No cross-domain queries | Domains are genuinely independent |
| A managed distributed database | Cost, lock-in | You need sharding but not the operational burden |

Row four deserves attention. A great many "we need sharding" conversations are really "we have five
years of data nobody queries in the same table as today's". Moving cold rows out is reversible and
takes a week.

## 19. Failure scenarios

| Failure | What happens | Mitigation |
|---|---|---|
| **Hot shard** | One key or range takes most traffic; that shard saturates while others idle | Better key; split the hot range; a cache in front |
| One shard down | That fraction of users is fully down | Replicate every shard — see [replication](../replication/) |
| Resharding mid-write | Writes land on the old shard and are lost | Dual-write during migration; a cutover with fencing |
| Scatter-gather tail | Every cross-shard query takes the slowest shard's p99 | Avoid such queries; hedged requests |
| Uneven growth | Shards diverge in size over time | Consistent hashing; periodic rebalancing |
| Cross-shard transaction | Partial application, inconsistent state | Sagas with compensations |

**Hot shards are the defining failure.** Hashing distributes *keys* evenly, not *load*. One celebrity
user, one popular product, one tenant ten times bigger than the rest — and a perfectly balanced hash
gives you a badly balanced system.

```mermaid
flowchart TD
    H["Uniform hash over 4 shards<br/>1 million customer keys"]
    H --> S0["Shard 0<br/>250,000 keys"]
    H --> S1["Shard 1<br/>250,000 keys"]
    H --> S2["Shard 2<br/>250,000 keys"]
    H --> S3["Shard 3<br/>250,000 keys<br/>one of which is the celebrity"]
    S0 --> L0["about 120 requests per second"]
    S1 --> L1["about 130 requests per second"]
    S2 --> L2["about 125 requests per second"]
    S3 --> L3["about 9,000 requests per second<br/>CPU pinned, this shard is the outage"]
    style S3 fill:#2a2317,stroke:#d9a441,color:#e4ecea
    style L3 fill:#2b1c17,stroke:#e0705a,color:#e4ecea
```

Illustrative numbers, but the shape is the real one. **The middle row is perfectly balanced and the
bottom row is not** — and the hash function only ever promised you the middle row. Nothing in the key
distribution is wrong, no rebalancing will help, and re-hashing moves the celebrity to a different
shard which then becomes the hot one. Note also that an aggregate CPU dashboard averages the bottom
row into something unremarkable, which is why per-shard monitoring is not a nice-to-have here.

## 20. Resharding

The operation everyone underestimates. The safe shape is roughly:

1. Stand up the new shards
2. **Dual-write** to old and new
3. Backfill historical data
4. Verify — compare row counts and checksums
5. Cut reads over, shard by shard
6. Stop dual-writing, decommission

```mermaid
sequenceDiagram
    participant App as Application
    participant Old as Old shard
    participant New as New shard
    participant Job as Backfill job
    Note over App,New: Step 2 - dual write starts FIRST
    App->>Old: write, still authoritative
    App->>New: write, shadow copy
    Note over Job: Step 3 - only now backfill history
    Job->>Old: read historical rows
    Job->>New: write historical rows
    Note over Old,New: Step 4 - compare counts and checksums.<br/>This is the step people skip.
    Note over App,New: Step 5 - move reads over, shard by shard
    App->>New: read
    Note over App,Old: Step 6 - stop dual-writing LAST. Until this<br/>point the old shard is still complete,<br/>so rollback is one configuration change.
```

Read the ordering, because that is where the correctness lives, not in the steps themselves. Dual-write
must begin **before** the backfill, or every row written during the backfill window falls into the gap
between the snapshot and the cutover and is silently missing. And dual-writing must stop **last**,
because for as long as the old shard is still receiving every write it remains a complete copy — which
is the only thing making steps 2 to 5 reversible at all.

Every step must be reversible, and step 4 is the one people skip. Some systems avoid this entirely by
**over-sharding at the start**: create 1,024 logical shards on 4 physical machines, and "resharding"
becomes moving logical shards, which is a data-movement problem rather than a re-keying problem.
That is a genuinely good trick and costs almost nothing to adopt early.

---

## 25. Without it → With it → New problem → Next

```
Without it   →  one machine caps write throughput and total storage
With it      →  writes and storage scale roughly linearly with machines
New problem  →  no cross-shard joins or transactions; hot shards; a shard key
                that is effectively permanent; N machines to operate
Next         →  replication per shard for availability, a search index for
                queries the shard key cannot serve, and sagas for cross-shard writes
```

## 26. Combination patterns

- **[Shard + replica](../../14-component-combinations/MATRIX.md)** — shard for writes, replicate each shard for reads and availability. The standard large-database shape.
- **[Shard + distributed lock](../../14-component-combinations/MATRIX.md)** — resharding needs mutual exclusion, one of the few genuinely warranted uses
- **[Shard + search](../../14-component-combinations/MATRIX.md)** — ⚠ scatter-gather search takes the slowest shard's latency every time; use a dedicated index

## 28. Common mistakes

| Mistake | Why it is wrong |
|---|---|
| Sharding before exhausting simpler options | Near-irreversible complexity for a problem cache or replicas would have solved |
| A shard key absent from most queries | Every read becomes scatter-gather |
| Low-cardinality shard key | Cannot spread; some shards stay empty |
| `hash % N` | Adding a node remaps ~80% of keys |
| Assuming hashing prevents hot shards | It balances keys, not load |
| Not replicating each shard | Availability *drops* — N machines must now be up |
| No plan for resharding | Discovering the plan is needed during an incident |
| Forgetting global uniqueness | Auto-increment IDs collide across shards |

## 29. Monitoring

Per-shard everything: QPS, storage, latency, error rate. **An aggregate hides a hot shard perfectly**
— that is the whole reason to break it out. Track the ratio of scatter-gather to single-shard
queries; a rising ratio means the access pattern has drifted away from the shard key. Watch shard
size divergence as the early signal that rebalancing is due.

## 31. Exercises

**1.** Storage has reached 3 TB and queries are slowing. The team proposes sharding. What do you check
first, and what is the most likely real answer?

<details><summary>Answer</summary>

Everything in [§13](#13-when-to-shard), in order: query plans and indexes, vertical headroom — 3 TB is
well inside one modern machine — then cache, then read replicas. Sharding solves exactly two problems,
write throughput and storage capacity, and "queries are slowing" is neither of them until proven.

The most likely real answer is that five years of history nobody queries is sitting in the same table
as this week's rows. Archiving cold data is reversible and takes a week; sharding is close to
permanent and takes a quarter. Row four of [§18](#18-why-not) is the one to read twice.
</details>

**2.** You shard on `user_id`. Which queries did you just make expensive, and why is that not fixable
later with an index?

<details><summary>Answer</summary>

Every query that does not carry `user_id`. "All orders placed today" now scatters to every shard and
gathers, so it costs the **slowest shard's p99 every single time** rather than one lookup.

An index cannot fix it because a secondary index is per-shard: no shard holds the global answer. Your
options are a separate index shard, a dedicated search index, or maintaining a denormalised copy —
all of which are new systems. A good shard key needs high cardinality, even distribution **and**
presence in most queries, and the third property is the one that pulls against the others.
</details>

**3.** Sixteen shards, a uniform hash, tenants spread evenly. One shard sits at 95% CPU while the rest
idle at 10%. What happened?

<details><summary>Answer</summary>

Hashing distributes **keys** evenly. It does not distribute **load**. One tenant ten times larger than
the others, one celebrity account, one product on the front page — a perfectly balanced hash gives you
a badly balanced system, and this is sharding's defining failure rather than an edge case.

Fixes all cost something: isolate that tenant onto its own shard, split the hot range, or put a cache
in front of the hot key. Changing the shard key rewrites every row. Note also that an aggregate CPU
dashboard would have read ~15% and told you nothing — **per-shard monitoring is the whole point**.
</details>

**4.** Why is `hash(key) % N` a trap, and what is the cheaper thing to do at the very start?

<details><summary>Answer</summary>

Because `N` appears in the formula. Going from 4 shards to 5 changes the destination of roughly
`(N−1)/N` of all keys — about 80% — and every one of those rows must physically move before the
system is correct again. Consistent hashing puts keys and nodes on a ring, so a new node steals a
contiguous arc from one neighbour and only ~1/N of keys move.

The cheaper trick is to **over-shard logically at the start**: create 1,024 logical shards on 4
machines. Resharding then becomes moving logical shards between machines — a data-movement problem
rather than a re-keying one — and it costs almost nothing to adopt early.
</details>

**5.** You shard eight ways and your availability gets *worse*. Explain, and say what you left out.

<details><summary>Answer</summary>

Naive sharding reduces availability: eight machines must now be up instead of one, and losing any one
of them takes 1/8 of your users **fully** down rather than degrading everyone slightly. Availability
of the whole is the product of the parts, so eight nodes at 99.9% each is 99.2%.

What is missing is a replica per shard. Sharding buys write scale and storage; replication buys
availability; they are orthogonal and the standard large-database shape is both together — see
[replication](../replication/). Sharding without it converts one single point of failure into eight.
</details>

## 32. Decision checklist

- [ ] Queries optimised, scaled up, cached and replicated first
- [ ] The specific ceiling (writes or storage) measured, not assumed
- [ ] Shard key has cardinality, distribution, **and** appears in most queries
- [ ] Queries that will become scatter-gather are enumerated and accepted
- [ ] Global uniqueness strategy chosen
- [ ] Each shard is itself replicated
- [ ] Resharding plan exists — ideally over-sharded logically from the start
- [ ] Per-shard monitoring, not aggregate

## 27. Implementation

[Consistent hashing](../../18-implementations/consistent-hashing/) is implemented and measured. Adding
one node to a ring of four remaps **19.8%** of keys against **80.2%** for `hash % N` — and the
virtual-node effect is measured too: with one vnode per node the busiest owns 4.34x its fair share,
with 150 it owns 1.08x.

## 33. Related

- [Observability](../../11-observability/) — how you would know any of this broke
- [Database](../fundamentals/) — step 5 of scaling, and the last one
- [Replication](../replication/) — availability per shard
- [Consistency](../../00-foundations/consistency/) · [CAP](../../00-foundations/cap-theorem/)
- [Glossary: hot key](../../GLOSSARY.md#hot-key) · [sharding](../../GLOSSARY.md#sharding)

<!-- PATH:BEGIN -->

---

<sub>**The reading path** · step 16 of 27 · *Sharding*</sub>

◀ **Previous** [Replication](../../05-databases/replication/README.md) &nbsp;·&nbsp; **Next** [Queue](../../06-messaging/queues/README.md) ▶

<!-- PATH:END -->
