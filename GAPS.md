---
topic: Coverage Gaps
category: Meta
difficulty: n/a
---

# Coverage Gaps

What this repository does **not** cover, and what the original plan left out entirely.
[ROADMAP.md](ROADMAP.md) tracks what is *planned and unbuilt*. This page tracks what was *never
planned* — the more dangerous category, because an unplanned gap looks exactly like coverage.

Status values: ✅ covered · ◐ partial · ❌ absent

---

## Scorecard — the standard system design syllabus

The list most interview guides and job descriptions use, scored honestly against this repository.

| Topic | Status | Where it is, or why not |
|---|---|---|
| **Databases — SQL and NoSQL** | ✅ | [database](05-databases/fundamentals/) — the type table and the choose-by-access-pattern rule |
| **Caching — strategies, eviction** | ✅ | [cache](04-caching/fundamentals/) |
| **Redis vs Memcached** | ◐ | Named in the cache page's alternatives table; no comparison page |
| **CDN** | ❌ | Referenced in 13 files, has no page |
| **APIs — REST, gRPC, GraphQL, versioning** | ❌ | The word appears everywhere; API *design* is nowhere |
| **Functional / non-functional requirements** | ◐ | Steps 3–4 of [the method](SYSTEM-DESIGN-THINKING.md); the NFRs each have a page; no page on eliciting or writing requirements |
| **DNS** | ◐ | Mentioned in availability and load balancer; no page |
| **TCP / UDP** | ❌ | One passing mention |
| **HTTP / HTTP2 / HTTP3** | ❌ | Mentioned as a protocol label only |
| **WebSockets** | ❌ | Two mentions |
| **TLS / SSL** | ◐ | Certificate expiry as a failure mode; no page |
| **OAuth** | ❌ | Zero occurrences |
| **JWT** | ❌ | Zero occurrences |
| **API security** | ❌ | — |
| **Rate limiting** | ✅ | [Implementation](18-implementations/rate-limiter/) with measured benchmarks |
| **DDoS protection** | ❌ | One mention |
| **Message queues** | ✅ | [queue](06-messaging/queues/) |
| **Kafka vs RabbitMQ** | ◐ | The queue-vs-stream distinction is covered properly; no product comparison page |
| **Microservices vs monolith** | ❌ | Named in trade-offs; no page |
| **Fault tolerance / fallback** | ◐ | [reliability](00-foundations/reliability/); circuit breaker and bulkhead have no pages |
| **Redundancy** | ✅ | [availability](00-foundations/availability/) |
| **Load balancer types and algorithms** | ✅ | [load balancer](03-load-balancing/fundamentals/) — L4/L7 and six algorithms |
| **Observability — Prometheus, Grafana, ELK** | ❌ | **Zero occurrences.** Every concept page has a "how would you know it broke?" section pointing at nothing |
| **Alerting — PagerDuty, on-call** | ❌ | Zero occurrences |

**Roughly a third covered, a third partial, a third absent.**

## Scorecard — HLD deliverable

What a high-level design document is expected to contain.

| Element | Status | Where it is, or why not |
|---|---|---|
| **System architecture overview** | ◐ | The [scene format](19-diagrams/scenes/SCHEMA.md) expresses one; no guide to writing one |
| **Data flow and component interaction** | ✅ | [Combination matrix](14-component-combinations/MATRIX.md), [notation contract](19-diagrams/README.md), animated scenes |
| **Technology stack and infrastructure** | ❌ | Deliberately technology-agnostic — but the mapping from role to real technology was supposed to be a late section on each page, and it is not there |
| **Module responsibilities** | ❌ | No guidance on decomposition or ownership |
| **Performance and trade-offs** | ✅ | [Trade-off framework](TRADEOFF-FRAMEWORK.md) plus a trade-off table on every page |
| **Scalability / security / cost as NFRs** | ◐ | Scalability yes; security no; cost is an axis with no section |
| **Architecture + component diagrams** | ✅ | [Notation contract](19-diagrams/README.md) and generated SVGs |
| **Deployment diagrams** | ◐ | Named as a diagram type; no example |
| **Data flow diagrams** | ✅ | Notation contract |
| **ER / schema diagrams** | ❌ | Not a supported diagram type; data modelling is not covered |
| **An HLD / LLD document template** | ❌ | The biggest single miss here — there is no template for the artefact itself |

---

## Tier 1 — Missing from the plan, and load-bearing

| Gap | Why it matters |
|---|---|
| **Observability** | Prometheus, Grafana, ELK, tracing, alerting, on-call. Every page asks "how would you know it broke?" and answers nowhere. |
| **Security** | OAuth, JWT, TLS, API security, secrets, DDoS. Absent entirely. |
| **Networking** | DNS, TCP/UDP, HTTP/2/3, WebSockets, connection pooling. |
| **API design** | REST vs gRPC vs GraphQL, versioning, pagination, error contracts, idempotency keys. The interface every other decision is expressed through. |
| **Microservices vs monolith** | When to split, how to manage dependencies, the distributed monolith. |
| **HLD / LLD templates** | The document people are actually asked to produce. |
| **Schema migration** | Zero-downtime change: expand-contract, dual writes, backfills. The most common way a deploy causes an outage. |
| **Data modelling / ER** | Normalisation, access-pattern modelling, ER diagrams. |
| **Batch vs stream processing** | OLTP vs OLAP, ETL, windowing, Lambda/Kappa. |
| **SLI / SLO / error budgets** | The vocabulary for deciding how reliable is reliable enough. |
| **Multi-tenancy** | Isolation, noisy neighbours, per-tenant limits. |
| **Cost** | A trade-off axis with no section. At scale it kills more designs than latency. |

## Tier 2 — Missing from the plan, narrower

Search as a component · geospatial indexing (the plan has Uber as a problem and no way to answer it)
· probabilistic structures (Bloom, HyperLogLog, count-min) · storage engine internals (B-tree vs LSM —
now partly covered in [database](05-databases/fundamentals/)) · serialisation and schema evolution ·
load shedding · tail-latency techniques (hedged requests) · cell-based architecture · fan-out on write
vs read · compliance and data residency · chaos engineering · feature flags

## Tier 3 — Planned, not yet built

On [ROADMAP.md](ROADMAP.md). **Components:** CDN, API gateway. **Patterns:** batching, retries,
circuit breaker, rate limiting page, backpressure, async. **Combinations:** the 10 `CORE` pairs need
pages. **Problems:** 7 of 8. **Implementations:** 7 of 8. **Judgment:** ADRs, anti-patterns,
comparisons, interview guide.

---

## What is genuinely covered

- [Foundations](00-foundations/) — 7 concepts, complete
- [Load balancer](03-load-balancing/fundamentals/) · [cache](04-caching/fundamentals/) ·
  [database](05-databases/fundamentals/) · [queue](06-messaging/queues/) ·
  [worker](06-messaging/workers/) · [sharding](05-databases/sharding/) ·
  [replication](05-databases/replication/)
- [The method](SYSTEM-DESIGN-THINKING.md) · [trade-offs](TRADEOFF-FRAMEWORK.md) ·
  [estimation](ESTIMATION-GUIDE.md) · [checklist](DESIGN-CHECKLIST.md)
- [Pattern catalogue](13-design-patterns/CATALOGUE.md) — 78 patterns; 23 GoF with full entries
- [Combination matrix](14-component-combinations/MATRIX.md) — all 153 pairs
- [Diagram notation](19-diagrams/README.md) and the scene format
- One implementation with measured benchmarks; one scene with 8 versions

## How this page stays honest

1. When an item is built it moves to **What is genuinely covered** and the roadmap is ticked in the
   same commit.
2. New gaps are added when **noticed**, not when planned. A gap nobody has written down is
   indistinguishable from coverage.
