---
topic: Diagnostic
category: Meta
difficulty: n/a
---

# Diagnostic

`[BEGINNER → EXPERT]` · Seventeen questions, about half an hour. Not a quiz — a router. It tells you which page in this repository to open first.

---

None of these can be answered by recalling a definition. Every one of them is a small piece of
reasoning, usually arithmetic, and the wrong answer is the one that sounds most like the textbook.

**How to use it.** Answer out loud, or on paper, *before* opening the `Answer` fold. Then mark
yourself honestly: you get the point for the reasoning, not for the vocabulary. "It's a CAP
trade-off" is not an answer to anything.

| Tag | Level |
|---|---|
| `[B]` | Beginner — foundations |
| `[I]` | Intermediate — components and their costs |
| `[A]` | Advanced — the interactions |
| `[E]` | Expert — composing several of the above under pressure |

---

## The questions

**1.** `[B]` Your dashboard says average response time is 40 ms and has not moved in a month.
Support has a growing pile of tickets saying the app is slow. Which one is lying?

<details><summary>Answer</summary>

Neither. Latency is a **distribution**, and the mean is the one statistic that hides its shape — a
thousand 20 ms requests bury a handful of 8-second ones and the average barely twitches. The
complaints are coming from the tail, p99 or p99.9, which is precisely the population that files
tickets.

"Latency is 40 ms" is not a claim until it names a percentile. See
[latency §4](00-foundations/latency/#4-technical-explanation).
</details>

**2.** `[B]` You double the app server fleet. Requests per second doubles. p99 does not move at all.
Was the change a success?

<details><summary>Answer</summary>

It depends entirely on which number the complaint was about — and the fact that only one moved is
the **expected** outcome, not a bug. Adding servers buys [throughput](00-foundations/throughput/);
it does not buy [latency](00-foundations/latency/). Nothing you can purchase halves the round trip
to Sydney.

The one case where capacity *does* improve latency is when requests were queueing, because you
removed the queueing term. p99 not moving tells you they were not.
</details>

**3.** `[B]` A request touches three services in series, each independently measured at 99.9%. What
is the availability of the request, and roughly how many hours a year is that?

<details><summary>Answer</summary>

`0.999³ = 99.7%`, which is about **26 hours a year** — roughly three times the downtime of any single
link. Chains multiply, so a chain is always less available than its weakest member; ten dependencies
at 99.9% each give you 99%.

Redundancy in parallel is the opposite arithmetic and adds nines, but only if the failures are
genuinely independent. See
[availability](00-foundations/availability/#components-in-series-multiply).
</details>

**4.** `[B]` You put a load balancer in front of five app servers so that no single machine can take
the site down. How many single points of failure does the system now have?

<details><summary>Answer</summary>

At least one, and probably three. The load balancer itself is one unless it is a redundant pair —
five servers behind one load balancer is a system with the availability of one machine, which is the
most common mistake in the whole topic. DNS is now on the critical path too, and the five servers
almost certainly share one database.

Find the un-redundant component; that is your real number. See
[load balancer §5](03-load-balancing/fundamentals/#5-engineering-at-scale).
</details>

**5.** `[I]` Reads are slow. Access is uniformly random across 40 million keys and the working set
does not fit in memory. Do you add a cache?

<details><summary>Answer</summary>

**No.** A cache is a bet on skew and temporal locality, and this workload has neither. A cache sized
at 20% of the dataset over uniform access returns a 20% hit rate: four reads in five pay the full
cost *plus* a wasted lookup, and you have bought a new component that can take the database down
when it dies.

Fix the query, add the index, or scale up. Also re-measure — "uniformly random" is a claim, and it is
wrong more often than it is right. See [cache §14](04-caching/fundamentals/#14-when-not-to) and the
ordered list in [database §20](05-databases/fundamentals/#20-scaling--in-order).
</details>

**6.** `[I]` A colleague adds retries to every outbound call in the service. What did they just
break?

<details><summary>Answer</summary>

Correctness on every non-idempotent write. A retry cannot distinguish a lost request from a lost
*response*, so "charge the card" quietly becomes "charge the card twice" whenever the timeout fires
after the work succeeded.

Retries need [idempotency](GLOSSARY.md#idempotency) first — a key stored alongside the result, so a
repeat returns the original outcome instead of repeating the effect — plus backoff and jitter, or
the retries themselves finish off the dependency that was merely struggling. See
[reliability §9](00-foundations/reliability/#9-how-it-works).
</details>

**7.** `[I]` A user creates a record, is shown `201 Created`, immediately loads their list of
records, and the list is empty. Nothing is broken. Explain, and give the cheapest fix.

<details><summary>Answer</summary>

The write went to the leader; the read went to an asynchronous follower that has not applied it yet.
The guarantee being violated is **read-your-writes**, and it is the single most common consistency
bug in any system with replicas.

The cheapest fix is not strong consistency — it is routing a user's reads to the leader for a few
seconds after they write. See [replication §10](05-databases/replication/#10-the-bug-you-will-hit).
</details>

**8.** `[I]` You move email sending behind a queue whose vendor advertises exactly-once delivery. A
user reports receiving the same email four times. Who is wrong?

<details><summary>Answer</summary>

Not the vendor — the design, about what that guarantee covers. **Exactly-once does not exist end to
end.** What is sold as exactly-once is at-least-once plus deduplication *inside* the broker's
boundary; the moment an effect leaves that boundary — an SMTP call, a card charge — the ack can be
lost after the work was done, and the message comes back.

Four deliveries means the worker died or timed out after sending and before acking, three times.
The fix is an idempotent consumer, and checking that the ack happens **after** the work is durable
rather than before. See [queue — delivery semantics](06-messaging/queues/#delivery-semantics).
</details>

**9.** `[A]` Your service spans two regions and the link between them fails for 90 seconds. Payments
and the activity feed both live in it. What should the system do?

<details><summary>Answer</summary>

Two different things, because the choice is **per operation, not per system**. Payments should
refuse — CP — since a double spend costs more than 90 seconds of rejected checkouts. The feed should
serve local data — AP — since a stale feed costs nothing and an absent one costs a user. The
question that resolves almost every case: is showing the wrong answer worse, or showing no answer?

Note where the AP bill actually lands: not during the partition but **after it heals**, when
divergent replicas must be merged. If no merge strategy was written down, the default is wall-clock
last-write-wins, which silently discards data. See [CAP](00-foundations/cap-theorem/) and
[PACELC](00-foundations/cap-theorem/#pacelc) for the 99.9% of the time when there is no partition at
all.
</details>

**10.** `[A]` You shard sixteen ways on `hash(tenant_id)`. The hash is uniform and the tenants are
spread evenly across shards. One shard sits at 95% CPU while the rest idle at 10%. What happened?

<details><summary>Answer</summary>

Hashing distributes **keys** evenly. It does not distribute **load**. One tenant ten times the size
of the others, one celebrity account, one product on the front page — it lands on one shard and takes
that shard with it. A perfectly balanced hash gives you a badly balanced system, and this is
sharding's defining failure rather than an edge case.

Every fix costs something: isolate the tenant onto its own shard, put a cache in front of the hot
key, or change the shard key — which is close to permanent and rewrites every row. Note too that an
aggregate CPU dashboard would have read ~15% and told you nothing. See
[sharding §19](05-databases/sharding/#19-failure-scenarios).
</details>

**11.** `[A]` To chase one customer complaint, an engineer adds `user_id` as a label on the HTTP
request metric. The deploy goes out at 14:00. Predict 14:30, and say where that data belonged.

<details><summary>Answer</summary>

The metrics backend runs out of memory and you go blind — plausibly just before the next real
incident. Labels multiply into time series: `{method, status, endpoint}` might be 1,200 series, and
a million user IDs makes that 1.2 billion.

Metric labels must be **bounded**. Per-request identity belongs in logs or traces, which are built
for unbounded cardinality and pay for it with sampling and retention limits. That the observability
system dies exactly when it is needed is also why its path should not share fate with the system it
watches. See [the cardinality trap](11-observability/#the-cardinality-trap).
</details>

**12.** `[E]` A worker fleet drains a queue and writes to the same primary database that serves user
traffic. Autoscaling is keyed on queue depth, which is correct. A dependency outage builds a
two-hour backlog. The dependency recovers, the fleet scales up to drain — and the *website* goes
down. Walk the mechanism, then say what you would change.

<details><summary>Answer</summary>

Four things compose, and each was individually reasonable:

1. Moving work behind a [queue](06-messaging/queues/#5-engineering-at-scale) removed the natural
   backpressure the request path had. On the request path a slow database slows the client, which
   throttles arrival. Behind a queue nothing pushes back — workers pull as fast as they are able.
2. Depth is the right autoscaling signal, and it is also what aims the fleet at the database. Depth
   is enormous, so the policy adds workers until it is not. The fleet is now sized by the backlog
   rather than by anything downstream can absorb.
3. The number that decides the outcome is **fleet concurrency** — workers × per-worker concurrency —
   and nobody set it. Twenty workers at concurrency 50 is a thousand simultaneous operations. See
   [worker §5](06-messaging/workers/#5-engineering-at-scale).
4. The connection pool is shared with the request path, so it exhausts and the site returns errors
   while the database itself sits comfortably idle. That symptom is
   [in the table](05-databases/fundamentals/#19-failure-scenarios) and is routinely misread as a
   database problem.

**What to change:** bound total fleet concurrency against measured downstream capacity and cap the
autoscaler's maximum to respect it; give workers their own connection pool so neither workload can
starve the other; and accept that the drain now takes longer, because the backlog has no user
waiting on it and the website does.

The general shape is worth more than the fix: **a queue does not add capacity, it moves the moment
you pay for the shortfall.** Two correct components, one bad interaction — which is what the
[combination matrix](14-component-combinations/MATRIX.md) is for.
</details>

---

**13.** `[I]` A colleague says your API is safe because every endpoint checks that the caller is
logged in. You change `GET /invoices/8814` to `GET /invoices/8815` and get someone else's invoice.
What was checked, and what was not?

<details><summary>Answer</summary>

Authentication was checked; **authorization was not**. The endpoint confirmed *who you are* and never
asked whether you are allowed *this object*. Those are two different questions and conflating them is
the most common real API vulnerability there is — IDOR, or BOLA in the API-specific naming.

The fix is not another gate at the edge. The ownership check has to happen where the object is
loaded, because that is the only place that knows which object was asked for. See
[api-security](12-security/api-security/).
</details>

**14.** `[I]` You issue JWTs with a 24-hour expiry. An account is compromised at 09:00 and you
disable it at 09:05. When does the attacker's token stop working?

<details><summary>Answer</summary>

**At 09:00 tomorrow.** A JWT is validated by checking a signature, and nothing in that check consults
your database — which is exactly the property people choose JWTs for. Disabling the account changes
state the token never reads.

Every fix reintroduces the server state you were trying to avoid: a short expiry plus refresh tokens
narrows the window, a denylist closes it and costs a lookup per request. There is no version of this
where you keep statelessness and get revocation. See [jwt](12-security/jwt/).
</details>

**15.** `[I]` `GET /orders?limit=20&offset=40` powers an infinite scroll. Orders arrive constantly.
A user scrolls steadily and complains about seeing the same order twice. Is that a bug in your code?

<details><summary>Answer</summary>

It is a bug in **offset pagination**, and your code is probably faithful to it. Each page is a fresh
query against a table that has changed since the last one. Three new orders inserted at the head push
everything down three rows, so rows that were at offsets 38–40 slide to 41–43 and get returned again.

Delete rows instead of inserting and the same mechanism **silently skips** records, which is worse —
a duplicate is visible to a client that de-duplicates by id, a skip is simply gone. Cursor pagination
exists for this. It is invisible in testing because test fixtures do not move. See
[pagination](07-api-design/pagination/).
</details>

**16.** `[A]` Six engineers. The team proposes splitting the monolith into eight services to "scale
better". Throughput is fine; deploys are slow because everything ships together. Good idea?

<details><summary>Answer</summary>

No — or at least, not for that reason. Microservices are an **organisational** solution to a
team-scaling problem, not a technical solution to a performance one, and the stated problem is
deploy coupling rather than throughput.

Six people cannot operate eight services: eight pipelines, eight on-call surfaces, and availability
that now **multiplies** down every synchronous call. The intermediate step is a modular monolith with
enforced internal boundaries, which fixes coupling without buying a distributed system. Split later,
along the seams that hurt, if they ever do. See
[monolith vs microservices](02-architecture/monolith-vs-microservices/).
</details>

**17.** `[A]` You lower a DNS record's TTL from 3600 to 60 as part of a failover plan, then fail over.
Some users still reach the dead region twenty minutes later. Why?

<details><summary>Answer</summary>

Because the **old** TTL governs everything already cached. A resolver that fetched the record at
3600 seconds holds it for up to an hour regardless of what you publish afterwards — the reduction
only applies to lookups made after it propagates. Lowering the TTL is something you do *days* before
a planned failover, not during one.

And that is only the resolvers you can reason about. Some clients and libraries cache DNS for the
process lifetime and ignore TTL entirely. **DNS TTL is a floor on your real recovery time, not the
value of it.** See [dns](01-networking/dns/).
</details>

## Scoring

One point per question where you had the **reasoning**. No points for the label: "it's a CAP
trade-off", "you'd use a cache", "p99" with no account of why the average could not have told you.

| Score | What it means | Start here |
|---|---|---|
| **0–6** | The vocabulary is probably there; the arithmetic is not. This is the normal starting point and it is a good one, because foundations are the cheapest thing in this repository to fix. | [00-foundations/](00-foundations/), in order. Do not skip [availability](00-foundations/availability/) — the multiplying is where most intuition fails. Then [SYSTEM-DESIGN-THINKING.md](SYSTEM-DESIGN-THINKING.md) for the method, and [ESTIMATION-GUIDE.md](ESTIMATION-GUIDE.md) for putting numbers on a problem. |
| **7–11** | Foundations are solid. You know what the components are and are still learning what each one **costs**. | The component pages: [load balancer](03-load-balancing/fundamentals/), [cache](04-caching/fundamentals/), [database](05-databases/fundamentals/), [queue](06-messaging/queues/). Read each page's **§14 When NOT to** and **§19 Failure scenarios** first — that half is what most material omits, and it is where questions 5 and 8 came from. |
| **12–17** | Individual components are not your problem any more. Your remaining gaps are in how they behave **together**, which no single-component page can teach. | The [combination matrix](14-component-combinations/MATRIX.md) — all 153 pairs, including the ones that amplify each other — then the worked problem, [URL shortener V1→V8](15-real-world-problems/url-shortener/), which is the whole chain applied end to end. Then the sections that assume all of the above: [security](12-security/), [API design](07-api-design/), [architecture](02-architecture/) and [networking](01-networking/). Finish with [GAPS.md](GAPS.md), so you know what this repository deliberately does not cover. |

**A missed question is worth more than the score.** Each one maps to exactly one page:

| # | What it tests | Page |
|---|---|---|
| 1 | Latency percentiles | [latency](00-foundations/latency/) |
| 2 | Throughput versus latency | [throughput](00-foundations/throughput/) |
| 3 | Availability chains | [availability](00-foundations/availability/) |
| 4 | Load balancer as a new SPOF | [load balancer](03-load-balancing/fundamentals/) |
| 5 | Caching is a bet on skew | [cache](04-caching/fundamentals/) |
| 6 | Retries need idempotency | [reliability](00-foundations/reliability/) |
| 7 | Replication lag, read-your-writes | [replication](05-databases/replication/) |
| 8 | At-least-once delivery | [queue](06-messaging/queues/) |
| 9 | CAP per operation, and PACELC | [CAP theorem](00-foundations/cap-theorem/) · [consistency](00-foundations/consistency/) |
| 10 | Hot shards | [sharding](05-databases/sharding/) |
| 11 | Metric cardinality | [observability](11-observability/) |
| 12 | Composition, and lost backpressure | [queue](06-messaging/queues/) · [workers](06-messaging/workers/) · [matrix](14-component-combinations/MATRIX.md) |
| 13 | Authentication is not authorization | [api-security](12-security/api-security/) |
| 14 | A JWT cannot be revoked before expiry | [jwt](12-security/jwt/) |
| 15 | Offset pagination skips and duplicates | [pagination](07-api-design/pagination/) |
| 16 | Microservices are an org solution | [monolith vs microservices](02-architecture/monolith-vs-microservices/) |
| 17 | The old DNS TTL governs what is cached | [dns](01-networking/dns/) |

A caveat on a perfect score: every question here has one right answer and production does not.
Twelve out of twelve means you are ready for the [combinations](14-component-combinations/MATRIX.md)
and the [judgement](TRADEOFF-FRAMEWORK.md) material, not that the reading is finished.

**Preparing for an interview rather than learning?** The [question bank](20-system-design-interview/) is the same material asked the way an interviewer asks it — 46 questions with their follow-up chains, and what each one is actually probing.

## Related

- [README](README.md) — the map, and the reading order this feeds into
- [System design thinking](SYSTEM-DESIGN-THINKING.md) — the chain, and the 18-step method
- [Trade-off framework](TRADEOFF-FRAMEWORK.md) — how to choose, once you know the costs
- [Design checklist](DESIGN-CHECKLIST.md) — the 45-minute short form
- [Glossary](GLOSSARY.md) — every term used above, defined once
- Each concept page ends with a **§31 Exercises** section in this same format
