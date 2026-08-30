---
topic: Consistency
category: Foundations
difficulty: Intermediate
concepts: [replication, cap, isolation]
related: [cap-theorem, availability, reliability]
---

# Consistency

`[INTERMEDIATE]` · Whether every reader sees the same data. The moment you have more than one copy, you have to decide how much disagreement you will tolerate.

---

## 1. One-line definition

The guarantee about what a read may return, relative to the writes that preceded it.

## 2. Explain like I'm new

You post a photo. Your phone shows it immediately. Your friend refreshes and does not see it for two
seconds.

That two-second window is **inconsistency**, and it is not a bug — it is a deliberate trade someone
made so the app could be fast and stay up. For a photo, two seconds is invisible. For a bank balance,
two seconds is a lawsuit. **The same technical behaviour is fine or fatal depending entirely on what
the data means.**

## 3. Real-world analogy

Several notice boards across a campus. Post an update on one; someone reading another sees the old
version until a runner carries the update over.

**Where it breaks:** real replicas can receive updates in *different orders*, so two boards can
disagree about which of two updates came last. That is the genuinely hard part, and no notice-board
intuition prepares you for it.

```mermaid
sequenceDiagram
    participant L as Writer in London
    participant A as Replica A
    participant B as Replica B
    participant S as Writer in Sydney
    L->>A: set title to Draft
    S->>B: set title to Final
    A->>B: replicate Draft
    B->>A: replicate Final
    Note over A: applied Draft, then Final<br/>A believes Final is the newer value
    Note over B: applied Final, then Draft<br/>B believes Draft is the newer value
    Note over A,B: the same two writes, two different winners.<br/>Neither replica is lagging or broken.
```

Neither replica has dropped a message and neither is behind — both have applied both writes. Read
the two notes: the disagreement is about **order**, which is exactly what a notice board cannot
model, because a board has one reading position and a distributed system has one per replica. This
is the thing conflict resolution exists to settle, and it is why the settlement cannot simply be
"whichever arrived last".

## 4. Technical explanation

Consistency is a spectrum, not a switch. From strongest to weakest:

| Model | Guarantee | Cost |
|---|---|---|
| **Linearizable** | Every read sees the latest write, globally, as if there were one copy | Coordination on every operation; highest latency |
| **Sequential** | Everyone sees operations in the *same* order, not necessarily real-time order | Cheaper than linearizable |
| **Causal** | Related operations appear in order; unrelated ones may not | Often the sweet spot |
| **Read-your-writes** | *You* always see your own writes; others may lag | Cheap and fixes the most-noticed problem |
| **Eventual** | Replicas converge if writes stop | Cheapest, weakest |

**"Eventually consistent" with no stated bound is not a design.** The useful statement names the
window and who is affected: *"a follower count may lag up to 30 seconds; the account balance never
lags."*

### The classic bug

```mermaid
sequenceDiagram
    participant U as User
    participant P as Primary
    participant R as Replica
    U->>P: POST /url  (create abc123)
    P-->>U: 201 Created
    P-)R: replicate (async, ~200ms)
    U->>R: GET /abc123
    R-->>U: 404 Not Found
    Note over U,R: The user just created it<br/>and the system says it does not exist
```

This is **read-your-writes** being violated, and it is the single most common consistency bug in
systems with read replicas. It is also cheap to fix without going strongly consistent: route a user's
reads to the primary for a short window after they write, or pin them to the replica that has caught
up.

## 5. Engineering at scale

**Consistency costs latency, and physics sets the floor.** Strong consistency across regions means
coordinating over a link with a ~150ms round trip. No implementation improves on that; it is distance.

**Different data in the same product deserves different models.** This is the mature position, and it
is what [PACELC](../cap-theorem/#pacelc) formalises:

| Data | Model | Why |
|---|---|---|
| Payment balance | Strong | Double-spend is unacceptable |
| Inventory count | Strong-ish | Overselling has real cost |
| Follower count | Eventual | Nobody notices or cares |
| Feed / timeline | Eventual | Freshness matters more than exactness |
| Session | Read-your-writes | Users must see their own changes |

Choosing one model for a whole system is a design smell. Choose per dataset.

```mermaid
flowchart LR
    A["<b>Linearizable</b><br/>every read sees the latest write<br/>cost: coordination on every operation<br/><i>payment balance, the last seat</i>"] --> B["<b>Sequential</b><br/>one order, agreed by everyone<br/>cost: ordering, but not real time<br/><i>audit and event logs</i>"]
    B --> C["<b>Causal</b><br/>related operations stay in order<br/>cost: version tracking<br/><i>a comment under its post</i>"]
    C --> D["<b>Read-your-writes</b><br/>you see your own writes, others lag<br/>cost: session pinning<br/><i>profile edits, drafts</i>"]
    D --> E["<b>Eventual</b><br/>converges once writes stop<br/>cost: conflict resolution<br/><i>follower counts, feeds</i>"]

    style A fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
    style E fill:#2a2317,stroke:#d9a441,color:#e4ecea
```

The two tables above describe the same axis from opposite ends, and this is that axis: the models on
one line, the data that belongs at each point on the next. Read it left to right as a price list —
every step right deletes a coordination round trip and hands you back a class of bug to handle in
application code. The italic line is the one that matters here, because a mature product sits at
**several** points at once; a system sitting at exactly one has overpaid on some of its data and
under-protected the rest.

## 7. The problem it does NOT solve

Consistency is about **agreement between copies**, not correctness. A perfectly linearizable system
can store a wrong value — every replica will agree on it. It also does not mean
[durability](../reliability/): all replicas agreeing on data that is then lost is entirely possible.

---

## 13. When you need strong consistency

- Money moving; anything double-spendable
- Uniqueness constraints — usernames, seat reservations, inventory at zero
- Anything where two concurrent readers acting on stale data causes real harm
- Authorisation and permission revocation

## 14. When NOT to

- Counts, likes, view totals — nobody can tell
- Feeds and timelines — freshness beats exactness
- Search indexes — seconds of lag is normal and expected
- Analytics
- **When it would cost availability you need more.** See [CAP](../cap-theorem/).

## 17. Trade-offs

| Choose | Get | Pay |
|---|---|---|
| Strong | Trivial reasoning; no reconciliation code | Latency, reduced availability under partition, no local reads |
| Eventual | Low latency, high availability, local reads | Conflict resolution, stale reads, harder debugging |
| Read-your-writes | Fixes the visible symptom cheaply | Session pinning complexity |
| Causal | Related ops ordered, good latency | More machinery than eventual |

## 18. Why not just use strong consistency everywhere?

| Alternative | Why not | When it WOULD win |
|---|---|---|
| Strong everywhere | Every cross-region write pays ~150ms; system stops on partition | Small dataset, single region, correctness dominates — genuinely common |
| Eventual everywhere | Users see their own writes vanish; conflicts everywhere | Single-writer or append-only data |
| Single node, no replicas | No consistency problem at all — the honest cheapest answer | Data fits one machine and downtime is acceptable |
| Per-dataset choice | Most code and thought | Almost every real product at scale |

That third row matters: **the simplest way to avoid consistency problems is to not have replicas.**
That is a legitimate answer until scale or availability forces otherwise.

## 19. Failure scenarios

| Failure | Effect | Mitigation |
|---|---|---|
| Replication lag spike | Users read stale data; read-your-writes breaks | Route reads to primary after write; monitor lag |
| Network partition | Replicas diverge | Pick A or C deliberately — [CAP](../cap-theorem/) |
| Split brain | Two primaries both accept writes | Quorum, fencing tokens |
| Concurrent conflicting writes | Last-write-wins silently discards one | Vector clocks, CRDTs, or application-level merge |
| Clock skew | Last-write-wins picks the wrong winner | Logical clocks, never wall-clock time |

**Last-write-wins based on wall-clock time is a data-loss mechanism dressed as a conflict-resolution
strategy.** Two servers whose clocks differ by 50ms will silently discard the write that actually
came second.

```mermaid
sequenceDiagram
    participant A as Server A - clock runs 40 ms fast
    participant K as The replica holding the key
    participant B as Server B - clock correct
    A->>K: write OLD. Really at 0 ms. Stamped 40 ms.
    B->>K: write NEW. Really at 30 ms. Stamped 30 ms.
    Note over K: last-write-wins compares the stamps.<br/>40 beats 30, so it keeps OLD.
    Note over A,B: the write that genuinely came second was discarded.<br/>No error was raised and no metric moved.
```

Read the two arrows in the order they are drawn — that is real time — then read the stamps, which
are the only thing the resolver ever sees. The 30 ms between the writes is smaller than the 40 ms of
skew between the clocks, and the moment that is true, last-write-wins is choosing at random. Nothing
on this diagram is a bug in the replica, which is why the defence is a logical clock rather than
tighter time synchronisation.

## 25. Without it → With it → New problem → Next

```
Without it   →  replicas disagree and nobody knows which is right
With it      →  a stated contract about what a read may return
New problem  →  stronger guarantees cost latency and availability
Next         →  CAP and PACELC, which is where that cost gets made explicit
```

## 26. Combination patterns

- **Cache + database** — a cache is a deliberate consistency weakening, with the TTL as the bound
- **Replication + read-your-writes routing** — read scale without the most-noticed bug
- **Sharding + replication** — each shard makes its own consistency choice

## 28. Common mistakes

| Mistake | Why it is wrong |
|---|---|
| "Eventually consistent" with no bound | Not a design; nobody can verify it |
| One model for the whole system | Overpays on some data, under-protects the rest |
| Reading from a replica right after writing | The 404-on-your-own-record bug |
| Wall-clock last-write-wins | Clock skew silently loses writes |
| Assuming a transaction spans services | It does not — that is what sagas are for |
| Treating a cache as consistent | It is a replica with a TTL, and it lies for exactly that long |

## 29. Monitoring

Alert on **replication lag** with a threshold derived from your stated window — if you promised 30s,
alert at 10s. Track stale-read rate where you can detect it. Count conflict resolutions; a rising
count means your assumptions about concurrency are wrong.

## 31. Exercises

**1.** One screen shows a like counter and an account balance. Which consistency model does each get,
and what would you have to write down before shipping either?

<details><summary>Answer</summary>

Eventual for the counter — nobody can tell, and nobody is harmed by a number that is briefly two
low. Strong for the balance, because it is double-spendable. Same screen, same product, two models:
choosing one model for a whole system is a design smell.

What you write down is the **bound**. "Eventually consistent" with no stated window is not a design,
because nobody can verify it or build against it. The useful form names the window and who is
affected: *the like count may lag up to 30 seconds; the balance never lags.*
</details>

**2.** A user creates a post, is shown `201 Created`, immediately loads their own timeline, and it is
empty. What guarantee broke, and what is the cheapest fix?

<details><summary>Answer</summary>

**Read-your-writes.** The write went to the primary; the read went to an asynchronous replica that has
not applied it yet. It is the most common consistency bug in any system with replicas, and it looks
like data loss to the user even though nothing was lost.

The cheap fix is routing that user's reads to the primary for a few seconds after they write, or
pinning the session to a replica known to have caught up. You do not need strong consistency to fix
the visible symptom — see [replication §10](../../05-databases/replication/#10-the-bug-you-will-hit).
</details>

**3.** Two servers write to the same key 30 ms apart. Last-write-wins keeps the *earlier* one. How?

<details><summary>Answer</summary>

Clock skew. Wall-clock last-write-wins compares timestamps generated on different machines, and if
those clocks differ by more than the gap between the writes, the comparison picks the wrong winner
and the later write is silently discarded.

**Wall-clock LWW is a data-loss mechanism dressed as a conflict-resolution strategy.** Use logical
clocks — vector clocks, version vectors — or a CRDT, or an application-level merge rule. And count
conflict resolutions in production: a rising count means your assumptions about concurrency are
wrong.
</details>

**4.** A PM asks for the entire product to be strongly consistent, "to be safe". What do you say?

<details><summary>Answer</summary>

Not a flat no — for a single-region system it is a genuinely common and correct answer, and it
removes an entire class of reconciliation code. Price it honestly first: strong consistency costs a
coordination round trip per operation, which is ~1 ms inside a datacentre and ~150 ms across regions,
and it means the system stops answering during a partition.

Then ask which datasets actually need it, because paying that on the follower count is pure waste.
And note the cheapest answer of all, which people skip: **the simplest way to avoid consistency
problems is not to have replicas.** That is legitimate until scale or availability forces otherwise.
</details>

## 32. Decision checklist

- [ ] Consistency chosen **per dataset**, not per system
- [ ] Every "eventual" has a stated bound, and someone has agreed it
- [ ] Read-your-writes handled wherever users write then read
- [ ] Conflict resolution defined — and not naive wall-clock LWW
- [ ] Replication lag monitored with an alert
- [ ] The partition behaviour is a decision, not an accident

## 33. Related

- [Observability](../../11-observability/) — how you would know any of this broke
- [CAP theorem](../cap-theorem/) — the formal statement of this trade-off ★
- [Availability](../availability/) — the thing consistency is traded against
- [Reliability](../reliability/) — agreement is not correctness
- [Glossary: eventual consistency](../../GLOSSARY.md#eventual-consistency)

<!-- PATH:BEGIN -->

---

<sub>**The reading path** · step 10 of 27 · *Consistency*</sub>

◀ **Previous** [Reliability](../../00-foundations/reliability/README.md) &nbsp;·&nbsp; **Next** [CAP theorem](../../00-foundations/cap-theorem/README.md) ▶

<!-- PATH:END -->
