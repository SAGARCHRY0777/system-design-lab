---
topic: Real-world problems
category: Real-world problems
difficulty: Beginner → Advanced
---

# Real-world problems

`[BEGINNER → ADVANCED]` · Complete designs, each taken from its first version to its eighth, with the
specific failure that forced every change. Four problems, chosen because each one breaks a rule the
previous one taught you.

---

## Why this section exists

Every other section here explains a component. This one explains what happens when you have to choose
between them under a constraint, which is the only place system design actually happens.

The format is the same every time, and it is deliberate: the
[18-step method](../SYSTEM-DESIGN-THINKING.md) applied end to end, so that by the fourth page you are
reading *differences* rather than re-learning a structure.

> **A design is not a diagram, it is a sequence of forced moves.** Each page below numbers those
> moves V1 to V8 and states the trigger for each — the measurement, the incident or the review that
> made the previous version untenable. A version without a trigger is decoration.

---

## The four worked designs

| Design | Difficulty | The number that decides it | What it forces |
|---|---|---|---|
| [URL shortener](url-shortener/) | `[B → A]` | **100:1** read:write | Cache before replicas; do not design for write scale |
| [Chat system](chat-system/) | `[I → A]` | **1M** held connections | Stateful servers — and every operational assumption re-derived |
| [Notification system](notification-system/) | `[I → A]` | **2,000/s** provider ceiling vs a 6,000/s peak | The queue is mandatory, not an optimisation |
| [Payment system](payment-system/) | `[A]` | **5,000** unknown outcomes a day | Reconciliation as the correctness mechanism |

**Read them in that order.** It is not difficulty ordering, it is *assumption* ordering — each one
removes something the previous page relied on:

```mermaid
flowchart LR
    U["URL SHORTENER<br/><i>stateless · read-heavy<br/>cache everything</i>"]
    C["CHAT<br/><i>servers hold state<br/>idle costs money</i>"]
    N["NOTIFICATION<br/><i>the hard part is<br/>somebody else's system</i>"]
    P["PAYMENT<br/><i>eventual consistency<br/>is not available</i>"]

    U -->|"servers stop being interchangeable"| C
    C -->|"the failing component is not yours"| N
    N -->|"you may not lose one message"| P

    style U fill:#1c6853,stroke:#4fc3a1,color:#e4ecea
    style N fill:#2a2317,stroke:#d9a441,color:#e4ecea
    style P fill:#2b1c17,stroke:#e0705a,color:#e4ecea
```

The URL shortener teaches the chain. The chat system takes away statelessness. The notification
system takes away control of the thing that fails. The payment system takes away eventual
consistency, which by then is the only tool you have left.

---

## What each one uniquely teaches

**[URL shortener](url-shortener/)** — the worked example, and the one to read first. Every scaling
technique appears in the order something forced it: load balancer, replicas, cache, CDN, shards,
queue, second region. Its most useful row is the one that says **120 writes a second is trivial, stop
designing for it**.

**[Chat system](chat-system/)** — the connection-state problem. A WebSocket is not a request, it is a
resident: machine 7 knows something machines 1–6 do not, and rolling deploys, autoscaling and
round-robin balancing all have to be re-derived from scratch. Its sharpest lesson is arithmetic —
**presence costs 130× the entire message path**, which rules the naive design out before anyone
builds it. And a million idle connections is a memory and file-descriptor problem, not a throughput
one, so a CPU-based capacity plan is wrong by an order of magnitude.

**[Notification system](notification-system/)** — fan-out, and then the harder half. Fan-out is a
queue and some workers; *suppression* is the design. Deduplication, because the same event firing
twice at 03:00 is how you lose a user permanently and silently. Per-user rate limits, because the
system being nowhere near its own limits is irrelevant to the person receiving 140 pushes. And the
pairing worth stating unprompted: **dedupe fails open, preferences fail closed** — two identical
looking checks with opposite defaults, because a duplicate is an annoyance and an unwanted send is a
regulatory incident.

**[Payment system](payment-system/)** — the one where you may not be eventually consistent about
money. Idempotency keys, a saga with compensations rather than rollbacks, a double-entry ledger as
the source of truth, and reconciliation against the provider because your record and theirs *will*
diverge. The key insight, and the reason it is last: **you cannot make the external provider
transactional, so the ledger must be reconcilable rather than correct by construction.** Its
throughput is the smallest in this section and its design is the hardest, which is the most
instructive pairing on offer.

---

## How to read one

Each page follows the same spine, so you always know where to look:

| Section | What it answers |
|---|---|
| What it actually is | Why this problem teaches well, in three points |
| Steps 1–5 · Understand | Functional requirements, then the non-functional table where the design is really decided |
| Step 6 · Estimate | The numbers, and — the part that matters — **a table of what each number ruled out** |
| Steps 7–8 · API and data model | The access pattern, and the one decision people get wrong |
| Steps 9–12 · The evolution | V1 → V8, each with its trigger and its cost, with generated diagrams |
| Steps 13–16 · Failure and security | What dies, what happens, and whether it is survivable |
| Steps 17–18 · Trade-offs, 10× / ÷10 | Three trade-offs stated unprompted, then both directions of scale |
| Exercises | Five questions with the answers folded away |
| What it does NOT cover | Named explicitly, because scope you have not named is scope you have not thought about |

**The ÷10 section is the one most worth reading twice.** Knowing what to delete when the problem is
ten times smaller is a rarer skill than knowing what to add when it is ten times larger, and it is
the one that stops you building the large version of a small system.

---

## Diagrams, and the scenes behind them

Every version diagram on these pages is generated from a
[scene file](../19-diagrams/scenes/SCHEMA.md) — one JSON document per problem describing its nodes,
its versions, its request flows and its failures. The same file drives the committed SVGs and the
[interactive lab](https://SAGARCHRY0777.github.io/system-design-lab/), so the picture in the page and
the picture in the app cannot disagree.

```bash
python scripts/check_scenes.py            # no flow crosses an inactive node
python scripts/render_diagrams.py         # regenerate the SVGs after editing a scene
```

Two further scenes exist without a written page yet — [social feed](../19-diagrams/scenes/social-feed.json)
(write-amplified rather than read-dominated, which inverts nearly every URL shortener decision) and
[ticket booking](../19-diagrams/scenes/ticket-booking.json) (the other problem where a stale read is
unacceptable). Both are scrubbable in the lab today. See [GAPS.md](../GAPS.md) for what is missing and
why.

## Related

- [System design thinking](../SYSTEM-DESIGN-THINKING.md) — the 18-step method every page here uses
- [Estimation guide](../ESTIMATION-GUIDE.md) — where all four sets of numbers come from
- [Trade-off framework](../TRADEOFF-FRAMEWORK.md) — how to choose, and how to say why not
- [Design checklist](../DESIGN-CHECKLIST.md) — the short form for a 45-minute discussion
- [ADRs](../ADRs/) — four of the URL shortener's decisions, written up as records
- [Case studies](../17-case-studies/) — the same reasoning applied to ten systems that really exist
- [Diagram notation](../19-diagrams/) — the contract every diagram on these pages obeys
