---
topic: Latency
category: Foundations
difficulty: Beginner
concepts: [performance, percentiles, tail-latency]
related: [throughput, batching, caching]
---

# Latency

`[BEGINNER]` · How long **one** operation takes. The number your users actually feel.

---

## 1. One-line definition

The time between making a request and receiving the response.

## 2. Explain like I'm new

You order a coffee. Latency is how long *you* wait, from ordering to holding the cup. It has nothing
to do with how many coffees the shop makes an hour — that is a different number, and confusing the
two is the most common mistake in this whole subject.

## 3. Real-world analogy

A single car's journey time from A to B.

**Where the analogy breaks:** a road can carry more cars by adding lanes without any one journey
getting faster. Systems work the same way — which is exactly why latency and
[throughput](../throughput/) are separate axes. Adding servers usually raises throughput and does
nothing at all for latency.

## 4. Technical explanation

Latency is a **distribution**, not a number. Every request takes a different amount of time, and the
shape of that distribution is what matters.

The distribution is almost always right-skewed with a long tail: most requests are fast, a few are
dramatically slower. That shape is why the average is close to useless.

| Statistic | What it tells you |
|---|---|
| Average (mean) | Almost nothing. One 10-second request hides behind a thousand fast ones. |
| p50 (median) | The typical experience |
| **p99** | The experience of your least happy 1% — **quote this one** |
| p99.9 | Where your worst outliers live; matters at high volume |

**Always specify the percentile.** "Latency is 20ms" is not a claim, because it does not say whether
that is p50 or p99, and those can differ by 50×.

## 5. Engineering at scale

Two things become true at scale that are not obvious at small scale.

**Tail latency dominates.** If a single page load fans out to 100 backend services, and each has a
1% chance of being slow, then the probability that *at least one* is slow is `1 - 0.99^100 ≈ 63%`.
Nearly two thirds of page loads hit somebody's p99. **At scale, your p99 becomes your typical
experience.**

```mermaid
flowchart TD
    U["One page load"] --> F["fans out to 100 backend services"]
    F --> A["Service 1<br/>fast 99 calls in 100"]
    F --> B["Service 2<br/>fast 99 calls in 100"]
    F --> C["...97 more, each just as good..."]
    F --> D["Service 100<br/>fast 99 calls in 100"]
    A --> J["The page cannot finish until the<br/><b>slowest</b> of the 100 has finished"]
    B --> J
    C --> J
    D --> J
    J --> OUT["1 minus 0.99 to the power 100 = 0.63<br/><b>63 page loads in every 100<br/>are waiting on someone's p99</b>"]

    style J fill:#2a2317,stroke:#d9a441,color:#e4ecea
    style OUT fill:#2b1c17,stroke:#e0705a,color:#e4ecea
```

Every box in the middle row is individually excellent — a service that is fast 99% of the time is one
most teams would be pleased to own. Read off the join: a fan-out inherits the **maximum** of its
dependencies, not their average, so a hundred excellent services compose into a page that is slow
most of the time. Nobody on that middle row will see anything wrong on their own dashboard.

**Latency adds along the synchronous path and does not along the asynchronous one.** This is the
single most useful reading skill for an architecture diagram — sum the solid arrows, ignore the
dashed ones. See [the notation contract](../../19-diagrams/README.md).

## 6. The problem it solves

Latency is not a solution — it is a *constraint you are given*. It is on this list because most
architecture decisions are made in service of it.

## 7. The problem it does NOT solve

Low latency does not mean high capacity. A system can answer every request in 2ms and still collapse
at 100 concurrent users. If you optimise latency and your problem was throughput, nothing improves.

## 8. Why does this exist as a concept?

Because "make it faster" is ambiguous, and the two things it might mean are addressed by opposite
techniques. Batching makes throughput better and latency worse. Caching usually improves both.
Adding servers improves throughput and leaves latency untouched.

---

## 9. How it works — where the time goes

```mermaid
flowchart LR
    C[Client] -->|"network<br/>~1-150ms"| LB[Load Balancer]
    LB -->|"~0.5ms"| A[Service]
    A -->|"queue wait<br/>0 to ∞"| A2[Service: processing]
    A2 -->|"~0.5ms"| D[(Database)]
    D -->|"disk / index<br/>~0.1-10ms"| D
```

Five contributors, roughly in order of how often they are the actual culprit:

1. **Queueing delay** — waiting for a free worker. Invisible in code, dominant under load, and the
   usual answer when latency degrades non-linearly.
2. **Network** — dominated by physical distance. Unfixable except by moving closer.
3. **Processing** — actual computation. Usually the *smallest* term, and usually where people look first.
4. **Storage** — disk seeks, index traversal, lock waits.
5. **Serialisation** — encoding and decoding, which becomes real with large payloads.

Those five are not the same size, and they do not grow together. Illustrative numbers for one
endpoint, same code path in both rows:

```mermaid
flowchart LR
    subgraph FAST["This request at p50 — 13 ms total"]
        F1["network<br/>10 ms"] --> F2["queue<br/>0 ms"] --> F3["serialise<br/>1 ms"] --> F4["process<br/>1 ms"] --> F5["storage<br/>1 ms"]
    end
    subgraph SLOW["The same request at p99 — 250 ms total"]
        S1["network<br/>10 ms"] --> S2["queue<br/>237 ms"] --> S3["serialise<br/>1 ms"] --> S4["process<br/>1 ms"] --> S5["storage<br/>1 ms"]
    end

    style S2 fill:#2a2317,stroke:#d9a441,color:#e4ecea
```

Read off which box changed. Four of the five terms are **identical** in both rows; the entire
p50-to-p99 gap is queueing. That term is invisible to a profiler, because the request has not begun
executing while it accrues — which is why the instinct to open a flame graph and stare at *process*,
the smallest box on the diagram, so reliably finds nothing.

## 11. The numbers that shape architecture

Orders of magnitude, not measurements. The ratios are the point.

| Operation | Order |
|---|---|
| Memory reference | ~100 ns |
| SSD random read | ~100 µs |
| Round trip inside a datacentre | ~0.5 ms |
| Round trip across a continent | ~50 ms |
| Round trip across the world | ~150 ms |

**Memory is ~1,000× faster than SSD. A cross-world round trip is ~1,000,000× slower than memory.**

Those two ratios explain most of system design. Caching exists because of the first. CDNs and
multi-region exist because of the second, and because **the speed of light is the one constraint no
amount of hardware fixes**.

---

## 13. When to optimise for latency

- Anything a human is waiting on. Perceptible delay starts around 100ms; ~1s breaks the sense of
  direct manipulation.
- Anything on a fan-out path, where your p99 becomes someone else's typical case.
- Trading, bidding, real-time control — where latency *is* the product.

## 14. When NOT to

- Batch and offline work. A nightly job that finishes by morning has no latency requirement, and
  optimising it costs throughput you actually need.
- When the real complaint is capacity. Measure before choosing which number to chase.
- When it is already below human perception. Going from 20ms to 10ms is invisible and will cost you
  something real elsewhere.

## 17. Trade-offs

| Choose | Get | Pay |
|---|---|---|
| Cache | Much lower p50 and p99 | Staleness, invalidation, thundering herd |
| Edge / CDN | Lower network term | Only works for cacheable responses |
| Bigger connection pool | Less queueing delay | More memory and DB connections |
| Batching | — | **Worse latency**, better throughput |
| Async processing | Lower *perceived* latency | The work is now eventual |

## 19. Failure scenarios

| Failure | What happens |
|---|---|
| A dependency gets slow | **Worse than it going down.** A dead dependency fails fast and you route around it; a slow one holds every thread that touches it and takes down callers that do not even depend on it. |
| Queue builds up | Latency rises non-linearly. Near saturation, a 10% traffic increase can multiply wait time. |
| Retry storm | Retries add load, which adds latency, which triggers more retries. |
| GC pause / cold start | A clean p99 with an ugly p99.9 |

**Timeouts are not optional.** They are the only thing that converts "slow" back into "down", which
is the failure mode you can actually handle.

## 21. Performance — the counter-intuitive part

Latency does **not** degrade linearly with load. Queueing theory says wait time scales roughly with
`1/(1 - utilisation)`:

| Utilisation | Relative wait |
|---|---|
| 50% | 2× |
| 80% | 5× |
| 90% | 10× |
| 95% | 20× |
| 99% | 100× |

**This is why you do not run systems at 90% utilisation**, however efficient it looks on a cost
dashboard. The last 10% of capacity buys you 10× the latency, and leaves nothing for a traffic spike.

```mermaid
flowchart LR
    A["Running at 50% utilisation<br/>wait ≈ 2× the service time"] -->|"traffic rises<br/>by 10 points"| A2["Now at 60%<br/>wait ≈ 2.5×<br/><i>nobody notices</i>"]
    B["Running at 90% utilisation<br/>wait ≈ 10× the service time"] -->|"<b>the same</b><br/>10-point rise"| B2["Now at 100%<br/>the queue never drains<br/><i>wait is bounded only by your timeout</i>"]

    style B fill:#2a2317,stroke:#d9a441,color:#e4ecea
    style B2 fill:#2b1c17,stroke:#e0705a,color:#e4ecea
```

Two rows, the same input on both: ten points more traffic. Read off how different the outputs are —
the top row absorbs it invisibly, the bottom row falls off the end of the curve, because
`1/(1 − utilisation)` has no finite value at 1. The headroom that looks like waste on a cost
dashboard is the identical headroom that was absorbing your spikes, so the two rows are the same
decision seen before and after.

---

## 25. Without it → With it → New problem → Next

```
Without it   →  no way to say what "fast" means, so no way to know if a change helped
With it      →  a measurable target, and a way to find the bottleneck
New problem  →  optimising latency often costs throughput or money
Next         →  throughput, and the trade-off framework for deciding between them
```

Latency is where the whole chain starts: a latency problem is what forces the first cache, which
forces invalidation, which forces everything after it.

## 26. Combination patterns

- **Cache + database** — the standard latency fix; the cache absorbs the skewed reads
- **CDN + load balancer + cache** — attacks the network term, which nothing else can
- **Batching + queue** — deliberately trades latency away for throughput

## 28. Common mistakes

| Mistake | Why it is wrong |
|---|---|
| Quoting the average | Hides the tail completely |
| Measuring server-side only | Excludes network and client time — the user's number is larger |
| Optimising the median | The p99 is what people complain about |
| No timeouts | Slow dependencies hang everything |
| Running at high utilisation | Latency explodes non-linearly |
| Confusing it with throughput | Leads to fixing the wrong thing entirely |

## 29. Monitoring

Track p50, p99 and p99.9 separately — **never average percentiles across hosts**, which is
mathematically meaningless. Alert on p99 breaching its budget, not on the mean. Break the number down
by endpoint; one slow endpoint disappears inside an aggregate.

## 31. Exercises

**1.** Your p50 is 25 ms and your p99 is 3 seconds. The code path is identical for both. Where is the
time going?

<details><summary>Answer</summary>

Not in the code — if the path is the same, the difference is contention rather than computation.
Queueing delay is the usual culprit, along with GC pauses, a cold cache, a connection pool wait, or
one slow shard or replica. None of those appear in a profiler run on an idle machine, which is why
this gets misdiagnosed.

A p99 that is 100× the p50 is the signature of a system running close to saturation — check
utilisation and queue depth per stage before anything else, and see [§21](#21-performance--the-counter-intuitive-part).
</details>

**2.** Finance points out that your servers average 35% CPU and asks you to run them at 90%. Make the
counter-argument in numbers.

<details><summary>Answer</summary>

Queueing theory: wait time scales roughly with `1/(1 − utilisation)`. At 50% you wait about 2× the
service time, at 90% about 10×, at 95% about 20× — so the last slice of capacity costs an order of
magnitude of latency, and it is also the slice that absorbs a traffic spike.

At 90% you do not degrade gracefully under a spike, you fall off a cliff. The correct response to the
cost question is not "no" but fewer larger instances, or autoscaling — cheaper capacity, not less
headroom.
</details>

**3.** A dependency you call synchronously slows from 50 ms to 5 seconds but keeps returning 200s.
Why is that worse than it going down, and what would have contained it?

<details><summary>Answer</summary>

A dead dependency fails in milliseconds — connection refused — so you route around it or fail fast. A
slow one holds a thread and a pool slot for five seconds per request, so at any real arrival rate your
pool exhausts and **every** endpoint goes down, including the ones that never touch it.

Containment is a timeout set below your own latency budget, which is the only thing that converts
"slow" back into "down" — a failure mode you can actually handle — plus a circuit breaker and a
bulkhead so one dependency cannot consume the whole pool.
</details>

**4.** Your p50 is 20 ms. Product asks for 10 ms. Should you do the work?

<details><summary>Answer</summary>

Almost certainly not, and you should say so rather than quietly deprioritising it. Perceptible delay
starts around 100 ms; 20 ms to 10 ms is invisible to a human and will cost you something real — a
cache to invalidate, a denormalisation to keep in sync, headroom spent.

Two answers would change it: the endpoint sits on a fan-out path where your p99 becomes someone
else's typical case, or a contract specifies the number. Ask which. Otherwise the honest reply is
"we can, and it would be the worst-value work on the roadmap" — see [§14](#14-when-not-to).
</details>

**5.** Adding servers cut your p99 in half. Does that mean latency scales horizontally after all?

<details><summary>Answer</summary>

Only the queueing term did. You removed contention, so requests stopped waiting for a free worker —
but the network, processing and storage terms are untouched, and once the queue is empty there is
nothing left to remove. Add more servers to an under-utilised system and p99 will not move at all.

The general rule survives: horizontal scaling buys [throughput](../throughput/), and buys latency only
to the extent that the latency was a capacity problem wearing a disguise.
</details>

## 32. Decision checklist

- [ ] Latency target stated as a **percentile**, not an average
- [ ] Measured at the client, not just the server
- [ ] Broken down per endpoint
- [ ] Every outbound call has a timeout
- [ ] Utilisation kept below ~70%
- [ ] You know whether the requirement is really latency or throughput

## 33. Related

- [Observability](../../11-observability/) — how you would know any of this broke
- [Throughput](../throughput/) — the other half; read it next
- [Estimation guide](../../ESTIMATION-GUIDE.md) — the latency table in context
- [Trade-off framework](../../TRADEOFF-FRAMEWORK.md) — the "faster reads" decision tree
- [Glossary: tail latency](../../GLOSSARY.md#tail-latency)

<!-- PATH:BEGIN -->

---

<sub>**The reading path** · step 5 of 27 · *Latency*</sub>

◀ **Previous** [Foundations](../../00-foundations/README.md) &nbsp;·&nbsp; **Next** [Throughput](../../00-foundations/throughput/README.md) ▶

<!-- PATH:END -->
