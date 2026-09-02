#!/usr/bin/env python3
"""Generate the complete component-combination matrix.

Every pair of components is classified. Not a curated selection -- all
C(18,2) = 153 of them, so coverage is provable rather than asserted, and the
gaps are visible instead of implied.

Literal "all permutations" would be 2^18 = 262,144 subsets, almost all of them
meaningless (CDN + distributed lock). Pairs are the level where exhaustiveness
is both achievable and useful; meaningful triples are listed separately because
they are the ones real architectures are actually made of.

Every CORE and REAL pair carries a real system and a public source, because a
combination nobody ships is a thought experiment, not a pattern.

    python scripts/gen_combination_matrix.py            # write MATRIX.md
    python scripts/gen_combination_matrix.py --check    # fail if stale
"""

from __future__ import annotations

import argparse
import sys
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "14-component-combinations" / "MATRIX.md"

# --------------------------------------------------------------------------- #
# Components                                                                   #
# --------------------------------------------------------------------------- #

COMPONENTS = [
    ("client",    "Client",            "Browser, mobile app, or calling service"),
    ("cdn",       "CDN / Edge",        "Geographically distributed cache"),
    ("lb",        "Load Balancer",     "Spreads requests across servers"),
    ("gateway",   "API Gateway",       "Single entry point: auth, routing, quotas"),
    ("service",   "Service",           "Stateless application server"),
    ("cache",     "Cache",             "Fast in-memory copy; safe to lose"),
    ("db",        "Database",          "Durable primary store"),
    ("replica",   "Read Replica",      "Read-only copy of the primary"),
    ("shard",     "Shard",             "Horizontal partition of the data"),
    ("queue",     "Queue",             "Point-to-point async work buffer"),
    ("stream",    "Stream / Log",      "Ordered, replayable, multi-consumer log"),
    ("worker",    "Worker",            "Consumes async work"),
    ("blob",      "Object Storage",    "Large immutable files"),
    ("search",    "Search Index",      "Inverted index for text and facets"),
    ("ratelimit", "Rate Limiter",      "Caps consumption per client"),
    ("breaker",   "Circuit Breaker",   "Stops calling a failing dependency"),
    ("lock",      "Distributed Lock",  "Mutual exclusion across processes"),
    ("discovery", "Service Discovery", "Finds healthy instances"),
]

NAME = {k: n for k, n, _ in COMPONENTS}
IDS = [k for k, _, _ in COMPONENTS]

# --------------------------------------------------------------------------- #
# Classification                                                               #
#                                                                              #
#   CORE  gets its own full page -- the combinations worth studying            #
#   REAL  genuinely used; documented here with a real system                   #
#   SITU  occurs, but situational or niche                                     #
#   ANTI  a known mistake; documented so it is recognised                      #
#   NONE  no meaningful direct interaction (the honest majority)               #
# --------------------------------------------------------------------------- #

CORE, REAL, SITU, ANTI = "CORE", "REAL", "SITU", "ANTI"

# (a, b): (class, what emerges, real system, source)
PAIRS: dict[tuple[str, str], tuple[str, str, str, str]] = {
    ("lb", "cache"): (
        CORE,
        "Where the cache sits decides whether it works. Per-server caches mean each server "
        "misses independently and hit rate falls as the fleet grows; a shared cache keeps one "
        "hit rate at any fleet size.",
        "Facebook",
        "Scaling Memcache at Facebook (NSDI '13)",
    ),
    ("cache", "db"): (
        CORE,
        "The canonical latency fix, and the source of the canonical bug: invalidation. Adds "
        "staleness bounded by TTL, plus thundering herd when a hot key expires.",
        "Facebook, Twitter, essentially every read-heavy product",
        "Scaling Memcache at Facebook (NSDI '13)",
    ),
    ("queue", "worker"): (
        CORE,
        "Decouples arrival rate from processing rate, so a spike becomes a backlog instead of "
        "an outage. Buys at-least-once delivery, which forces idempotency.",
        "Celery/Sidekiq shops; AWS SQS + Lambda",
        "AWS SQS documentation",
    ),
    ("queue", "db"): (
        CORE,
        "The dual-write problem: enqueue and commit are two systems and cannot share a "
        "transaction. Solved by the transactional outbox, not by ordering the two calls "
        "carefully.",
        "Debezium / CDC-based pipelines",
        "Kleppmann, Designing Data-Intensive Applications, ch. 11",
    ),
    ("cdn", "lb"): (
        CORE,
        "The CDN absorbs cacheable traffic before it reaches you; the load balancer only sees "
        "the misses. Attacks the one term nothing else can touch: distance.",
        "Netflix Open Connect",
        "Netflix Open Connect appliance documentation",
    ),
    ("breaker", "service"): (
        CORE,
        "Retries alone finish off a struggling dependency. The breaker is what makes retrying "
        "safe -- it converts 'slow' back into 'fast failure', which is the only mode you can "
        "route around.",
        "Netflix Hystrix",
        "Netflix TechBlog, Hystrix",
    ),
    ("ratelimit", "lb"): (
        CORE,
        "Limit at the edge or per-server? Per-server means N servers each allow the full "
        "limit. Shared state at the edge is correct but adds a hop to every request.",
        "Stripe API rate limits",
        "Stripe engineering blog, Scaling your API with rate limiters",
    ),
    ("db", "replica"): (
        CORE,
        "Read scale, at the cost of replication lag -- which produces the most common "
        "consistency bug there is: a user writes, reads, and gets a 404 on their own record.",
        "Standard Postgres/MySQL deployments",
        "PostgreSQL streaming replication docs",
    ),
    ("db", "shard"): (
        CORE,
        "Write scale and unbounded storage, paid for with the loss of cross-shard joins and a "
        "shard key that is effectively permanent.",
        "Discord message storage; Vitess at YouTube",
        "Discord blog: How Discord Stores Trillions of Messages",
    ),
}

PAIRS.update({
    ("cdn", "blob"): (
        REAL,
        "Origin for static assets. The CDN serves; object storage stores. Cheapest possible "
        "delivery path for immutable content.",
        "Most media delivery; S3 + CloudFront",
        "AWS CloudFront + S3 documentation",
    ),
    ("service", "cache"): (
        REAL,
        "Read-through or cache-aside. Cache-aside puts invalidation in application code, which "
        "is where invalidation bugs live.",
        "Ubiquitous",
        "Kleppmann, DDIA ch. 1",
    ),
    ("service", "db"): (
        REAL,
        "The base case. Connection pool size, not database capacity, is usually the real "
        "throughput ceiling.",
        "Every system",
        "Little's Law",
    ),
    ("service", "queue"): (
        REAL,
        "Producer side. Moving work off the request path is the single largest perceived "
        "latency win available.",
        "Ubiquitous",
        "AWS SQS documentation",
    ),
    ("stream", "worker"): (
        REAL,
        "Unlike a queue, the log is replayable and multi-consumer -- so a bug can be fixed by "
        "reprocessing from an offset rather than by recovering lost messages.",
        "LinkedIn (Kafka's origin)",
        "Kreps, The Log (LinkedIn engineering, 2013)",
    ),
    ("stream", "db"): (
        REAL,
        "Change data capture: the database's replication log becomes the event stream, which "
        "removes the dual-write problem entirely.",
        "Debezium; Netflix DBLog",
        "Netflix TechBlog, DBLog",
    ),
    ("stream", "cache"): (
        REAL,
        "Cache invalidation driven by the change log instead of by application code. Turns a "
        "correctness problem into a plumbing problem.",
        "Facebook's cache invalidation pipeline",
        "Scaling Memcache at Facebook (NSDI '13)",
    ),
    ("db", "search"): (
        REAL,
        "The database owns the truth; the index owns the query. They are always slightly out of "
        "sync, and the sync mechanism is where the bugs are.",
        "Most e-commerce catalogues",
        "Elasticsearch documentation",
    ),
    ("worker", "db"): (
        REAL,
        "Async writes. Workers can overwhelm a primary that the request path was politely "
        "rate-limited against -- the queue removed the natural backpressure.",
        "Common failure in batch pipelines",
        "Kleppmann, DDIA ch. 11",
    ),
    ("worker", "blob"): (
        REAL,
        "Large payloads go to object storage; the queue carries only a pointer. Avoids message "
        "size limits and keeps the queue fast.",
        "Claim-check pattern; AWS SQS extended client",
        "Azure Architecture Center, Claim-Check pattern",
    ),
    ("gateway", "ratelimit"): (
        REAL,
        "Quota enforcement at the single entry point, where the identity of the caller is "
        "already known.",
        "Kong, AWS API Gateway",
        "AWS API Gateway throttling documentation",
    ),
    ("gateway", "service"): (
        REAL,
        "One public entry point in front of many private services. Also becomes a single point "
        "of failure and a deployment bottleneck if it holds business logic.",
        "Netflix Zuul",
        "Netflix TechBlog, Zuul",
    ),
    ("lb", "discovery"): (
        REAL,
        "The load balancer needs to know which instances exist and which are healthy. In "
        "autoscaled fleets that list changes constantly.",
        "Consul, Kubernetes Services",
        "Kubernetes Service documentation",
    ),
    ("lb", "service"): (
        REAL,
        "Requires the service to be stateless. Sessions in local memory break load balancing, "
        "deploys and failover simultaneously.",
        "Every horizontally scaled tier",
        "Twelve-Factor App, factor VI",
    ),
    ("shard", "lock"): (
        REAL,
        "Resharding needs mutual exclusion or two nodes will move the same key. One of the few "
        "places a distributed lock is genuinely warranted.",
        "Vitess resharding",
        "Vitess resharding documentation",
    ),
    ("shard", "replica"): (
        CORE,
        "Shard for write scale, replicate each shard for read scale and availability. The "
        "standard large-database shape -- and now every shard has its own failover story.",
        "Vitess; MongoDB sharded clusters",
        "MongoDB sharded cluster documentation",
    ),
    ("cache", "queue"): (
        CORE,
        "The dangerous one. A cache miss storm and a queue backlog amplify each other: misses "
        "enqueue work, the backlog delays cache population, which produces more misses.",
        "Common cascading-failure shape",
        "Google SRE Book, ch. 22 (Addressing Cascading Failures)",
    ),
    ("cache", "replica"): (
        REAL,
        "Two staleness windows stacked: cache TTL plus replication lag. Users can observe data "
        "older than either bound alone.",
        "Common read-heavy stack",
        "Kleppmann, DDIA ch. 5",
    ),
    ("ratelimit", "breaker"): (
        REAL,
        "Rate limiting protects you from callers; the circuit breaker protects you from "
        "dependencies. Inbound and outbound halves of the same idea.",
        "Netflix Hystrix + Zuul",
        "Netflix TechBlog",
    ),
    ("breaker", "queue"): (
        REAL,
        "When the breaker opens, work can be parked on a queue instead of dropped -- so the "
        "outage degrades to a delay.",
        "Common resilience shape",
        "Google SRE Book, ch. 22",
    ),
    ("client", "cdn"): (
        REAL,
        "First hop for most user traffic. Everything downstream only sees what the edge could "
        "not answer.",
        "Any consumer product at scale",
        "Netflix Open Connect",
    ),
    ("client", "lb"): (
        REAL,
        "First hop when there is no edge tier. DNS decides which load balancer, which makes DNS "
        "part of your availability calculation.",
        "Standard web architecture",
        "AWS ELB documentation",
    ),
    ("blob", "db"): (
        REAL,
        "Metadata in the database, bytes in object storage. Storing large blobs in the database "
        "inflates backups and destroys buffer-cache efficiency.",
        "Standard media architecture",
        "AWS S3 best practices",
    ),
    ("search", "stream"): (
        REAL,
        "Index updates fed from the change log rather than by dual-writing from the "
        "application.",
        "Common CDC-to-Elasticsearch pipeline",
        "Debezium documentation",
    ),
    ("lock", "db"): (
        SITU,
        "Often unnecessary: a database transaction or a unique constraint usually does the job "
        "with fewer moving parts and no lease-expiry hazard.",
        "Frequently over-applied",
        "Kleppmann, How to do distributed locking (2016)",
    ),
    ("discovery", "service"): (
        REAL,
        "Services register; callers resolve. In Kubernetes this is DNS plus endpoint objects "
        "rather than a separate system.",
        "Kubernetes, Consul",
        "Kubernetes Service documentation",
    ),
    ("cdn", "cache"): (
        SITU,
        "Two cache layers with independent TTLs. Debugging staleness means reasoning about both "
        "at once, and the edge TTL usually dominates.",
        "Multi-layer caching setups",
        "Fastly / Cloudflare caching docs",
    ),
    ("gateway", "breaker"): (
        REAL,
        "One place to stop calls to a failing downstream, rather than every caller implementing "
        "it separately and inconsistently.",
        "Netflix Zuul + Hystrix",
        "Netflix TechBlog",
    ),
    ("queue", "stream"): (
        SITU,
        "Frequently confused. A queue deletes on ack and is point-to-point; a log retains and "
        "supports many independent consumers. Picking wrongly is a common and expensive mistake.",
        "Kafka vs RabbitMQ decisions",
        "Kreps, The Log",
    ),
    ("worker", "lock"): (
        REAL,
        "Ensures only one worker handles a given key. Often replaceable by partitioning the key "
        "space, which needs no lock at all.",
        "Kafka consumer group partition assignment",
        "Kafka documentation",
    ),
    ("client", "ratelimit"): (
        REAL,
        "A limiter that says no without saying when guarantees an immediate retry. 429 plus "
        "Retry-After is the contract.",
        "Stripe, GitHub APIs",
        "GitHub REST API rate limit documentation",
    ),
})

# Known mistakes -- documented so they are recognised, not so they are copied.
PAIRS.update({
    ("cache", "lock"): (
        ANTI,
        "Locking to prevent a thundering herd usually serialises every reader behind one lock. "
        "Request coalescing or a probabilistic early refresh solves it without the contention.",
        "Common over-correction",
        "Vattani et al., Optimal Probabilistic Cache Stampede Prevention (VLDB 2015)",
    ),
    ("gateway", "db"): (
        ANTI,
        "A gateway reaching a database directly means business logic has leaked into the edge "
        "tier, which then cannot be deployed independently.",
        "Distributed-monolith smell",
        "Richardson, Microservices Patterns",
    ),
    ("shard", "search"): (
        ANTI,
        "Fanning a search across every shard makes latency the slowest shard's latency, every "
        "time. Use a dedicated index instead.",
        "Common scatter-gather trap",
        "Dean & Barroso, The Tail at Scale (CACM 2013)",
    ),
})


def classify(a: str, b: str):
    """Look up a pair in either order.

    The relation is symmetric, so a key written one way round must not be
    findable while the other resolves to something different. That happened:
    ("breaker","service") was CORE and ("service","breaker") was a REAL entry
    added "for symmetry", so the canonical lookup returned REAL while the grid
    -- which probes both orderings -- drew CORE in one cell and REAL in its
    mirror. One pair, two classifications, in the same table.

    The duplicate is gone; this asserts it cannot come back.
    """
    fwd, rev = PAIRS.get((a, b)), PAIRS.get((b, a))
    if fwd is not None and rev is not None and fwd != rev:
        raise ValueError(
            f"pair ({a}, {b}) is declared twice with different values -- "
            "the relation is symmetric, so declare it once"
        )
    return fwd or rev


# Triples that real architectures are actually made of.
TRIPLES = [
    ("lb+cache+db", ["lb", "cache", "db"], CORE,
     "The default read-heavy web stack. Each element solves the problem the previous one "
     "created.", "Almost every consumer web product", "Scaling Memcache at Facebook"),
    ("cdn+lb+cache", ["cdn", "lb", "cache"], CORE,
     "Three cache layers at three distances. Debugging staleness means reasoning about all "
     "three TTLs together.", "Netflix, Cloudflare-fronted products", "Netflix Open Connect"),
    ("queue+worker+db", ["queue", "worker", "db"], CORE,
     "The async write pipeline. At-least-once delivery makes idempotency mandatory, not "
     "optional.", "Stripe webhook processing", "Stripe idempotency documentation"),
    ("cache+queue+db", ["cache", "queue", "db"], CORE,
     "Write-behind caching. Fastest writes available, and the only shape here that can lose "
     "acknowledged data.", "High-write telemetry systems", "Kleppmann, DDIA ch. 11"),
    ("shard+replica+lb", ["shard", "replica", "lb"], REAL,
     "Full database scale-out: partitioned for writes, replicated for reads, routed by a "
     "shard-aware layer.", "Vitess at YouTube", "Vitess documentation"),
    ("retry+breaker+queue", ["breaker", "queue", "worker"], CORE,
     "The resilience triad. Retry without a breaker is a retry storm; a breaker without a queue "
     "drops work that could have waited.", "Netflix Hystrix + SQS-style buffers",
     "Google SRE Book ch. 22"),
    ("stream+worker+search", ["stream", "worker", "search"], REAL,
     "CDC-driven index maintenance. Removes the dual write between database and index.",
     "Debezium to Elasticsearch", "Debezium documentation"),
    ("gateway+ratelimit+breaker", ["gateway", "ratelimit", "breaker"], REAL,
     "The edge policy tier: who may call, how often, and what happens when downstream is sick.",
     "Netflix Zuul", "Netflix TechBlog"),
]


def build() -> str:
    total = len(list(combinations(IDS, 2)))
    buckets = {CORE: [], REAL: [], SITU: [], ANTI: [], "NONE": []}
    for a, b in combinations(IDS, 2):
        hit = classify(a, b)
        buckets[hit[0] if hit else "NONE"].append((a, b, hit))

    L = []
    L.append("<!-- GENERATED by scripts/gen_combination_matrix.py -- do not edit by hand. -->")
    L.append("---")
    L.append("topic: Component Combination Matrix")
    L.append("category: Combinations")
    L.append("difficulty: Intermediate")
    L.append("---")
    L.append("")
    L.append("# Component Combination Matrix")
    L.append("")
    # The four classifications, and why the ANTI ones justify the page.
    L.append("```mermaid")
    L.append("flowchart LR")
    L.append('    C["18 components"] --> P["153 unordered pairs<br/>every one classified"]')
    L.append('    P --> A1["CORE · the pairing is the point"]')
    L.append('    P --> A2["REAL · common, with a caveat"]')
    L.append('    P --> A3["RARE · defensible, narrow"]')
    L.append('    P --> A4["ANTI · looks reasonable, is not"]')
    L.append('    A4 --> N["The ANTI cells are why this exists.<br/>A catalogue listing only what WORKS<br/>teaches that everything works."]')
    L.append("```")
    L.append("")
    L.append(f"Every pair of {len(IDS)} components — all **{total}** of them — classified. Not a "
             "curated selection, so coverage is provable and the gaps are visible.")
    L.append("")
    L.append("Literal *all permutations* would be 2<sup>18</sup> = 262,144 subsets, almost all "
             "meaningless (CDN + distributed lock). Pairs are the level at which exhaustiveness "
             "is both achievable and useful. [Meaningful triples](#meaningful-triples) are listed "
             "separately, because those are what real architectures are made of.")
    L.append("")
    L.append("Every `CORE` and `REAL` pair names a real system and a public source. **A "
             "combination nobody ships is a thought experiment, not a pattern.**")
    L.append("")
    L.append("| Class | Meaning | Count |")
    L.append("|---|---|---|")
    L.append(f"| ● **CORE** | Worth a full page of its own | {len(buckets[CORE])} |")
    L.append(f"| ○ **REAL** | Genuinely used; documented below | {len(buckets[REAL])} |")
    L.append(f"| · **SITU** | Occurs, but situational or often confused | {len(buckets[SITU])} |")
    L.append(f"| ⚠ **ANTI** | A known mistake — documented so it is recognised | {len(buckets[ANTI])} |")
    L.append(f"| — **none** | No meaningful direct interaction | {len(buckets['NONE'])} |")
    L.append(f"| | **total** | **{total}** |")
    L.append("")
    L.append("That the honest majority is *none* is the useful part. A matrix with no empty cells "
             "would mean the classification was not doing any work.")
    L.append("")

    # Grid
    L.append("## The grid")
    L.append("")
    L.append("Read either direction; the relation is symmetric.")
    L.append("")
    short = {k: k[:4] for k in IDS}
    L.append("| |" + "|".join(f" `{short[c]}` " for c in IDS) + "|")
    L.append("|---|" + "|".join("---" for _ in IDS) + "|")
    sym = {CORE: "●", REAL: "○", SITU: "·", ANTI: "⚠"}
    for a in IDS:
        row = [f"**`{short[a]}`**"]
        for b in IDS:
            if a == b:
                row.append("▪")
                continue
            hit = classify(a, b)
            row.append(sym.get(hit[0], "") if hit else "")
        L.append("| " + " | ".join(row) + " |")
    L.append("")
    L.append("| Key | | | | |")
    L.append("|---|---|---|---|---|")
    L.append("| ● CORE | ○ REAL | · SITU | ⚠ ANTI | ▪ self |")
    L.append("")

    L.append("## Components")
    L.append("")
    L.append("| id | Component | What it is |")
    L.append("|---|---|---|")
    for k, n, d in COMPONENTS:
        L.append(f"| `{k[:4]}` | {n} | {d} |")
    L.append("")

    for cls, title, blurb in [
        (CORE, "● Core combinations", "These get their own page. Each one is a step in "
         "[the chain](../SYSTEM-DESIGN-THINKING.md#part-1--the-chain) — a problem created by the "
         "previous component."),
        (REAL, "○ Real combinations", "Genuinely shipped, documented here rather than given a "
         "page of their own."),
        (SITU, "· Situational", "Occurs, but niche — or commonly confused with something else."),
        (ANTI, "⚠ Anti-patterns", "Documented so they are recognised in a design review, not so "
         "they are copied."),
    ]:
        rows = buckets[cls]
        if not rows:
            continue
        L.append(f"## {title}")
        L.append("")
        L.append(blurb)
        L.append("")
        L.append("| Combination | What emerges | Real system | Source |")
        L.append("|---|---|---|---|")
        for a, b, hit in sorted(rows, key=lambda r: (NAME[r[0]], NAME[r[1]])):
            _, what, who, src = hit
            L.append(f"| **{NAME[a]} + {NAME[b]}** | {what} | {who} | {src} |")
        L.append("")

    L.append("## Meaningful triples")
    L.append("")
    L.append("Pairs are where the interactions are; triples are where the architectures are.")
    L.append("")
    L.append("| Combination | What emerges | Real system | Source |")
    L.append("|---|---|---|---|")
    for name, parts, cls, what, who, src in TRIPLES:
        mark = "●" if cls == CORE else "○"
        label = " + ".join(NAME[p] for p in parts)
        L.append(f"| {mark} **{label}** | {what} | {who} | {src} |")
    L.append("")

    L.append("## Pairs with no meaningful interaction")
    L.append("")
    L.append(f"The remaining **{len(buckets['NONE'])}** pairs. Listed rather than omitted, so "
             "that 'not covered' is distinguishable from 'not applicable'.")
    L.append("")
    none_rows = [f"{NAME[a]} + {NAME[b]}" for a, b, _ in buckets["NONE"]]
    for i in range(0, len(none_rows), 3):
        L.append("- " + " · ".join(none_rows[i:i + 3]))
    L.append("")

    L.append("## Related")
    L.append("")
    L.append("- [System Design Thinking](../SYSTEM-DESIGN-THINKING.md) — the chain these sit on")
    L.append("- [Trade-off Framework](../TRADEOFF-FRAMEWORK.md)")
    L.append("- [Glossary](../GLOSSARY.md)")
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    content = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    current = OUT.read_text(encoding="utf-8") if OUT.exists() else None

    if args.check:
        if current != content:
            print("MATRIX.md is stale -- run: python scripts/gen_combination_matrix.py")
            return 1
        print("MATRIX.md matches the generator")
        return 0

    OUT.write_text(content, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
