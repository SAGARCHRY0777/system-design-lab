---
topic: Architecture
category: Architecture
difficulty: Intermediate
concepts: [boundaries, coupling, conways-law, team-topology]
related: [monolith-vs-microservices, availability, api-design, queues]
---

# Architecture

Every other section of this repository is about components — things you add because something broke.
This section is about the **boundaries between them**, which is a different kind of decision, and a
much worse one to get wrong.

A cache can be removed on a Tuesday. A load balancer can be swapped. **A service boundary, once
teams and data have grown around it, is close to permanent** — undoing one means merging two
codebases, two datastores, two on-call rotations and two teams' sense of ownership. Boundaries are
the most expensive and least reversible thing you will decide, and they are routinely decided in a
meeting that was really about something else.

---

## The one decision in this section

| # | Topic | Difficulty | The one thing to take away |
|---|---|---|---|
| 1 | [Monolith vs microservices](monolith-vs-microservices/) ★ | `[I]` | **Start with a modular monolith.** Microservices solve a team-scaling problem, not a performance one. |

More topics belong here — event-driven architecture, layering, the strangler fig migration in its own
right — and are not written yet. What exists is deliberately the one that gets decided earliest and
regretted longest.

## Three claims this section will defend

Stated up front, because they are the parts most treatments get wrong:

**1. Microservices are an organisational solution.** The unit of value is the independent deploy, and
the independent deploy exists so that teams stop blocking each other. If your teams are not blocking
each other, you are paying the full cost of distribution to solve a problem you do not have. Nothing
about splitting a process across a network makes code faster — it makes it slower, by roughly the
cost of a network round trip per hop.

**2. Availability multiplies across synchronous dependencies.** Ten services at 99.9% in a request
path give you 99% — 3.65 days of downtime a year, from components that were each individually fine.
The arithmetic is in [availability](../00-foundations/availability/) and its consequences are the
core of the [monolith page](monolith-vs-microservices/).

**3. The distributed monolith is the worst available outcome.** Services that must be released
together, plus a network between them. You kept every coupling of a monolith and added partial
failure, latency, and the impossibility of a transaction. It is not a rare pathology; it is the
default result of splitting by noun instead of by boundary.

## The heuristic worth memorising

Before you draw a line between two services, ask one question:

> **Must these two things be atomic?**

If yes, they belong in the same service. Splitting them means you have chosen sagas, compensating
transactions and eventual consistency — permanently, for that invariant. That is sometimes the right
choice and it is never a small one, and it is a far better test than the usual ones (bounded
contexts, nouns, "one team one service") because it is the only one whose answer you can check
against the code you already have.

## Related

- [API design](../07-api-design/) — a service boundary *is* an API boundary; the protocol is the cheap half of that decision
- [Availability](../00-foundations/availability/) — why synchronous chains multiply, with the arithmetic
- [Latency](../00-foundations/latency/) — an in-process call and a network call differ by about six orders of magnitude
- [Queues](../06-messaging/queues/) — asynchrony is the only thing that stops availability multiplying
- [Consistency](../00-foundations/consistency/) — what you give up the moment a transaction spans two services
- [Observability](../11-observability/) — distributed tracing stops being optional at the first split
- [Pattern catalogue](../13-design-patterns/CATALOGUE.md) — Strangler Fig, Saga, Bulkhead, Cell-Based Architecture
- [Combination matrix](../14-component-combinations/MATRIX.md) · [System Design Thinking](../SYSTEM-DESIGN-THINKING.md) · [Glossary](../GLOSSARY.md)
