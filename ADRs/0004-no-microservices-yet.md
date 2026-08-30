---
topic: ADR-0004 No microservices yet
category: Judgment
difficulty: Advanced
---

# ADR-0004: No microservices yet

- **Status** — Accepted
- **Date** — 2026-02
- **Deciders** — Engineering lead · CTO · the on-call rotation, which is everyone

## Context

Six engineers. **One** on-call rotation. Availability target **99.99%**, which is 53 minutes a year.

The [URL shortener](../15-real-world-problems/url-shortener/) is at 1 billion redirects a day across
two regions, and it is a **modular monolith**: one artefact, four modules — `redirect`, `create`,
`analytics`, `abuse` — with boundaries enforced by the build rather than by good intentions. One
schema per module, no cross-module table access, architecture tests in CI that fail the build on a
violation.

It is already deployed as three independently scaled things: the **redirect** role behind its own
autoscaling group, the **create** role behind another, and the **analytics worker** pool from
[ADR-0002](0002-queue-for-click-analytics.md). All three are the *same binary* started with a
different entry point. This detail is the reason the record can be short: **independent scaling did
not require independent deployables**, and it never does.

This proposal has now been raised three times in eighteen months. That is the reason to write it
down. An argument that recurs is an argument that was never actually settled.

## Problem

A recurring proposal to split into five services: `redirect-service`, `url-service`,
`analytics-service`, `user-service`, `abuse-service`.

The arguments for it are real ones and deserve better than dismissal:

- **The scaling profiles genuinely diverge.** Read:write is 100:1. Redirect and create are not the
  same workload and should not scale together.
- **The availability requirements genuinely diverge.** Redirects must survive at 99.99%. The
  analytics dashboard does not.
- **The security posture genuinely diverges.** `abuse` handles blocklists and third-party
  reputation feeds and would benefit from tighter isolation.
- **Boundaries are cheaper to draw early than to retrofit**, and a monolith accretes coupling nobody
  ever pays down.
- **Hiring.** Candidates ask what the stack looks like, and "a monolith" costs us interviews.

The question is not whether those are true. Several are. The question is whether splitting the
deployment unit is the cheapest way to satisfy them, and whether six people can operate the result.

## Decision

**We are not splitting.** We stay on one artefact, run in three roles behind separate autoscaling
groups, with module boundaries enforced by CI.

Concretely, each argument above is answered without a service boundary:

| The argument | How it is satisfied today |
|---|---|
| Divergent scaling profiles | Already satisfied. Same binary, different roles, independent autoscaling groups, independent instance types. Costs nothing and is reversible in an afternoon |
| Divergent availability targets | Already satisfied for analytics — the **queue** in ADR-0002 is the boundary, and an asynchronous boundary is the thing that actually stops availability multiplying. A service boundary would add nothing |
| Divergent security posture for `abuse` | Partially satisfied by module isolation and separate credentials. Genuinely the strongest remaining case, and it is on the trigger list below |
| Boundaries drawn early | Satisfied, and better: they are enforced by the compiler and by architecture tests, where a violation is a **build failure** rather than a runtime error found in production |
| Hiring | Not an architectural constraint. Answered by describing the system honestly, which is more attractive to the engineers we want than a service count |

And the parts of the split that would be actively harmful are named rather than left implied. Five
synchronous services at 99.9% each give roughly **99.5%** availability — about 44 hours a year
against a 53-minute target. Six engineers would own five pipelines, five dashboards sets, five
runbooks and five upgrade cadences. And the `create` seam is transactional: creation writes the link
and the creator-side index in one logical operation, so splitting it buys a saga
([ADR-0003](0003-shard-by-user-id.md) already made that a two-store write; making it a two-service
write as well would compound it).

## Alternatives considered

| Option | Why not | When it would win |
|---|---|---|
| **Full split into five services** | Availability multiplies to ~99.5% against a 99.99% target. Six engineers cannot operate five services. Boundaries would be drawn around nouns — `User`, `Url` — which is the classic mistake, and the create seam is transactional | Teams measurably blocking each other on releases. See the triggers — this is the option that wins when the first trigger fires, and it should |
| **Extract the analytics consumer only** | The **least bad** split available, and still not worth it. The queue already gives it independent scaling and independent failure. A separate repository would add a pipeline, a rotation entry and a version-skew surface, and buy nothing further | The analytics stack needs a different runtime — a JVM streaming framework, a Python model — or a separate team takes ownership of it end to end |
| **Extract `abuse` only** | Tempting for the security argument. But it is called **synchronously** on the create path, so its availability would multiply into creation, and the blocklist check has a hard latency budget | A third party runs it, it must be air-gapped for compliance, or its dependency footprint becomes a liability we do not want in the redirect binary. **The most likely first extraction** |
| **Separate repositories, single deploy** | Merge-conflict relief and none of the isolation, plus version skew between repositories with no network boundary to make the skew visible | Build time is the binding constraint on developer productivity. It is not; our build is four minutes |
| **Serverless functions for the redirect path** | Cold starts on a path with a 100 ms p99 budget, and the cache tier would need a connection model that survives per-invocation lifecycles | Spiky, isolated, stateless workloads. The redirect path is high-volume and steady — the opposite profile |
| **Split and reorganise the team to match** | Conway's Law means this is the *only* honest way to do a split. With six people there are not enough teams to be independent of each other, so the reorganisation would be fictional | Above roughly 20–25 engineers, when there are genuinely separate teams to align boundaries with |
| **Do nothing, and do not write it down** | This is what we did the previous three times, which is why we are having the conversation a fourth time. The cost of not recording a decision is paying for it again | Never. An unrecorded decision is not a decision, it is a mood |

## Trade-offs

| Get | Pay |
|---|---|
| One deploy, one rollback, one place to look at 3am | Everyone ships from one release train. One bad merge blocks the team |
| Real transactions across the create seam | A memory leak in **any** module can take down the process it runs in |
| A stack trace instead of a distributed trace | Module boundaries hold only as long as CI enforces them. The day the architecture tests are disabled, this record's premise expires |
| One on-call rotation, one runbook, one set of dashboards | The team must resist the pull to split for reasons that are not on the trigger list |
| Local development is one process, so onboarding is a day | Perceived staleness in hiring conversations. Real, and named rather than denied |
| **Optionality.** A module is extractable; a merged service is not un-mergeable but nobody ever does it | The extraction cost grows slowly with the codebase, so waiting has a price — bounded by keeping schemas separate |

## Consequences

**Module boundaries must be enforced by the build, permanently.** Architecture tests in CI, package
visibility, one schema per module, no cross-module table access. This is not hygiene, it is the
load-bearing premise: the entire argument of this record is that you can have boundaries without a
network, and that claim is only true while something mechanical checks it.

**Distributed tracing is installed now, not at the split.** It is also how we debug the queue path
from ADR-0002, so it pays for itself immediately — and installing it before a split is the difference
between having a debugging tool and discovering during an incident that you gave up stack traces
without replacing them.

**We maintain the extraction as a permanent dry run.** Separate schemas, no cross-module joins, no
shared mutable state. When a trigger fires, extraction is a data *move* rather than a data
*untangle*, and that difference is the whole cost of the eventual split.

**The redirect role runs in its own process group** so that a memory leak in `create` or `analytics`
cannot exhaust the redirect tier. Same artefact, separate processes, separate limits — most of the
fault isolation people want from services, at none of the price.

**This argument is now settled until a trigger fires**, and the triggers are measured monthly by the
engineering lead. That is the actual output of the record: not "no", but "no, and here is exactly
what would make it yes, and here is who is watching for it".

## Failure modes this introduces

| Failure | What it looks like | Mitigation, or "accepted" |
|---|---|---|
| **Process-level blast radius** | A leak or a runaway query in one module kills the process | Roles run as separate process groups with separate memory limits, so the redirect tier is insulated from the other two. Accepted within a role |
| **Boundary erosion** | Someone adds a cross-module query under deadline pressure. If CI misses it, "modular" quietly stops being true and this record's premise has expired without anyone noticing | Architecture tests, reviewed quarterly. **Treat a disabled architecture test as an incident**, because it is the failure that invalidates the decision rather than merely degrading it |
| **Release train contention** | One bad merge blocks everyone. Grows with headcount | Measured — it is trigger one. The point is that the pain is instrumented rather than tolerated |
| **The trigger fires late** | Extraction begins when the team is most blocked and least able to do it | Monthly measurement with a threshold, so the trigger fires on a trend rather than on a crisis |
| **Recruitment friction** | Candidates read a monolith as a red flag | Accepted, and answered honestly in interviews. A 99.99% service run by six people is a better story than five services run by six people |
| **Argument recurrence** | The proposal returns with new advocates and no new information | This record, and the non-trigger list below. Point at it |

## Revisit when

**This is the entire value of the record.** Everything above is context; the table below is what a
reader six months from now needs. Measured monthly by the engineering lead, reported at the quarterly
review.

| Trigger | Measured how | Threshold |
|---|---|---|
| **Teams block each other on releases** | Median time from merge to production, and releases reverted for a reason unrelated to the change | **> 1 working day**, or **> 2 unrelated reverts a month**, sustained for a quarter. This is the primary trigger and the only one that justifies a general split |
| **Headcount** | Engineers on the team | **> 20**. Below that there are not enough teams for boundaries to align with, and Conway's Law makes fictional boundaries fuse anyway |
| **A module needs a different runtime** | A dependency that cannot live in the main artefact — a GPU, a JVM streaming framework, a native library with a conflicting version | Any. This is a technical constraint rather than a preference, and it is the likeliest way `analytics` leaves |
| **A module needs isolation the process cannot give** | A compliance requirement, a data-residency rule, or a third-party dependency we will not run in the redirect binary | Any. This is how `abuse` leaves, and it is the extraction to do first because it teaches the team what a service costs on something cheap |
| **A module's availability requirement diverges *and* the boundary can be asynchronous** | A stated SLO difference plus a design where the caller does not need the answer | Both conditions. Asynchronous is the load-bearing half — a synchronous split makes availability worse, not better |
| **An acquisition** | A system arrives with its own lifecycle, stack and on-call | Any. It was never going to be one deploy |

### What does **not** reopen this

The non-triggers matter as much as the triggers, because these are the arguments that will actually
be made:

- **"Microservices are the modern way."** Not a constraint. Not a measurement. Not an argument.
- **A performance problem.** Splitting adds network hops to calls that were free. The answer to slow
  is profiling, indexes, the cache from ADR-0001, and horizontal scaling — all of which a monolith
  has.
- **A desire to force interface discipline.** Do it in CI, where a violation is a build failure
  instead of a 3am incident. If we cannot hold a boundary in one process, we will not hold it across
  a network — we will get the same tangle with worse latency and no stack traces.
- **A new hire's previous stack**, a conference talk, or a vendor's reference architecture.
- **A single incident.** An incident tells you which module was at fault; it does not tell you the
  module should have been a service. Ask instead whether the split would have prevented it, and the
  honest answer is usually that it would have turned one clear failure into three ambiguous ones.
- **Hiring.** If the architecture is right for the system, describe it confidently.

---

## Related

- [Monolith vs microservices](../02-architecture/monolith-vs-microservices/) — the availability arithmetic and the team-size table this record applies
- [Monolith vs microservices comparison](../comparisons/monolith-vs-microservices.md) — the deciding question in short form
- [Anti-pattern: premature microservices](../anti-patterns/premature-microservices/) — what this record is preventing
- [Anti-pattern: distributed monolith](../anti-patterns/distributed-monolith/) — the usual result of splitting anyway
- [Availability](../00-foundations/availability/) — why five synchronous 99.9% services are not 99.9%
- [Queue](../06-messaging/queues/) — the asynchronous boundary that already gave us the isolation a split would claim
- [ADR-0002](0002-queue-for-click-analytics.md) — the boundary that made analytics independent without a service
- [ADR index](README.md) · [Glossary](../GLOSSARY.md)
