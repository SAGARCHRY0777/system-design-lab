---
topic: Database
category: Components
difficulty: Intermediate
concepts: [durability, consistency, indexing, transactions]
related: [consistency, cap-theorem, sharding, replication, cache]
---

# Database ★

`[INTERMEDIATE]` · The component whose loss costs **data**, not just latency. Every other choice in a system is eventually constrained by this one.

---

## 1. One-line definition

A system that stores data durably and answers queries over it, with defined guarantees about what
survives a crash and what a reader may see.

## 2. Explain like I'm new

A filing cabinet that also answers questions. Not just "give me folder 47" but "how many folders were
opened last Tuesday" — and crucially, it promises that once it says *filed*, the paper is still there
after the building loses power.

That promise is the whole difference between a database and a cache. A cache is allowed to forget
everything at any moment. **A database that forgets is broken.**

## 3. Real-world analogy

A bank ledger: append-only, auditable, and never allowed to lose an entry.

**Where it breaks:** a paper ledger has exactly one copy and one reader at a time. A database has
many copies and thousands of concurrent readers and writers, which is where every hard problem in
this page comes from — [isolation](#12-isolation-levels), [replication lag](#19-failure-scenarios),
and [consistency](../../00-foundations/consistency/).

## 4. Technical explanation

Databases differ along one axis that matters more than the SQL/NoSQL label: **the access pattern they
are built to serve.**

| Type | Data shape | Query shape | Choose when |
|---|---|---|---|
| **Relational** | Rows, fixed schema | Joins, transactions, ad-hoc | **The default. Needs no justification.** |
| Key-value | Opaque blob by key | Get/put by exact key | Access is always by one key |
| Document | Nested JSON | By key, or fields within | The aggregate is the unit of access |
| Wide-column | Sparse rows, many columns | By partition key + range | Huge write volume, time-series |
| Graph | Nodes and edges | Traversal | **Relationships are the query**, not the data |
| Search index | Inverted index | Text, facets, ranking | Relevance matters, not exactness |

**Relational is the correct default and everything else needs an argument.** Postgres handles far
more load than most people assume, and "we might need to scale" is not a reason to give up
transactions and joins before you have measured anything. The most expensive architectural mistakes
in this area are made by teams who chose a distributed store at day one and spent two years
reimplementing joins in application code.

## 5. Engineering at scale

**Design for the query, not the entity.** The access pattern decides the storage, never the other way
round. This inverts how most people are taught to model data, and it is the single most useful habit
here — in a key-value or wide-column store, getting it wrong is not slow, it is *impossible without a
migration*.

**The storage engine matters more than the vendor.** Two engines dominate, and they are opposites:

| | **B-tree** | **LSM-tree** |
|---|---|---|
| Writes | In place — random I/O | Append to a log, merge later — sequential |
| Reads | One traversal, predictable | May check several levels; needs Bloom filters |
| Best for | Read-heavy, range scans | **Write-heavy** |
| Cost | Write amplification on random writes | Compaction: background CPU and I/O spikes |
| Examples | Postgres, MySQL/InnoDB | Cassandra, RocksDB, ScyllaDB |

If your workload is write-dominated and you picked a B-tree engine, you will be fighting random I/O
forever. That decision is made once, and it is nearly impossible to reverse later.

```mermaid
flowchart TD
    W["One small write to a random key"]
    W --> B["B-tree engine"]
    W --> L["LSM engine"]
    B --> B1["Locate the leaf page.<br/>Read it from disk if it is not<br/>already in the buffer pool."]
    B1 --> B2["Modify it in place and write<br/>the whole page back to its<br/>own fixed location."]
    B2 --> B3["Cost paid NOW, on the write path:<br/>a random seek plus a full page<br/>written for a few changed bytes."]
    L --> L1["Append to the in-memory memtable<br/>and one sequential log append.<br/>Acknowledge."]
    L1 --> L2["Later, flush the memtable to a new<br/>immutable sorted file. Nothing<br/>on disk is ever modified."]
    L2 --> L3["Cost paid LATER, in the background:<br/>compaction rewrites the same data<br/>several times over its lifetime."]
    style B3 fill:#2a2317,stroke:#d9a441,color:#e4ecea
    style L3 fill:#2a2317,stroke:#d9a441,color:#e4ecea
```

Both bottom boxes are amber because **neither engine avoids the work** — they differ only in when it
is paid and who waits for it. The B-tree charges every write synchronously and predictably; the LSM
charges nothing on the request path until compaction falls behind, at which point the bill arrives all
at once as a latency spike. That is the real trade: a steady tax versus a cheap write with a
background process that can lose a race with your write rate.

## 6. The problem it solves

Durable, queryable, concurrent access to shared state — with guarantees strong enough that
application code does not have to reason about crashes and interleaving.

## 7. The problem it does NOT solve

A database does not make your data model correct. It does not scale writes past one machine without
[sharding](../sharding/). It does not give you low latency to distant users — that is physics, not
configuration. And **it does not protect you from your own application**: a missing index, an N+1
query, or a transaction held open across a network call will bring down any database on the market.

## 8. Why does this exist?

Because the alternatives — files, and application-managed state — cannot provide concurrency control,
crash recovery, or ad-hoc queries. Every one of those was reinvented badly enough times that a
category emerged.

---

## 9. How it works

```mermaid
flowchart LR
    Q[Query] --> P[Parser]
    P --> O[Planner / Optimiser]
    O --> E[Execution engine]
    E --> B[Buffer pool<br/><i>in memory</i>]
    B <--> S[(Storage engine<br/>B-tree / LSM)]
    E --> W[Write-ahead log]
    W --> S

    style W fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
```

The **write-ahead log** is highlighted because it is the mechanism behind almost everything a database
promises. Write the intent to an append-only log and `fsync` it *before* touching the data pages, and
a crash mid-write is recoverable — replay the log. The same log then does double duty as the source
for [replication](../replication/) and for change data capture.

**Durability is the WAL and the `fsync`.** A database configured with `fsync` off is fast and is
lying to you about what it has saved.

```mermaid
flowchart LR
    T["Transaction commits"] --> W["Write-ahead log<br/>append-only, fsynced BEFORE<br/>any data page is touched"]
    W --> R1["Crash recovery<br/>replay the log forward to rebuild<br/>whatever the buffer pool lost"]
    W --> R2["Replication<br/>ship the same records to a replica<br/>and apply them in the same order"]
    W --> R3["Change data capture<br/>decode the same records into an<br/>event stream for search, cache, warehouse"]
    style W fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
```

Durability, replication and CDC are not three features — they are **three readers of one append-only
sequence**, which is why they share consequences that look unrelated in a feature list. Replication
lag is literally "how many log records behind"; a replica cannot diverge from an ordering the log
already fixed; CDC can never see a change that was not logged; and turning `fsync` off does not
degrade one of the three, it silently removes the guarantee under all of them at once.

## 10. Indexing

An index is a second data structure that trades write cost and storage for read speed.

| Concept | What to know |
|---|---|
| **B-tree index** | The default. Supports equality *and* range. |
| **Hash index** | Equality only, O(1). Cannot serve `>` or `ORDER BY`. |
| **Composite index** | Column order matters: an index on `(a, b)` serves `WHERE a=?` and `WHERE a=? AND b=?`, but **not** `WHERE b=?` — the leftmost-prefix rule. |
| **Covering index** | Contains every column the query needs, so the table is never touched. |
| **Partial index** | Indexes only rows matching a predicate. Small and cheap. |
| **Selectivity** | An index on a boolean column matching half the rows will be ignored — a scan is cheaper. |

**Every index makes writes slower.** An index is not free storage; it is a tax on every insert,
update and delete of the indexed columns. The common failure is a table with fifteen indexes added
one incident at a time, where writes have quietly become the bottleneck.

## 11. Transactions — ACID

| | Means | The one thing people get wrong |
|---|---|---|
| **A**tomicity | All or nothing | Only within one database. It does not span services — that is what sagas are for. |
| **C**onsistency | Constraints hold before and after | **Unrelated to the C in [CAP](../../00-foundations/cap-theorem/).** Different concept entirely. |
| **I**solation | Concurrent transactions do not corrupt each other | Almost nobody runs at full isolation — see below |
| **D**urability | Committed survives a crash | Depends on `fsync` actually being on |

## 12. Isolation levels

Weaker isolation is faster and permits specific anomalies. Knowing *which* anomaly each level allows
is the difference between choosing a level and inheriting one.

| Level | Dirty read | Non-repeatable read | Phantom | Notes |
|---|---|---|---|---|
| Read uncommitted | possible | possible | possible | Almost never useful |
| **Read committed** | no | possible | possible | **Postgres default** |
| **Repeatable read** | no | no | possible* | **MySQL/InnoDB default** |
| Serializable | no | no | no | Correct, and slowest |

\* Postgres's repeatable read also prevents phantoms; the SQL standard does not require it. **Two
databases at the "same" isolation level behave differently**, which is why the level name alone is
not a specification.

The practical rule: **read committed is fine until you do read-modify-write**. `SELECT balance` then
`UPDATE balance = x` is a lost-update bug at read committed, and no amount of care in application
code fixes it. Use `SELECT ... FOR UPDATE`, an atomic `UPDATE ... SET balance = balance - 10`, or
serializable.

```mermaid
sequenceDiagram
    participant A as Transaction A
    participant D as Database at read committed
    participant B as Transaction B
    A->>D: SELECT balance
    D-->>A: 100
    B->>D: SELECT balance
    D-->>B: 100
    Note over A,B: Read committed permits this overlap.<br/>Neither transaction can see the other,<br/>and neither has done anything wrong.
    A->>D: UPDATE balance to 90
    D-->>A: OK, committed
    B->>D: UPDATE balance to 90
    D-->>B: OK, committed
    Note over D: Two debits of 10 were applied.<br/>Balance is 90. It should be 80.<br/>No error was raised anywhere.
```

The anomaly is in the **overlap**, not in either transaction — read the two reads returning the same
value as the moment the bug is already certain, several milliseconds before either write. This is why
adding validation, retries or careful code inside A or B cannot help: each is individually correct.
Only something that makes the read-and-write a single indivisible step removes it, which is exactly
what the row lock, the atomic in-place `UPDATE`, and serializable each do in a different way.

---

## 13. When to use a relational database

- You need transactions across more than one row
- The query shape is not fully known in advance — ad-hoc reporting exists
- Data has genuine relationships
- **By default**, unless something specific rules it out

## 14. When NOT to

- Access is always by a single key and the value is opaque → key-value
- Write volume genuinely exceeds one machine and the data partitions cleanly → wide-column
- The query *is* a traversal ("friends of friends who like X") → graph
- Ranking and relevance matter more than exactness → search index
- **When you do not need a database at all** — a file, or a cache, or nothing

## 17. Trade-offs

| Choose | Get | Pay |
|---|---|---|
| Relational | Transactions, joins, flexible queries | Harder horizontal write scale |
| NoSQL | Scale, flexible schema | No joins; the access pattern is fixed at design time |
| More indexes | Faster reads | Slower writes, more storage |
| Stronger isolation | Fewer anomalies | Lower concurrency, more deadlocks |
| Synchronous replication | No data loss on failover | Latency on every write |
| Async replication | Fast writes | A failover window where committed data is lost |
| Normalisation | No update anomalies | Joins at read time |
| Denormalisation | Fast reads | Update anomalies; you now own consistency |

## 18. Why not?

| Alternative | Why not here | When it WOULD win |
|---|---|---|
| **A file** | No concurrency, no queries, no crash safety | Genuinely single-writer config or logs |
| SQLite | Single writer | Embedded, single-machine, read-heavy — **very underrated** |
| NoSQL from day one | Loses joins and transactions before you know if you need scale | Access pattern is genuinely single-key and volume is known to be huge |
| Sharding from day one | Enormous complexity, permanent shard-key commitment | You already know one machine cannot hold it |
| Managed cloud database | Cost, less control | Almost always right if the team is small — **operations is the real cost of a database** |

## 19. Failure scenarios

| Failure | What happens | Mitigation |
|---|---|---|
| Primary dies | Writes stop; reads continue on replicas | Automated failover — **tested** |
| Async replica promoted | Acknowledged writes in the lag window are **lost** | Sync replication for data that cannot be lost |
| Replication lag spike | Users do not see their own writes | Route reads to primary after write |
| Connection pool exhausted | Everything fails while the database is idle | Size with Little's Law; a per-service pool cap |
| Long transaction held open | Blocks vacuum/GC; bloat; lock pileups | Never hold a transaction across a network call |
| Missing index | A full scan under load takes everything down | Query review; alert on slow queries |
| N+1 queries | 1 + N round trips instead of 1 | Eager loading; the ORM proxy hid the cost |
| Split brain | Two primaries accept writes; divergence | Quorum, fencing tokens |
| Disk full | Usually a **total** outage, and predictable | Alert on growth trend, not just threshold |

**The most common real outage on this list is not hardware.** It is a missing index or an unbounded
query meeting a traffic increase.

## 20. Scaling — in order

The order matters, and most teams skip to step 5.

1. **Fix the queries.** Indexes, N+1, unnecessary columns. Routinely 10–100×, and free.
2. **Scale up.** Modern machines are enormous. No architectural change.
3. **Cache.** Absorbs skewed reads — see [cache](../../04-caching/fundamentals/).
4. **[Read replicas](../replication/).** Read scale; introduces lag.
5. **[Shard](../sharding/).** Write scale; the last resort, and near-irreversible.

Steps 1–3 solve the overwhelming majority of real problems. Step 5 changes what your application can
express, permanently.

## 23. Operational considerations

Backups are worthless until a restore has been **tested** — an untested backup is a hypothesis. Know
your RPO (how much data you can lose) and RTO (how long recovery may take) as numbers, not
adjectives. Schema migrations on a large table need expand-contract; `ALTER TABLE` that locks a
hot table is an outage you scheduled yourself.

---

## 25. Without it → With it → New problem → Next

```
Without it   →  no durable shared state; no concurrency control; no queries
With it      →  durable, queryable, transactional state
New problem  →  it is the one component that cannot simply be duplicated, so it
                becomes the bottleneck AND the single point of failure
Next         →  cache for read latency, replicas for read scale and availability,
                sharding for write scale — each with its own consistency cost
```

Every scaling story eventually becomes a story about the database. See
[the chain](../../SYSTEM-DESIGN-THINKING.md#part-1--the-chain).

## 26. Combination patterns

- **[Cache + database](../../14-component-combinations/MATRIX.md)** — the canonical latency fix
- **[Database + replica](../../14-component-combinations/MATRIX.md)** — read scale, replication lag
- **[Database + shard](../../14-component-combinations/MATRIX.md)** — write scale, no cross-shard joins
- **[Queue + database](../../14-component-combinations/MATRIX.md)** — the dual-write problem; solved by the outbox
- **[Database + search](../../14-component-combinations/MATRIX.md)** — truth versus query; always slightly out of sync

## 28. Common mistakes

| Mistake | Why it is wrong |
|---|---|
| Choosing NoSQL for "scale" before measuring | Gives up joins and transactions for scale you may never need |
| Modelling entities instead of queries | In a KV or wide-column store this is unrecoverable without migration |
| Adding indexes without removing any | Writes quietly become the bottleneck |
| Transactions held across network calls | Locks held for the duration of someone else's outage |
| Read-modify-write at read committed | Lost updates; no amount of application care fixes it |
| Trusting untested backups | Discovering the restore is broken during the incident |
| `SELECT *` | Fetches columns you do not need; defeats covering indexes |
| Reading from a replica right after writing | The 404-on-your-own-record bug |
| Confusing ACID's C with CAP's C | They are unrelated |

## 29. Monitoring

Slow query log, always on, with an alert. Replication lag with a threshold derived from your stated
consistency window. Connection pool utilisation — exhaustion looks like a total outage while the
database sits idle. Disk growth **trend**, not just a threshold, because the alert needs to fire days
before it matters. Lock waits and deadlock counts.

## 31. Exercises

**1.** A team picks a wide-column store for a new product "because we might need to scale". What have
they traded, and when will they find out?

<details><summary>Answer</summary>

Joins, multi-row transactions and ad-hoc queries — traded away before knowing whether the scale is
real. Relational is the correct default and everything else needs an argument; "we might need to
scale" is a hypothesis, not an argument.

They find out when the first unanticipated query appears, because in a wide-column or key-value store
the access pattern is fixed at design time. Getting the model wrong there is not slow, it is
**impossible without a migration** — which is what turns this into two years of reimplementing joins
in application code.
</details>

**2.** Reads are slow. Rank these and say why the order is not negotiable: shard, add a cache, fix the
queries, add read replicas, scale up.

<details><summary>Answer</summary>

Fix the queries → scale up → cache → read replicas → shard, exactly as in [§20](#20-scaling--in-order).

The order is forced by cost and reversibility, not preference. Indexing and killing an N+1 is
routinely 10–100×, free, and undoable this afternoon. Scaling up needs no architectural change at
all. A cache adds staleness and a failure mode. Replicas add lag and the read-your-writes bug.
Sharding is last because it is near-irreversible and it changes what the application can *express* —
no cross-shard joins, no `COUNT(*)`, a shard key you will live with forever.

Steps 1–3 solve the overwhelming majority of real problems, and most teams skip to step 5.
</details>

**3.** You have an index on `(tenant_id, created_at)` and a query that filters only on `created_at`.
Will it be used?

<details><summary>Answer</summary>

No — the **leftmost-prefix rule**. A composite index is ordered by its first column, so it serves
`WHERE tenant_id = ?` and `WHERE tenant_id = ? AND created_at = ?`, but a predicate on the second
column alone has nothing to seek on.

Before adding an index on `created_at`, note that it is not free: **every index is a tax on every
insert, update and delete** of the indexed columns. The classic failure is a table that accumulated
fifteen indexes one incident at a time, where writes have quietly become the bottleneck.
</details>

**4.** Under Postgres's default isolation level, `SELECT balance` followed by `UPDATE balance = :new`
is a bug. Why, and what are the three fixes?

<details><summary>Answer</summary>

Read committed permits non-repeatable reads, so two concurrent transactions can both read 100, both
compute 90, and both write 90 — one debit vanishes. This is a **lost update**, and no amount of care
in application code prevents it, because the race is between the read and the write.

Three fixes: `SELECT ... FOR UPDATE` to lock the row, an atomic `UPDATE ... SET balance = balance -
10` that never reads into the application at all, or serializable isolation. Note also that
"repeatable read" means different things in Postgres and MySQL, so the level name alone is not a
specification.
</details>

**5.** The database is slow every night at 3am and fine all day. Someone proposes a read replica. Do
you approve it?

<details><summary>Answer</summary>

Not before finding out what runs at 3am. The candidates are all scheduled work: backups, vacuum or
compaction, and batch jobs reading every row — and that last one also evicts the buffer pool and the
[cache](../../04-caching/fundamentals/) working set, so the morning traffic arrives cold and the
symptom outlives the job.

A replica may well be right, and moving analytics off the hot path is a good reason to have one. But
adding infrastructure to hide a pattern you have not explained buys lag, an operational burden and
another thing to fail — and it will not help at all if the cause was vacuum on the primary.
</details>

## 32. Decision checklist

- [ ] Access patterns written down **before** the schema
- [ ] Relational chosen by default, or a specific reason recorded for not
- [ ] Storage engine matches read/write balance
- [ ] Isolation level chosen deliberately; read-modify-write paths identified
- [ ] Index set reviewed for write cost, not only read benefit
- [ ] Connection pool sized by Little's Law
- [ ] RPO and RTO are numbers, and a restore has actually been performed
- [ ] Migration strategy for large tables (expand-contract)
- [ ] Slow query alerting on

## 33. Related

- [Observability](../../11-observability/) — how you would know any of this broke
- [Consistency](../../00-foundations/consistency/) · [CAP](../../00-foundations/cap-theorem/)
- [Cache](../../04-caching/fundamentals/) — step 3 of scaling reads
- [Combination matrix](../../14-component-combinations/MATRIX.md)
- [Glossary: replication](../../GLOSSARY.md#replication) · [sharding](../../GLOSSARY.md#sharding)
