---
topic: ADR-0002 Queue for click analytics
category: Judgment
difficulty: Intermediate
---

# ADR-0002: Move click counting off the redirect path onto a log

- **Status** — Accepted
- **Date** — 2025-08
- **Deciders** — Backend lead · Analytics owner · Product owner, who owns the freshness SLO · SRE on call

## Context

The [URL shortener](../15-real-world-problems/url-shortener/) is approaching **1 billion redirects a
day** — about 11,600 requests per second on average and roughly **35,000 at peak**. The cache from
[ADR-0001](0001-cache-before-replicas.md) absorbs about 95% of the lookups.

We serve **302, not 301**, and that was a deliberate choice: a 301 would be cached by browsers and
most repeat clicks would never reach us, which is a large traffic saving and destroys the click data
that the product is sold on. Having paid for every click to arrive at our servers, we then have to do
something with each one.

Today the redirect handler does this before writing the `Location` header:

```
UPDATE clicks SET n = n + 1 WHERE code = ?
```

At peak that is 35,000 writes per second, and because access is skewed 92% toward the top 0.1% of
codes, a large share of those writes contend on **the same row**. The redirect path — the most
trafficked endpoint in the system, and the one with the tightest latency budget — now contains a
row-level lock on the hottest row in the database.

Nobody has ever asked how fresh a click counter needs to be.

## Problem

Three separate problems wear the same clothes here, and only naming them separately makes the
decision obvious.

1. **Latency.** A database write sits inside a read path with a 100 ms p99 budget, and the write is
   the slowest thing in it.
2. **Availability.** Analytics availability is now a term in redirect availability. If the counter
   table is slow, redirects are slow. If it is down, redirects fail. The most valuable path in the
   system depends on the least valuable one.
3. **Contention.** The hot-key skew that makes the cache work makes the counter worse: the more
   popular a link, the more concurrent writers fight over one row.

And a fourth thing that is not a problem but a missing requirement: **no freshness target has ever
been stated**, so every conversation about this defaults to "real time", which is the most expensive
possible answer and one nobody has priced.

## Decision

Take click counting off the request path.

- The redirect handler writes the `Location` header first, then emits a **click event** to a durable
  **log** — a retained, replayable, partitioned stream — and returns. The emit is fire-and-forget
  into a bounded local buffer with a **hard bound**; if the buffer is full, the event is **dropped
  and counted**, and the redirect still succeeds.
- A **worker pool** consumes the log, aggregates in memory over short windows, and writes batched
  counter updates. One row update per code per window, not per click.
- **Freshness SLO: counters are at most 60 seconds behind.** Written down, agreed with product, and
  alerted on. This is the number the decision buys, and stating it is half the value of the record.
- Events carry a **UUID** so aggregation can deduplicate, because delivery is at-least-once.
- Partition key is the **short code**, so all events for one link land in order on one partition.

**A log, not a delete-on-read queue.** The deciding question is
[will you ever want the data twice](../comparisons/kafka-vs-rabbitmq.md), and the answer here is
certainly yes: a bug in the aggregator on Tuesday is fixable by replaying from Monday's offset, and
the raw click stream will be wanted for geography, referrer and fraud analysis that nobody has
specified yet. A queue would have deleted it.

This lands in the same increment as [ADR-0003](0003-shard-by-user-id.md), and it ships **first**,
deliberately: this decision is nearly reversible and the shard key is nearly permanent.

## Alternatives considered

| Option | Why not | When it would win |
|---|---|---|
| **Keep the synchronous update** | Puts a contended write on the hot path of the most trafficked endpoint, and makes a counter failure a redirect failure | The counter is the product's source of truth for money, and the traffic is low enough that contention is theoretical |
| **In-process buffer, flush every 10 s, no broker** | Genuinely tempting: zero new components, most of the latency benefit. But a process restart loses the buffer, autoscaling loses it routinely, and **there is no raw stream to replay** | Advisory counters at moderate scale where losing a few seconds on deploy is fine and nobody will ever want the raw events. A real answer for a smaller system |
| **A delete-on-read queue instead of a log** | Solves the latency and availability problems identically and throws the events away after one consumer reads them. No replay, no second consumer | You are certain there is exactly one consumer forever and reprocessing is never needed. Rarely true of anything called an *event* |
| **Increment a counter in the cache, flush periodically** | Fast and simple, and it is a write-behind cache — **the one strategy that can lose acknowledged data.** For a counter that may be acceptable; the problem is that it hides that choice inside an existing component | Counters that are explicitly disposable and where you already run the cache. Never for anything a customer is billed on |
| **Derive counts from load-balancer access logs** | Zero code on the hot path, which is the strongest argument any option here has. But the log pipeline has its own lag, entries are sampled, and we lose fields the application knows and the LB does not | Coarse aggregate counts only, and you already ship and retain structured access logs |
| **Sample: count 1 in 10 and multiply** | Cheap and statistically fine in aggregate — but wrong for the long tail, which is most codes. A link with 7 clicks reports 0 or 10 | High-volume aggregate reporting where per-link accuracy does not matter |
| **Do nothing** | The redirect path keeps a contended write on it, and the next traffic step makes it the bottleneck. There is no version of this that improves on its own | If click data were not the product. Then the honest move is to switch to 301, delete the counter entirely, and shed most of the traffic — a strictly better outcome that this product cannot have |

## Trade-offs

| Get | Pay |
|---|---|
| A database write leaves the p99 path of the busiest endpoint | An extra component: a broker, a consumer fleet, a DLQ, and a place in the on-call rotation |
| Analytics failure no longer affects redirects — the availability term is removed, not merely reduced | Counters are **eventual**. The dashboard is up to 60 s behind, forever, by design |
| Row contention collapses: one batched update per code per window, not one per click | At-least-once delivery means **duplicates**, so aggregation must deduplicate or accept over-counting |
| A replayable raw stream we do not yet know all the uses for | Retention costs storage, and raw click data is personal data with a retention policy attached |
| Spikes become backlog rather than errors — a televised link no longer threatens the counter table | The buffer can only absorb a spike, never a sustained deficit. Consumers must keep up **on average** or depth grows without bound |
| Batching raises throughput substantially | Batching raises per-event latency, and one poison event can force a batch of a thousand to be reprocessed |

## Consequences

**The design's failure table can now say something it could not before:** if the analytics pipeline
dies, redirects are *completely unaffected* and counters simply stop. That row is the whole reason
this work was done, and it is worth noticing that the benefit is an **availability** benefit that
arrived disguised as a latency change.

**Counter correctness is now an eventual, deduplicated, at-least-once problem** rather than a
transactional one. Aggregation must be idempotent on the event UUID; if it is not, every redelivery
inflates the number a customer sees. This makes [idempotency](../07-api-design/idempotency/) a
correctness requirement of the analytics path rather than a nice-to-have.

**We have taken on a new class of silent failure.** Before this change, a broken counter meant an
error on the redirect — loud, immediate, obvious. Now a broken consumer means the dashboard is
*wrong* rather than *empty*, and a plausible-looking wrong number is the second-worst failure a system
can produce, behind only losing data outright. Monitoring must therefore watch consumer lag and
throughput, not just error rates: a consumer that has silently stopped produces no errors at all.

**The queue removes the natural backpressure the database used to have.** On the synchronous path, a
slow counter table slowed the redirect, which slowed arrivals. Behind a log, workers write at their
own pace with nothing pushing back, and can generate write load a synchronous path could never have
produced. A concurrency cap on the worker pool is not optional — see
[queue without backpressure](../anti-patterns/queue-without-backpressure/).

## Failure modes this introduces

| Failure | What it looks like | Mitigation, or "accepted" |
|---|---|---|
| **Consumers fall behind permanently** | Depth grows linearly, counters drift hours behind, and the broker eventually runs out of disk | Autoscale consumers on **depth**, not CPU. Alert on **age** as well as depth: 10 events three hours old is a worse signal than 10,000 one second old |
| **Duplicate counting** | At-least-once redelivery inflates numbers after any consumer restart | Deduplicate on event UUID within the aggregation window. Cross-window duplicates are accepted as a fraction of a percent |
| **Poison event** | One malformed event blocks its partition and stalls every code that hashes to it | Delivery cap then DLQ, with an alert on DLQ depth. A blocked partition is a stalled subset of links, which is harder to notice than a full stall |
| **Hot partition** | A televised link sends every one of its events to the same partition. The skew that helps the cache hurts here | Accepted at current scale — a single partition handles the volume. If it fires: salt the partition key for the top N codes and merge on aggregation |
| **Silent consumer death** | Counters simply stop advancing. No errors anywhere | Alert on consumer lag and on **counter staleness measured from the dashboard's side**, which is the only check that tests the whole chain |
| **Workers overwhelm the analytics database** | Backpressure the synchronous path used to provide is gone | Hard concurrency limit on the pool, and batch sizes tuned against the database rather than the broker |
| **Buffer drop during a spike** | Events discarded at the emit point, so counts are quietly low | Counted and exported as a metric, so the loss is visible. Accepted: a dropped click is better than a failed redirect, and that ordering is the point of the whole design |

## Revisit when

| Trigger | Measured how | Threshold |
|---|---|---|
| **Counters become billing-grade** | Any product decision that charges an advertiser per click, or exposes counts in a contract | Any. "A few seconds of lag and a fraction of a percent of duplicates" is fine for a dashboard and unacceptable for an invoice. That needs a ledger, reconciliation and an audit trail — **supersede this record, do not patch it** |
| **The freshness SLO is not met** | Consumer lag, p99, weekly | Above **60 s** for a week. Either scale the consumers or renegotiate the SLO with product — but do not let the stated number quietly become fiction |
| **Sub-second dashboards are required** | An approved product requirement for live per-click updates | Any. That is a streaming-aggregation and push architecture, not this one |
| **Duplicate rate becomes visible to customers** | Support tickets referencing count discrepancies, plus measured duplicate ratio | Above **0.5%**, or any customer-reported discrepancy. Deduplication scope must widen |
| **The product stops selling click data** | A move to 301, or the analytics feature being retired | Any — and this is the cheapest revisit of all, because the answer is to **delete the pipeline** and shed most of the traffic with it. Deletion is an outcome an ADR should make it easy to reach |
| **Broker operational cost exceeds the value of the counters** | Monthly infrastructure and on-call cost against analytics revenue | Cost exceeds value. Fall back to the in-process buffer option, which was second on the list for a reason |

**What does not reopen this:** a PM asking for the number to be "exact and real-time" without a
stated business cost — the answer is the 60 s SLO and a question about what exact is worth. Nor does
a single incident in the pipeline: the failure table above predicted it, redirects were unaffected,
and that is the design working.

---

## Related

- [Queue](../06-messaging/queues/) — queue versus log, delivery semantics, and why depth alone is not an alert
- [Workers](../06-messaging/workers/) — the consumer side, concurrency limits and poison messages
- [Kafka vs RabbitMQ](../comparisons/kafka-vs-rabbitmq.md) — will you ever want the data twice
- [Idempotency](../07-api-design/idempotency/) — why at-least-once makes deduplication a correctness requirement
- [Anti-pattern: queue without backpressure](../anti-patterns/queue-without-backpressure/) — the failure this record is one alert away from
- [URL shortener](../15-real-world-problems/url-shortener/) — V6 of the worked design
- [ADR index](README.md) · [Glossary](../GLOSSARY.md)
