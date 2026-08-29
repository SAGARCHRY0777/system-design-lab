---
topic: Coverage Gaps
category: Meta
difficulty: n/a
---

# Coverage Gaps

What this repository does **not** cover yet, and — more usefully — what the original plan left out
entirely. [ROADMAP.md](ROADMAP.md) tracks what is *planned and unbuilt*. This page tracks what was
*never planned*, which is the more dangerous category, because an unplanned gap looks like coverage.

Every item says whether it is **missing from the plan** (nobody had thought of it) or **planned,
unbuilt** (on the roadmap, not yet written).

---

## Tier 1 — Missing from the plan, and they matter

These are load-bearing topics that a serious system design resource cannot omit. None appears
anywhere in the original 21-section tree.

| Gap | Why it matters | Status |
|---|---|---|
| **API design** | REST vs gRPC vs GraphQL, versioning, pagination, error contracts, idempotency keys. The original plan says "identify the APIs" as a *step* but has no section on how to design one. It is the interface every other decision is expressed through. | Missing from plan |
| **Schema migration** | Zero-downtime schema change — expand-contract, dual writes, backfills, and the fact that a migration is a *distributed* operation with partial failure. Enormous in real work, absent from the plan, and the single most common way a deploy causes an outage. | Missing from plan |
| **Batch vs stream processing** | OLTP vs OLAP, ETL, windowing, watermarks, Lambda/Kappa. Half of what a data-heavy system does, and not represented at all. | Missing from plan |
| **SLI / SLO / error budgets** | The vocabulary for deciding *how reliable is reliable enough*. Without it, availability targets are picked by feel. | Missing from plan |
| **Multi-tenancy** | Isolation, noisy neighbours, per-tenant limits and data separation. Almost every B2B system, entirely absent. | Missing from plan |
| **Cost** | Listed as a trade-off axis but has no section. At scale, cost *is* an architectural constraint — it kills more designs than latency does. | Missing from plan |

## Tier 2 — Missing from the plan, narrower but real

| Gap | Why it matters | Status |
|---|---|---|
| **Search as a component** | The plan has "search-engine" as a *problem* but never teaches inverted indexes, ranking, or index/database sync as a component. | Missing from plan |
| **Geospatial indexing** | Geohashing, quadtrees, H3. The plan includes Uber and ride-matching as problems, which cannot be answered without it. | Missing from plan |
| **Probabilistic data structures** | Bloom filters, HyperLogLog, count-min sketch. Common in interviews, and the correct answer to several real problems. | Missing from plan |
| **Storage engine internals** | B-tree vs LSM-tree. The plan covers indexing but not the engine, and the read-heavy/write-heavy distinction between them drives real database choices. | Missing from plan |
| **Serialisation and schema evolution** | Protobuf, Avro, JSON; forward and backward compatibility. Every message you persist is a contract with your future self. | Missing from plan |
| **Load shedding** | Distinct from rate limiting and from backpressure, and routinely conflated with both. See the [pattern catalogue](13-design-patterns/CATALOGUE.md#resilience-patterns). | Missing from plan |
| **Tail-latency techniques** | Hedged requests, request cancellation, tied requests — Dean & Barroso's *The Tail at Scale*. | Missing from plan |
| **Cell-based architecture** | Bounded blast radius by partitioning the whole stack. Modern, and how large providers actually contain failure. | Missing from plan |
| **Fan-out on write vs read** | The decision that defines a social feed's architecture. Only present as a glossary entry. | Missing from plan |
| **Compliance and data residency** | GDPR, PII handling, where data is legally allowed to live. A hard architectural constraint, not a legal footnote. | Missing from plan |
| **Chaos engineering** | Testing distributed systems deliberately. The plan has per-concept "testing" but no discipline section — and untested failover is not failover. | Missing from plan |
| **Feature flags** | Decoupling deploy from release. Named in the [catalogue](13-design-patterns/CATALOGUE.md#deployment-patterns), no page. | Missing from plan |

## Tier 3 — Planned, not yet built

On [ROADMAP.md](ROADMAP.md). Listed here so the two views agree.

**Components** — load balancer ★, cache ★, database ★, queue ★, worker, CDN, API gateway
**Patterns** — batching, retries, circuit breaker, rate limiting, backpressure, sharding ★, replication, async
**Combinations** — the 10 `CORE` pairs in [the matrix](14-component-combinations/MATRIX.md) need pages
**Problems** — 7 of 8 (URL shortener has a scene but no prose)
**Implementations** — 7 of 8
**Judgment** — ADRs, anti-patterns, comparisons, interview guide

## Deferred deliberately

Directory-level topics from the original plan, not yet started, and a decision rather than an
oversight: networking (§01) · architecture styles (§02) · observability (§11) · security (§12) ·
case studies (§17) · design exercises (§16).

Of these, **observability and security are the two whose absence is least defensible** — every
concept page has a "how would you know it broke?" section pointing at a directory that does not
exist yet.

---

## What is genuinely covered

So the gaps are readable against something:

- [Foundations](00-foundations/) — 7 concepts, complete
- [The method](SYSTEM-DESIGN-THINKING.md), [trade-offs](TRADEOFF-FRAMEWORK.md),
  [estimation](ESTIMATION-GUIDE.md), [checklist](DESIGN-CHECKLIST.md)
- [Pattern catalogue](13-design-patterns/CATALOGUE.md) — 101 patterns across 5 families; the 23
  Gang of Four patterns have full entries
- [Combination matrix](14-component-combinations/MATRIX.md) — all 153 component pairs classified
- [Diagram notation](19-diagrams/README.md) and the scene format
- One implementation with measured benchmarks; one scene with 8 versions

## How this page stays honest

It is easy for a gap list to rot into a list of things that were quietly done. Two rules:

1. When a Tier 1 or Tier 2 item is built, it moves to **What is genuinely covered** and the roadmap
   entry is ticked in the same commit.
2. New gaps get added here when noticed, **not** when planned. A gap nobody has written down is
   indistinguishable from coverage.
