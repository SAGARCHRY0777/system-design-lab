---
topic: Comparisons
category: Comparison
difficulty: Intermediate
---

# Comparisons

`[INTERMEDIATE]` · Six recurring choices, each led by the one question that actually decides it — because a feature table compares products and a deciding question compares *your requirements*.

---

## Why these pages are not feature tables

Search for any of these comparisons and you will find a grid: rows of capabilities, ticks and
crosses, and a conclusion that says "it depends on your use case". That is true and useless. It
leaves the reader exactly where they started, holding a longer list.

The problem is structural. **A feature table compares the technologies. The decision is a property of
your requirements**, and it is almost always settled by one question — asked before any feature is
examined. Once that question is answered, most of the grid becomes irrelevant, and the rows that
remain are details rather than decisions.

So every page here leads with its deciding question and only then shows a table, for the cases where
the question genuinely does not settle it.

| Comparison | The question that actually decides it |
|---|---|
| [Monolith vs microservices](monolith-vs-microservices.md) | **Which two teams are blocking each other, and on what?** |
| [SQL vs NoSQL](sql-vs-nosql.md) | **Do you need transactions across rows?** |
| [Kafka vs RabbitMQ](kafka-vs-rabbitmq.md) | **Will you ever want the data twice?** |
| [Strong vs eventual consistency](strong-vs-eventual-consistency.md) | **Is there an invariant two concurrent writers could break?** |
| [Polling vs WebSocket](polling-vs-websocket.md) | **How does the update rate compare with the freshness requirement?** |
| [Redis vs Memcached](redis-vs-memcached.md) | **Do you need data structures and persistence, or just a fast map?** |

## Every page has a "when neither is the answer" section

It is not filler. It is frequently where the real answer lives, and it is the section a feature table
structurally cannot contain — because a grid with two columns has already assumed the answer is one
of the two.

A few examples of what turns up there: the answer to *monolith or microservices* is usually a modular
monolith with two extracted services; the answer to *Kafka or RabbitMQ* is often a database table
with `SKIP LOCKED`; the answer to *strong or eventual* is nearly always **both**, chosen per
operation rather than per system; and the answer to *Redis or Memcached* is sometimes that the
problem is a missing index rather than a cache.

**A comparison that cannot produce the answer "neither" is a shortlist, not an analysis.**

## The order these decisions come in

Technology comes last, deliberately. Choices flow downhill — requirements, then constraints, then
scale, then the non-functional targets, then operational capacity, and only then a product name. Two
of the six pages here are really requirement questions wearing technology labels: *strong vs eventual
consistency* is a property of your invariants, and *monolith vs microservices* is a property of your
organisation. Neither is settled by anything a vendor publishes.

See [the trade-off framework](../TRADEOFF-FRAMEWORK.md) for the full ordering, and in particular for
the discipline these pages apply: for every option, name the condition under which it would win.

## Related

- [Trade-off framework](../TRADEOFF-FRAMEWORK.md) — the order of operations and the seven axes
- [System design thinking](../SYSTEM-DESIGN-THINKING.md) — the method the questions come from
- [ADRs](../ADRs/) — how to record the answer, with the condition that would reverse it
- [Anti-patterns](../anti-patterns/) — what each of these choices looks like when made by default
- [Component combinations](../14-component-combinations/MATRIX.md) — how the winners behave together
- [Coverage gaps](../GAPS.md) · [Glossary](../GLOSSARY.md)
