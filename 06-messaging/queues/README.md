---
topic: Queue
category: Components
difficulty: Intermediate
concepts: [async, idempotency, backpressure, delivery-semantics]
related: [worker, backpressure, retries, database]
---

# Queue ★

`[INTERMEDIATE]` · Decouples arrival rate from processing rate, so a spike becomes a backlog instead of an outage. Buys at-least-once delivery — which makes idempotency mandatory, not optional.

---

## 1. One-line definition

A durable buffer that holds work between the thing producing it and the thing doing it.

## 2. Explain like I'm new

A restaurant where waiters clip orders to a rail and cooks take them off. Waiters never wait for
cooking to finish, so a sudden rush of customers produces a **longer rail**, not a jammed dining room.

Three things follow immediately, and they are the three things every queue has: the diner is told
"ordered", not "cooked" — the result is now *eventual*. If the rail fills faster than cooks empty it,
you are still in trouble, just later. And if a cook drops an order on the floor, someone must notice
and re-clip it — which is how the same meal ends up cooked twice.

## 3. Real-world analogy

The order rail above.

**Where it breaks:** a physical ticket exists once. A message can be delivered twice, arrive out of
order, or arrive after the cook has gone home and come back. None of those have a kitchen analogue,
and all three are routine.

## 4. Technical explanation

**A queue is not a stream, and confusing them is expensive.** They look similar and behave
differently:

| | **Queue** | **Stream / log** |
|---|---|---|
| After consumption | Message is deleted | Retained for a period |
| Consumers | One consumer gets each message | Many independent consumers, each with an offset |
| Replay | Impossible — it is gone | Reset the offset and reprocess |
| Ordering | Usually best-effort | Ordered within a partition |
| Scaling | Add workers to one queue | Add partitions |
| Examples | SQS, RabbitMQ | Kafka, Kinesis, Redis Streams |

**Pick a stream when you might want the data twice.** A bug found on Tuesday can be fixed by
replaying from Monday's offset — with a queue, the messages are gone and the data is unrecoverable.
That single property justifies a log for anything resembling an event.

### Delivery semantics

| Guarantee | Reality |
|---|---|
| At-most-once | Fire and forget. Fast, loses messages. Rarely what you want. |
| **At-least-once** | **What you actually get.** Duplicates are possible. Requires idempotency. |
| Exactly-once | Does not exist end-to-end. What is sold as exactly-once is at-least-once plus deduplication, inside a system boundary. |

The practical rule: **assume at-least-once and make every consumer idempotent.** Designs that depend
on exactly-once are depending on something that is not there.

## 5. Engineering at scale

**A queue does not add capacity; it defers work.** If producers sustainably outpace consumers, the
queue grows without bound until memory or disk runs out, and you have converted a slowdown into an
outage. The queue buys time to absorb a *spike*, not a permanent deficit. That is what
[backpressure](../../GLOSSARY.md#backpressure) is for.

**The queue removes natural backpressure from the database.** On the request path, a slow database
slows the client, which throttles arrival. Behind a queue, workers hammer the database at their own
pace with nothing pushing back. A common failure is a batch job that a synchronous path would never
have been able to generate.

**Queue depth is the best autoscaling signal you have.** CPU tells you about the workers; depth tells
you whether you are keeping up. Scaling on CPU for queue consumers is a standard mistake.

## 6. The problem it solves

Slow or unreliable work on the request path — and load spikes that would otherwise exceed capacity.

## 7. The problem it does NOT solve

It does not make the work faster. It does not add throughput. It does not remove the need for the
downstream system to be able to keep up on average. And **it does not preserve order** unless you
have specifically arranged for it — which usually costs you parallelism.

## 8. Why does this exist?

Because coupling the speed of the producer to the speed of the consumer means the slowest component
sets the pace for everyone. A buffer breaks that coupling — the same reason buffers exist everywhere
from CPU pipelines to shipping ports.

---

## 9. How it works

```mermaid
flowchart LR
    P[Producer] -->|"1 · enqueue"| Q[Queue]
    Q -->|"2 · receive<br/>(invisible to others)"| W[Worker]
    W -->|"3 · process"| D[(Database)]
    W -->|"4 · ack — delete"| Q
    Q -.->|"no ack before timeout<br/>→ redelivered"| W
    Q -->|"after N attempts"| DLQ[Dead Letter Queue]

    style DLQ fill:#2a2317,stroke:#d9a441,color:#e4ecea
```

The mechanism that makes it durable is **ack-after-processing**. Receiving a message makes it
invisible to other workers for a visibility timeout, but does not delete it. Only the ack deletes it.
So a worker crashing between steps 2 and 4 causes the message to reappear and be processed again —
which is exactly why at-least-once is what you get, and exactly why idempotency is required.

**Acking before processing turns at-least-once into at-most-once** and silently loses work on every
crash. It is a one-line change and a data-loss bug.

## 10. Internal components

- **Durable store** — messages must survive a broker restart
- **Visibility timeout / lease** — how long a worker has before redelivery
- **Delivery counter** — how many attempts, so poison messages can be capped
- **Dead letter queue** — where messages go after the cap
- **Ack / nack** — completion signal

## 11. The dead letter queue

Without a delivery cap, a message that can never succeed retries forever. If ordering is enforced, it
blocks everything behind it — one malformed message stops the entire pipeline.

A DLQ makes the failure visible and bounded. **A DLQ nobody monitors is a data-loss mechanism with
extra steps**, so the alert on DLQ depth matters more than the DLQ itself.

## 12. Ordering

Global ordering and parallel consumption are mutually exclusive. The standard compromise is
**ordering within a partition key**: all messages for user 42 go to the same partition and are
processed in order, while different users proceed in parallel.

Choose the key so that ordering is preserved where it matters and parallelism survives everywhere
else. A key with poor distribution recreates the single-consumer bottleneck.

---

## 13. When to use it

- The work is not needed for the response — email, thumbnails, analytics, indexing
- Load is spiky and you want to absorb peaks with fewer machines
- The downstream system is unreliable and you want retries handled centrally
- Fan-out: one event, several independent consumers (prefer a **stream** here)

## 14. When NOT to

- **The user needs the result now.** A queue makes the answer eventual; if a human is waiting for it,
  you have made the experience worse.
- Consumers cannot keep up on average. The queue only defers the problem.
- The operation is not idempotent and you cannot make it so.
- Strict global ordering is required and volume is high.
- **When a synchronous call would do.** A queue is a distributed system's worth of complexity — two
  more failure modes, a broker to run — for work that finishes in 5ms.

## 17. Trade-offs

| Choose | Get | Pay |
|---|---|---|
| Queue | Responsiveness, spike absorption, retry in one place | Eventual results; duplicates; ordering; a broker to run |
| Stream over queue | Replay, multiple consumers | Retention cost, offset management |
| Larger visibility timeout | Fewer spurious redeliveries | Slower recovery from a crashed worker |
| Ordering by key | Order where it matters | Parallelism capped by key distribution |
| Bigger batch | Throughput | Latency; a failure retries the whole batch |

## 18. Why not?

| Alternative | Why not here | When it WOULD win |
|---|---|---|
| **Synchronous call** | Couples you to the callee's latency and availability | The work is fast and the caller needs the result — **the common case** |
| A database table as a queue | Polling, lock contention, no built-in DLQ | Low volume, and you already have the database — genuinely fine at small scale |
| Cron / batch job | High latency, poor failure isolation | Work that is genuinely periodic |
| Stream (Kafka) instead | Heavier to operate | You need replay or multiple consumers |
| In-memory queue | **Loses everything on restart** | Work that is genuinely disposable |

That second row is worth taking seriously. `SELECT ... FOR UPDATE SKIP LOCKED` on a Postgres table is
a perfectly good queue up to a few thousand jobs a second, and it removes an entire component from
your architecture.

## 19. Failure scenarios

| Failure | What happens | Mitigation |
|---|---|---|
| Worker crashes mid-job | Message redelivered; work may be **half-applied** | Idempotency; transactional processing |
| Message delivered twice | Duplicate side effects — double charge, double email | Idempotency keys |
| Poison message | Retries forever; blocks the partition if ordered | Delivery cap → DLQ |
| Queue grows unboundedly | Memory/disk exhaustion; a slowdown becomes an outage | Backpressure; alert on depth *and* age |
| Consumers outpaced permanently | Latency grows without limit | Autoscale on depth; shed load |
| Broker down | Producers block or drop | Broker redundancy; local buffering with a bound |
| Out-of-order arrival | Inconsistent state | Partition keys; sequence numbers; order-independent design |
| **Ack before processing** | Silent data loss on every crash | Ack only after the work is durable |
| Workers overwhelm the database | The queue removed natural backpressure | Concurrency limit on the worker pool |

**Alert on message *age*, not only depth.** A queue with 10 messages that are three hours old is a
worse signal than a queue with 10,000 messages one second old, and a depth-only alert misses it
entirely.

## 21. Performance

The win is in *perceived* latency: the user's request returns as soon as the message is durable,
typically a few milliseconds, instead of waiting for work that might take seconds. Total work is
unchanged — slightly increased, in fact, by serialisation and the extra round trip.

Batching raises throughput and worsens per-item latency, exactly as in
[throughput](../../00-foundations/throughput/). Batch failures are the subtlety: with a batch of 100,
one poison message can cause the other 99 to be reprocessed.

---

## 25. Without it → With it → New problem → Next

```
Without it   →  slow work blocks the response; a traffic spike exceeds capacity
With it      →  responses return immediately; spikes become backlog
New problem  →  at-least-once delivery means duplicates; results are eventual;
                ordering is no longer free; the queue itself can grow unboundedly
Next         →  idempotency to make redelivery safe, a DLQ for poison messages,
                and backpressure so the buffer cannot become the outage
```

## 26. Combination patterns

- **[Queue + workers](../../14-component-combinations/MATRIX.md)** — the core async pipeline
- **[Queue + database](../../14-component-combinations/MATRIX.md)** — the dual-write problem; the outbox is the answer
- **[Cache + queue](../../14-component-combinations/MATRIX.md)** — ⚠ a miss storm and a backlog amplify each other
- **[Breaker + queue](../../14-component-combinations/MATRIX.md)** — park work instead of dropping it when the breaker opens
- **[Worker + object storage](../../14-component-combinations/MATRIX.md)** — claim-check: the message carries a pointer, not the payload

## 27. Implementation

A message queue with visibility timeouts and a DLQ is on the roadmap for
[18-implementations/](../../18-implementations/). The
[rate limiter](../../18-implementations/rate-limiter/) shows the standard these follow: real
measurements, and an explicit list of what production adds.

## 28. Common mistakes

| Mistake | Why it is wrong |
|---|---|
| **Ack before processing** | Turns at-least-once into at-most-once. Silent loss. |
| No idempotency | Duplicates become double charges |
| No DLQ | One poison message blocks the pipeline forever |
| No alert on queue age | Depth alone misses a stalled consumer |
| Assuming exactly-once | It does not exist end-to-end |
| Assuming ordering | Not guaranteed unless arranged, and it costs parallelism |
| Autoscaling on CPU | Depth is the correct signal for consumers |
| Unbounded workers | They overwhelm a database the request path protected |
| Queue where sync would do | A broker and two failure modes for 5ms of work |
| Queue instead of capacity | Defers the problem; does not solve it |

## 29. Monitoring

Depth **and oldest-message age** — the second catches stalled consumers the first cannot see. DLQ
depth with an alert at anything above zero, because a message there is work that silently did not
happen. Processing rate against arrival rate: if arrival exceeds processing for a sustained period,
the outage is already scheduled. Redelivery count, which is a direct measure of how often workers are
failing mid-job.

## 31. Interview questions

- **"Queue or stream?"** — wants replay and multi-consumer, not a product comparison.
- **"Exactly-once delivery — how?"** — the right answer starts with "you cannot, end to end".
- **"A worker crashes halfway. What happens?"** — wants redelivery, and idempotency as the fix.
- **"The queue is growing. What do you do?"** — wants: is this a spike or a deficit? Autoscale for
  the first; shed load or add capacity for the second.
- **"How do you guarantee ordering?"** — wants partition keys, and the parallelism cost.
- **"What breaks when you move work behind a queue?"** — the best question here. Wants: results
  become eventual, and the database loses its natural backpressure.

## 32. Decision checklist

- [ ] The user genuinely does not need the result synchronously
- [ ] Every consumer is idempotent
- [ ] Ack happens **after** the work is durable
- [ ] Delivery cap and DLQ configured; DLQ depth alerted
- [ ] Alert on message age, not only depth
- [ ] Ordering requirement stated; partition key chosen if needed
- [ ] Worker concurrency bounded so the database is protected
- [ ] Autoscaling keyed on queue depth
- [ ] Consumers can keep up on *average*, not just at trough

## 33. Related

- [Throughput](../../00-foundations/throughput/) — arrival rate versus processing rate
- [Reliability](../../00-foundations/reliability/) — idempotency, retries, DLQ
- [Database](../../05-databases/fundamentals/) — the dual-write problem
- [Combination matrix](../../14-component-combinations/MATRIX.md)
- [Glossary: idempotency](../../GLOSSARY.md#idempotency) · [backpressure](../../GLOSSARY.md#backpressure)
