---
topic: Reliability
category: Foundations
difficulty: Beginner
concepts: [durability, correctness, fault-tolerance]
related: [availability, consistency]
---

# Reliability

`[BEGINNER]` · Doing the **right** thing, consistently, including when parts are broken. Availability is being up; reliability is being correct.

---

## 1. One-line definition

The probability that the system performs its function correctly over a period of time.

## 2. Explain like I'm new

A cash machine that is always switched on is **available**. A cash machine that always dispenses the
right amount and always debits the right account is **reliable**.

You want both, but if you can only have one, everybody wants the second. A bank that is briefly
closed survives; a bank that loses your money does not.

## 3. Real-world analogy

An airliner: it has redundant systems not so it can fly *more often*, but so that a single failure
never produces a wrong outcome.

**Where it breaks:** aircraft redundancy is physically independent. Software "redundancy" often shares
a code path, so the same bug fails in all copies simultaneously. Redundancy defends against random
failure, never against a logic error.

## 4. Technical explanation

Reliability decomposes into three properties that are frequently confused:

| Property | Question | Failure looks like |
|---|---|---|
| **Availability** | Does it respond? | Timeout, 503 |
| **Correctness** | Is the answer right? | Wrong balance, missing record |
| **Durability** | Does committed data survive? | Data loss after a crash |

A system can score perfectly on one and fail the others. Ranked by how bad the failure is:

```
data loss  >  silent wrong answer  >  loud failure  >  slow  >  fine
```

**A loud failure is better than a silent wrong answer**, because a loud failure can be retried and a
wrong answer propagates. This ordering should drive your design: prefer to fail visibly.

Standard measures: **MTBF** (mean time between failures), **MTTR** (mean time to recovery).
Reducing MTTR is almost always cheaper than increasing MTBF — you cannot prevent every failure, but
you can always recover faster.

## 5. Engineering at scale

**At scale, rare becomes constant.** A disk with a 1-in-100,000-per-hour failure rate is effectively
reliable — until you have 10,000 of them, at which point one fails roughly every 10 hours. Everything
that can fail, does, continuously. Designs must assume it rather than hope.

**Idempotency is the load-bearing property.** Once you retry — and you will — every operation must be
safe to apply twice, or your reliability work actively creates corruption.

## 6. The problem it solves

Ensures the system produces correct outcomes despite component failures, which are guaranteed.

## 7. The problem it does NOT solve

Reliability engineering does not fix bugs. Retries, replicas and failover all faithfully reproduce a
logic error across every copy. **Redundancy protects against random failure, not against being wrong.**

---

## 9. How it works

Four mechanisms, roughly in order of how much they buy:

1. **Idempotency** — operations safe to repeat. Everything else depends on this.
2. **Retries with backoff and jitter** — survive transient faults without becoming a retry storm.
3. **Timeouts and circuit breakers** — stop a slow dependency from taking you with it.
4. **Redundancy and replication** — survive the loss of a machine or a disk.

```mermaid
flowchart LR
    R[Request] --> T{Timeout?}
    T -->|no| OK[Success]
    T -->|yes| CB{Circuit<br/>open?}
    CB -->|yes| FAIL[Fail fast<br/>degrade gracefully]
    CB -->|no| RETRY[Retry with<br/>backoff + jitter]
    RETRY --> IDEM{Idempotent?}
    IDEM -->|yes| OK
    IDEM -->|no| DUP[Duplicate work<br/>possible corruption]

    style DUP fill:#2b1c17,stroke:#e0705a,color:#e4ecea
    style IDEM fill:#2a2317,stroke:#d9a441,color:#e4ecea
```

The red box is what you get when retries are added without idempotency — a very common sequence,
because retries are easy to add and idempotency is easy to forget.

## 13. When to invest heavily

- Money, health, legal records — anywhere a wrong answer has consequences beyond annoyance
- Anything without a human to notice the mistake
- Write paths, always: a bad read is recoverable, a bad write may not be

## 14. When NOT to

- Read-only derived data that can simply be recomputed
- Analytics where a 0.1% error is invisible
- Before you have basic observability: **you cannot improve reliability you cannot measure**
- When it would be cheaper to make recovery fast than to make failure rare

## 17. Trade-offs

| Choose | Get | Pay |
|---|---|---|
| Retries | Survives transient faults | Duplicates unless idempotent; retry storms |
| Synchronous replication | No data loss on failover | Latency on every write; reduced availability |
| Async replication | Fast writes | A failover window where committed data is lost |
| Circuit breaker | Contains cascading failure | Rejects requests that might have worked |
| Strong consistency | Simple correctness reasoning | Latency, and availability under partition |

## 19. Failure scenarios

| Failure | Effect | Mitigation |
|---|---|---|
| Transient network blip | Request fails spuriously | Retry with backoff + jitter |
| Worker dies mid-job | Job lost or half-applied | At-least-once delivery + idempotency |
| Message delivered twice | Duplicate effect | Idempotency keys |
| Messages out of order | Inconsistent state | Sequence numbers, or design order-independently |
| Poison message | Retries forever, blocks the queue | Delivery cap → dead letter queue |
| Silent data corruption | Wrong answers, undetected | Checksums, invariant checks, reconciliation |
| Partial write | Some records applied | Transactions, or the outbox pattern |

**Silent corruption is the worst row**, because nothing alerts. This is what reconciliation jobs are
for: periodically re-derive the truth and compare.

## 25. Without it → With it → New problem → Next

```
Without it   →  failures produce wrong answers and lost data, silently
With it      →  failures produce correct-but-degraded behaviour, loudly
New problem  →  retries create duplicates; replication creates lag and disagreement
Next         →  idempotency to make retries safe, then consistency to reconcile the copies
```

## 26. Combination patterns

- **Retry + circuit breaker** — retries alone finish off a struggling service; the breaker is what
  makes retries safe
- **Queue + workers + idempotency** — the standard at-least-once pipeline
- **Replication + failover** — durability and availability together, at the cost of lag

## 28. Common mistakes

| Mistake | Why it is wrong |
|---|---|
| Retries without idempotency | Manufactures duplicate writes |
| Retries without backoff | Retry storm; you finish off the dying service |
| Retries without jitter | Every client retries in lockstep, recreating the spike |
| No timeout | One slow dependency exhausts your threads |
| No dead letter queue | One poison message blocks the whole queue |
| Confusing availability with reliability | Optimising uptime while losing data |
| Assuming replicas are independent | Same bug, same code, all copies wrong |

## 29. Monitoring

Error rate by type — distinguish "failed loudly" from "returned something wrong", because only the
first shows up in a 5xx count. Track MTTR, not just incident count. Run reconciliation jobs that
re-derive state independently and alert on divergence; this is the only defence against silent
corruption.

## 31. Exercises

**1.** A colleague adds retries to every outbound call in the service. What did they just break?

<details><summary>Answer</summary>

Correctness on every non-idempotent write. A retry cannot tell a lost request from a lost *response*,
so a timeout that fires after the work succeeded turns "charge the card" into "charge the card
twice".

Retries are easy to add and [idempotency](../../GLOSSARY.md#idempotency) is easy to forget, which is
exactly the sequence in the diagram in [§9](#9-how-it-works). They also need backoff **and** jitter:
without backoff you finish off a dependency that was merely struggling, and without jitter every
client retries in lockstep and recreates the original spike.
</details>

**2.** Make a payment endpoint safe to retry. What exactly do you store, and where?

<details><summary>Answer</summary>

An idempotency key supplied by the client, stored **with the result** of the operation — so a repeat
of the same key returns the original outcome rather than performing the effect again. Returning
"already done" is not enough; the caller needs the same response body it would have got the first
time, or it cannot tell success from a duplicate.

The subtlety is atomicity: the key and the effect must be committed together. Write the charge in one
transaction and record the key in another and a crash between them gives you a charge with no key,
which is precisely the case the whole mechanism exists to prevent.
</details>

**3.** A service returns HTTP 200, quickly, every time — with a balance that is wrong. What is its
availability, and what is its reliability?

<details><summary>Answer</summary>

100% available and catastrophically unreliable. Availability measures whether you responded, not
whether you were right, so this failure is invisible in an uptime dashboard and invisible in a 5xx
rate.

It also sits near the top of the badness ordering — `data loss > silent wrong answer > loud failure >
slow > fine` — because a loud failure can be retried and a wrong answer propagates. This is what
reconciliation jobs are for: periodically re-derive the truth independently and alert on divergence.
</details>

**4.** Your analytics events replicate asynchronously. An engineer proposes switching to synchronous
replication so that no event can ever be lost. Do you approve it?

<details><summary>Answer</summary>

No. Synchronous replication puts the slowest follower on the critical path of every write and reduces
availability — a real, permanent cost — to protect data whose loss nobody can detect. A missing
analytics event is at the cheap end of the ordering above.

The question to ask is what a lost record actually costs, and then whether the money would buy more
by reducing MTTR than by increasing MTBF. It usually would: you cannot prevent every failure, but you
can always recover faster. Save synchronous replication for the ledger, not the telemetry.
</details>

## 32. Decision checklist

- [ ] Every retried operation is idempotent
- [ ] Every retry has backoff **and jitter**
- [ ] Every outbound call has a timeout
- [ ] Poison messages have a delivery cap and a DLQ
- [ ] Data loss window under failover is known and accepted
- [ ] Correctness is monitored, not only uptime
- [ ] MTTR is measured, and rehearsed

## 33. Related

- [Observability](../../11-observability/) — how you would know any of this broke
- [Availability](../availability/) — up versus correct
- [Consistency](../consistency/) — agreement between copies
- [Glossary: idempotency](../../GLOSSARY.md#idempotency) · [retry storm](../../GLOSSARY.md#retry-storm)
