---
topic: Availability
category: Foundations
difficulty: Beginner
concepts: [reliability, redundancy, sla]
related: [reliability, cap-theorem, consistency]
---

# Availability

`[BEGINNER]` · The fraction of time the system answers successfully. Measured in nines, and each nine costs about 10× the last.

---

## 1. One-line definition

The probability that a request made right now gets a successful response.

## 2. Explain like I'm new

A shop with a sign saying "open 99% of the time" is closed for about 3.5 days a year — and you will
not know in advance which days. Availability is that percentage for a system, and the interesting
question is never the number itself but **what it costs to add another 9**.

## 3. Real-world analogy

A hospital emergency department: it must be open even when staff are ill, so it keeps spare capacity
and cross-trained people.

**Where it breaks:** a hospital degrades gracefully — a queue forms, urgent cases go first. Many
software systems have no equivalent and simply fail. Building the graceful version is a deliberate
choice, not a default.

## 4. Technical explanation

```
Availability = uptime / (uptime + downtime)
```

| Nines | Downtime/year | Downtime/month | Realistically means |
|---|---|---|---|
| 99% | 3.65 days | 7.2 hours | One server, manual recovery |
| 99.9% | 8.77 hours | 43.8 min | Redundancy, someone on call |
| 99.99% | 52.6 min | 4.4 min | Automated failover, multi-AZ |
| 99.999% | 5.26 min | 26 s | Multi-region, no human in the loop |

**Five minutes a year is less time than it takes a human to read an alert and open a laptop.** Past
about 99.99%, every recovery has to be automatic — which is why the cost curve is exponential rather
than linear.

### Components in series multiply

This is the part that surprises people:

```
Service (99.9%) → Database (99.9%) → Cache (99.9%)
   0.999 × 0.999 × 0.999  =  99.7%      ~26 hours/year
```

**A chain is less available than any of its links.** Ten dependencies at 99.9% each give you 99%.
This is the strongest technical argument against gratuitous microservices, and the reason each
synchronous dependency you add has a real cost.

### Redundancy in parallel adds nines

```
Two independent servers at 99% each:
   1 - (0.01 × 0.01)  =  99.99%
```

The word doing the work is **independent**. Two servers in the same rack share a power supply; two
availability zones share a region; two regions share your deployment pipeline and your DNS. Correlated
failure is what turns a calculated 99.99% into a real 99.5%.

## 5. Engineering at scale

**Your availability is capped by your least available critical dependency.** Before promising 99.99%,
check what your cloud provider, payment processor and DNS actually promise. You cannot exceed them on
the synchronous path.

**Most outages are not hardware.** They are deploys, config changes, certificate expiry, and capacity
exhaustion. Redundancy protects against a machine dying; it does nothing at all against a bad config
pushed to every machine simultaneously. Staged rollouts protect against the more common failure.

## 6. The problem it solves

Puts a number on "how much downtime is acceptable", which turns an argument into a budget.

## 7. The problem it does NOT solve

Availability says nothing about **correctness**. A system returning wrong answers quickly is 100%
available and useless. It also says nothing about [durability](../reliability/) — a system can be up
while quietly losing data.

---

## 9. How it works

```mermaid
flowchart LR
    C[Client] --> LB[Load Balancer<br/>redundant pair]
    LB --> A1[Server A]
    LB --> A2[Server B]
    LB --> A3[Server C]
    A1 --> D[(Primary)]
    A2 --> D
    A3 --> D
    D ==>|replication| R[(Standby)]

    style D fill:#2a2317,stroke:#d9a441,color:#e4ecea
```

Three app servers, but **one primary database** — so the system's availability is the database's
availability. Redundancy at the wrong layer buys nothing. Find the un-redundant component; that is
your real number.

Note also that a *single* load balancer would make the whole diagram pointless, which is the classic
mistake: adding an LB to remove a single point of failure and creating one in the process.

## 13. When to chase more nines

- Revenue stops when you are down
- Contractual SLA with penalties
- Safety-relevant systems
- The cost of downtime exceeds the cost of the next nine — **compute this, do not assume it**

## 14. When NOT to

- Internal tools. 99% is genuinely fine for a dashboard three people use.
- Before you have measured your current availability. You cannot improve a number you do not have.
- When correctness or durability matters more. A payment system that is briefly down is
  survivable; one that loses a transaction is not.
- When the money would buy more by reducing [latency](../latency/) instead.

## 17. Trade-offs

| Choose | Get | Pay |
|---|---|---|
| Redundancy | Higher availability | ~2× infrastructure cost |
| Multi-region | Survives regional failure | ~2× cost, cross-region consistency problems |
| Automated failover | Recovery in seconds | Split-brain risk; failover itself can cause the outage |
| Graceful degradation | Partial service beats none | Every feature needs a defined degraded mode |
| **Choosing A over C under partition** | Stays up during a network split | Serves stale or conflicting data — see [CAP](../cap-theorem/) |

## 19. Failure scenarios

| Failure | Effect | Mitigation |
|---|---|---|
| Single instance dies | Proportional capacity loss | N+1 redundancy, health checks |
| Whole AZ fails | Big loss if not spread | Multi-AZ |
| Region fails | Total outage | Multi-region + **tested** failover |
| Bad deploy | 100% outage, instantly, everywhere | Canary, staged rollout, fast rollback |
| Cert expiry | Total outage, entirely predictable | Automated renewal + expiry alerting |
| Dependency slow (not down) | Threads exhaust; you go down too | Timeouts, circuit breakers, bulkheads |

**Untested failover is not failover.** A standby nobody has ever failed over to is a hypothesis, and
the outage is a poor time to test it.

## 25. Without it → With it → New problem → Next

```
Without it   →  no shared definition of "up", so no way to decide what redundancy is worth
With it      →  a budget that justifies (or refuses) redundancy spending
New problem  →  redundancy means multiple copies, which means keeping them in agreement
Next         →  consistency, and then CAP — because under a partition you must choose
```

Availability is one half of the [CAP](../cap-theorem/) trade-off. You cannot reason about CAP until
you can state your availability target.

## 26. Combination patterns

- **Load balancer + health checks** — removes dead servers automatically; the foundation of the rest
- **Replication + failover** — availability for stateful components, which is the hard case
- **Circuit breaker + graceful degradation** — stays partly up when a dependency is down

## 28. Common mistakes

| Mistake | Why it is wrong |
|---|---|
| Redundant app servers, single database | Availability equals the database's |
| Assuming independence | Same rack, same AZ, same deploy pipeline = correlated failure |
| Ignoring dependency chains | Ten 99.9% dependencies in series = 99% |
| Untested failover | Discovering it does not work during the outage |
| Measuring server-side only | Users experiencing DNS or CDN failures are down and invisible to you |
| Chasing nines nobody asked for | Enormous cost, no value |

## 29. Monitoring

Measure availability from **outside** — a synthetic probe from a user's perspective, not your own
health endpoint saying it is fine. Track it as successful requests / total, per endpoint. Alert on
error budget burn rate rather than on individual failures, so a slow leak is caught and a single blip
is not paged.

## 31. Exercises

**1.** A request passes through three services in series, each measured at 99.9%. What is the
availability of the request, in per cent and in hours per year?

<details><summary>Answer</summary>

`0.999 × 0.999 × 0.999 = 99.7%`, which is about **26 hours a year** — roughly three times the
downtime of any single link. A chain is always less available than its weakest member, and ten
dependencies at 99.9% give you 99%.

This is the strongest technical argument against gratuitous synchronous dependencies: every one you
add has a cost you can compute before you add it. It is also the arithmetic most people skip, which
is why it is on the [diagnostic](../../DIAGNOSTIC.md).
</details>

**2.** Two servers at 99% each, in parallel, calculate to 99.99%. When is that number a lie?

<details><summary>Answer</summary>

Whenever the failures are correlated, which is most of the time. Two servers in a rack share a power
supply and a switch; two availability zones share a region; two regions share your deployment
pipeline, your DNS, your certificate authority and your config management.

**Independence is the word doing all the work in that formula.** Correlated failure is what turns a
calculated 99.99% into a real 99.5%, and the correlation is usually organisational rather than
physical — one bad config, pushed everywhere at once.
</details>

**3.** You are at 99.9% and have been asked for 99.99%. What actually has to change?

<details><summary>Answer</summary>

52 minutes a year is less than it takes a human to read an alert and open a laptop, so the first
change is that **no recovery may involve a person**: automated failover, multi-AZ, health-check-driven
ejection. That is the answer people expect.

The more useful half is that most outages are not hardware. They are deploys, config changes,
certificate expiry and capacity exhaustion — none of which redundancy protects against, since the bad
config reaches every replica simultaneously. Canaries, staged rollout and fast rollback usually buy
more nines per pound than another standby does.
</details>

**4.** An internal dashboard used by three people sits at 99%. Someone proposes multi-AZ with
automated failover. Do you approve it?

<details><summary>Answer</summary>

No. 99% is 3.65 days a year, and for a dashboard three people open occasionally that costs
approximately nothing — while the proposal costs roughly double the infrastructure plus a failover
mechanism that must itself be tested to be worth anything.

The question to make people answer is *what does an hour of downtime cost here*, and then compare it
to the price of the next nine. Chasing nines nobody asked for is a real and common way to spend a
budget that would have bought more as [latency](../latency/) somewhere else.
</details>

**5.** Would you ever deliberately choose **lower** availability?

<details><summary>Answer</summary>

Yes, and a payment ledger is the standard case. Under a network partition you must pick: keep
answering and risk a double spend, or refuse and be down for the duration. For money, refusing is
correct — a bank that is briefly closed survives, one that loses a transaction does not.

That is the CP side of [CAP](../cap-theorem/), and it is a deliberate purchase of correctness with
availability. Note also that availability says nothing about correctness on its own: a system
returning wrong answers quickly scores 100%.
</details>

## 32. Decision checklist

- [ ] Target stated as a number, with the cost of downtime that justifies it
- [ ] Every single point of failure identified — especially stateful ones
- [ ] Dependency chain multiplied out, not assumed
- [ ] Redundancy is genuinely independent (rack, AZ, region, deploy)
- [ ] Failover has actually been executed, deliberately, at least once
- [ ] Measured externally, not from inside the system
- [ ] Degraded modes defined per feature

## 33. Related

- [Observability](../../11-observability/) — how you would know any of this broke
- [Reliability](../reliability/) — availability is about being up; reliability is about being right
- [CAP theorem](../cap-theorem/) — the choice availability forces
- [Latency](../latency/) — slow is a form of down
- [Glossary: availability](../../GLOSSARY.md#availability)
