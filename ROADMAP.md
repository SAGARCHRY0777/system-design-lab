---
topic: Roadmap
category: Meta
difficulty: n/a
---

# Roadmap

What exists, what is next, and in what order. Topics not yet written are **absent from the tree
rather than stubbed**, so an empty checkbox here means "not built", never "built badly".

Difficulty: `[B]` beginner · `[I]` intermediate · `[A]` advanced · `[E]` expert
Dependencies are listed where following the wrong order will genuinely not work.

---

## Phase 0 — Spine ✅

The parts everything else references. Done first on purpose: notation decided late means redrawing
every diagram.

- [x] [Diagram notation contract](19-diagrams/README.md) `[B]`
- [x] [Scene schema](19-diagrams/scenes/SCHEMA.md) — one format, two renderers `[I]`
- [x] `scripts/render_diagrams.py` — scene → animated SVG, with `--check` `[I]`
- [x] `scripts/check_scenes.py` · `scripts/check_links.py` `[I]`
- [x] [System Design Thinking](SYSTEM-DESIGN-THINKING.md) — the chain + 18-step method `[B]`
- [x] [Trade-off Framework](TRADEOFF-FRAMEWORK.md) — decision trees `[I]`
- [x] [Estimation Guide](ESTIMATION-GUIDE.md) — worked examples `[B]`
- [x] [Design Checklist](DESIGN-CHECKLIST.md) `[B]`
- [x] [Glossary](GLOSSARY.md) `[B]`
- [x] [Concept dependency graph](19-diagrams/concept-dependency-graph.mmd) `[I]`
- [x] [Concept template](_templates/concept.md) — the 33-section shape every page follows
- [ ] Combination / problem / ADR templates in `_templates/`

## Phase 1 — Visualizer ✅ (v1)

- [x] React + Vite app, hand-rolled SVG, imports scenes directly
- [x] Request-flow animation with per-flow selection
- [x] V1→V8 evolution scrubber with the trigger for each step
- [x] Component toggles with real failure effects
- [x] Bottleneck highlighting
- [x] CI (lint + build) and Pages deploy workflow
- [x] First scene: [url-shortener](19-diagrams/scenes/url-shortener.json), 8 versions, 12 flows, 5 failure modes
- [ ] Keyboard navigation and a reduced-motion still mode
- [ ] Scene picker populated as more systems land

## Phase 2 — Foundations ✅

Everything downstream assumes these. Written in dependency order — see the
[index](00-foundations/) for the reading path.

- [x] [Latency](00-foundations/latency/) `[B]`
- [x] [Throughput](00-foundations/throughput/) `[B]`
- [x] [Scalability](00-foundations/scalability/) `[B]`
- [x] [Availability](00-foundations/availability/) `[B]`
- [x] [Reliability](00-foundations/reliability/) `[B]`
- [x] [Consistency](00-foundations/consistency/) `[I]`
- [x] ★ [CAP theorem + PACELC](00-foundations/cap-theorem/) `[I]`
- [ ] Estimation practice set `[B]` — the guide exists; the exercises do not

Durability is covered inside [reliability](00-foundations/reliability/) rather than as its own page,
because in practice it is never traded alone — always against write latency.

## Phase 3 — Core components

★ = flagship, full 33-section treatment; these are the worked examples of the template.

- [x] ★ [Load balancer](03-load-balancing/fundamentals/) `[B]`
- [x] ★ [Cache](04-caching/fundamentals/) `[B]`
- [x] ★ [Database](05-databases/fundamentals/) `[I]`
- [x] ★ [Queue](06-messaging/queues/) `[I]`
- [ ] Worker `[B]`
- [ ] CDN `[B]`
- [ ] API gateway `[I]`

## Phase 4 — Core patterns

- [ ] Batching `[I]`
- [ ] Retries `[B]`
- [ ] Exponential backoff + jitter `[I]` — *needs retries*
- [ ] Circuit breaker `[I]` — *needs retries*
- [ ] Rate limiting `[I]`
- [ ] Backpressure `[A]`
- [x] ★ [Sharding](05-databases/sharding/) `[A]`
- [x] [Replication](05-databases/replication/) `[I]`
- [ ] Asynchronous processing `[I]`

## Phase 5 — Combinations & patterns

The part most material skips, and the reason this repository exists.

- [x] [Combination matrix](14-component-combinations/MATRIX.md) — **all 153 pairs** classified, every
      CORE/REAL pair with a real system and a public source `[I]`
- [x] [Pattern catalogue](13-design-patterns/CATALOGUE.md) — **101 patterns**, five families; all 23
      Gang of Four with full entries and distributed counterparts `[I]`
- [x] [GAPS.md](GAPS.md) — what the original plan never included, tracked separately from what is
      merely unbuilt

The 10 `CORE` pairs below still need their own pages:

- [ ] Load balancer + cache `[I]`
- [ ] Cache + database `[I]`
- [ ] Queue + workers `[I]`
- [ ] Queue + database `[I]`
- [ ] Load balancer + cache + database `[I]`
- [ ] Batching + queue `[A]`
- [ ] Retry + circuit breaker `[A]`
- [ ] CDN + load balancer + cache `[I]`

## Phase 6 — Real-world problems

Each written V1→V8 with the reason for every change, and each with a scene file so it is scrubbable
in the visualizer.

- [x] URL shortener — scene only, prose pending `[B]`
- [ ] Notification system `[I]`
- [ ] Chat system `[A]`
- [ ] Social feed `[A]`
- [ ] File storage `[I]`
- [ ] Payment system `[E]`
- [ ] Ticket booking `[A]`
- [ ] Video streaming `[A]`

## Phase 7 — Implementations

Python, stdlib-only, with tests and **executed** benchmarks.

- [ ] Rate limiter — token bucket + sliding window `[I]`
- [ ] Consistent hashing `[A]`
- [ ] Cache — LRU + TTL `[I]`
- [ ] Circuit breaker `[I]`
- [ ] Worker pool `[I]`
- [ ] Load balancer — the algorithms `[B]`
- [ ] Message queue `[A]`
- [ ] Distributed lock `[E]`

## Phase 8 — Judgment

- [ ] ADRs with the template and 3 worked records
- [ ] Anti-patterns: premature microservices, cache everything, retry storm, distributed monolith,
      queue without backpressure, no idempotency, no timeout
- [ ] Comparisons: monolith vs microservices · SQL vs NoSQL · Kafka vs RabbitMQ ·
      strong vs eventual · polling vs websocket
- [ ] Interview guide: 5 / 15 / 30 / 45-minute approaches

---

## Deferred

Directory and template only for now — real content in a later pass. Listed so the absence is a
decision rather than an oversight.

Networking (§01) · architecture styles (§02) · observability (§11) · security (§12) ·
case studies (§17) · design exercises (§16)

---

## How to add a topic

1. Copy the relevant template from `_templates/`
2. Write it — including the four-line chain block, which is not optional
3. If it has motion or evolution, add a scene in [19-diagrams/scenes/](19-diagrams/scenes/) and run
   `python scripts/render_diagrams.py`
4. Cross-link it from [GLOSSARY.md](GLOSSARY.md) and from every related concept
5. Run `python scripts/check_links.py` — a dead link is a hole in the knowledge graph
6. Tick the box here
