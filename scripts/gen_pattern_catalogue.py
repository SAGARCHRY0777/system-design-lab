#!/usr/bin/env python3
"""Generate the complete pattern catalogue.

Five families, every pattern in each listed -- including all 23 Gang of Four
patterns, which most system design material omits on the grounds that they are
"just OO". That omission loses the most useful thing about them.

The bridge is the point of this document. Nearly every GoF pattern has a
distributed counterpart, and the counterpart is harder for the same reason every
time: the single-process version quietly relies on shared memory and one clock,
and the distributed version has neither.

    python scripts/gen_pattern_catalogue.py            # write CATALOGUE.md
    python scripts/gen_pattern_catalogue.py --check    # fail if stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from patterns_data import GOF_BEHAVIORAL, GOF_CREATIONAL, GOF_STRUCTURAL  # noqa: E402

# Full entries for the four non-GoF families. Optional on purpose: the module is
# written separately, and until it exists those families fall back to the
# name+description tuples below. A missing enrichment should degrade the page,
# never break the build.
try:
    import patterns_data_extra as EXTRA  # noqa: E402
except ImportError:
    EXTRA = None

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "13-design-patterns" / "CATALOGUE.md"
# The visualizer imports this, so the app and the markdown cannot drift.
OUT_JSON = ROOT / "13-design-patterns" / "patterns.json"

EIP = [
    ("Message Channel", "A named conduit between producer and consumer", "queue, topic"),
    ("Point-to-Point Channel", "Exactly one consumer receives each message", "SQS, RabbitMQ queue"),
    ("Publish-Subscribe", "Every subscriber receives every message", "SNS, Kafka topic"),
    ("Message Router", "Route by content or header", "Kafka partitioner, exchange bindings"),
    ("Content-Based Router", "Route on payload contents", "event routing rules"),
    ("Message Translator", "Convert between formats", "schema registry, adapters"),
    ("Message Filter", "Discard messages that do not match", "subscription filters"),
    ("Splitter", "One message into many", "batch fan-out"),
    ("Aggregator", "Many messages into one", "windowed aggregation"),
    ("Resequencer", "Restore order after out-of-order delivery", "sequence numbers"),
    ("Scatter-Gather", "Broadcast, then combine responses", "federated search"),
    ("Dead Letter Channel", "Park messages that cannot be processed", "DLQ"),
    ("Idempotent Receiver", "Safe to receive the same message twice", "idempotency keys"),
    ("Competing Consumers", "Many workers on one queue", "consumer groups"),
    ("Claim Check", "Store the payload, pass a reference", "S3 pointer in the message"),
    ("Guaranteed Delivery", "Message survives a crash", "persistent queues, WAL"),
    ("Transactional Outbox", "Write and publish atomically", "outbox table + CDC"),
]

DISTRIBUTED = [
    ("Saga", "Long-lived transaction as compensable local steps", "Advanced"),
    ("CQRS", "Separate read and write models", "Advanced"),
    ("Event Sourcing", "State as an append-only event log", "Advanced"),
    ("Transactional Outbox", "Atomically commit and publish", "Advanced"),
    ("Change Data Capture", "The replication log becomes the event stream", "Advanced"),
    ("Leader Election", "One node coordinates", "Expert"),
    ("Consensus (Raft/Paxos)", "Agreement despite failures", "Expert"),
    ("Quorum", "Majority read/write overlap", "Advanced"),
    ("Consistent Hashing", "Minimal reshuffling when nodes change", "Advanced"),
    ("Vector Clocks", "Track causality without a global clock", "Expert"),
    ("CRDT", "Data types that merge without coordination", "Expert"),
    ("Two-Phase Commit", "Atomic commit across nodes — and why it blocks", "Advanced"),
    ("Gossip", "Epidemic state dissemination", "Advanced"),
    ("Lease / Fencing Token", "Ownership that survives a stalled holder", "Expert"),
    ("Read Repair", "Fix stale replicas on read", "Advanced"),
    ("Hinted Handoff", "Hold writes for a node that is down", "Advanced"),
    ("Merkle Tree", "Cheaply find which replicas diverged", "Expert"),
]

RESILIENCE = [
    ("Retry with backoff + jitter", "Survive transient faults without synchronising clients"),
    ("Circuit Breaker", "Stop calling a failing dependency"),
    ("Bulkhead", "Isolate pools so one failure cannot exhaust everything"),
    ("Timeout", "Convert 'slow' into 'failed', the only mode you can handle"),
    ("Rate Limiting", "Cap what any one caller may consume"),
    ("Load Shedding", "Drop low-value work to protect high-value work"),
    ("Backpressure", "Tell producers to slow down instead of buffering forever"),
    ("Graceful Degradation", "Serve a reduced feature set rather than nothing"),
    ("Hedged Request", "Duplicate after p95, take the first answer — buys tail latency"),
    ("Health Check / Heartbeat", "Detect a dead instance before users do"),
    ("Cell-Based Architecture", "Partition the stack so failure has a bounded blast radius"),
    ("Chaos Engineering", "Inject failure deliberately — untested failover is not failover"),
]

DEPLOYMENT = [
    ("Blue-Green", "Two identical environments, flip traffic between them"),
    ("Canary", "Route a small percentage to the new version first"),
    ("Rolling Update", "Replace instances gradually"),
    ("Feature Flag", "Decouple deploying code from releasing behaviour"),
    ("Strangler Fig", "Replace a legacy system incrementally"),
    ("Expand-Contract", "Zero-downtime schema change in three deploys"),
    ("Sidecar", "Cross-cutting concerns in a co-located process"),
    ("Ambassador", "Proxy outbound calls on behalf of the application"),
    ("Backend-for-Frontend", "A tailored API per client type"),
]

GOF_GROUPS = [
    ("Creational", "How objects get made.", GOF_CREATIONAL),
    ("Structural", "How objects are composed.", GOF_STRUCTURAL),
    ("Behavioural", "How objects collaborate.", GOF_BEHAVIORAL),
]


def anchor(name: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in name]
    return "".join(keep).strip("-").replace("--", "-")


def entry(name: str, p: dict) -> list[str]:
    L = [f"### {name}", ""]
    L.append(f"**{p['what']}**")
    L.append("")
    L.append(f"- **Where** — {p['where']}")
    L.append(f"- **How** — {p['how']}")
    L.append(f"- **Why** — {p['why']}")
    L.append(f"- **Advantages** — {p['adv']}")
    L.append(f"- **Disadvantages** — {p['dis']}")
    L.append(f"- **Trade-off** — *{p['tradeoff']}*")
    L.append("")
    if p.get("bridge"):
        L.append(f"> **Distributed counterpart:** {p['bridge']}  ")
        L.append(f"> {p['harder']}")
        L.append("")
    L.append(f"**What the top 1% do differently.** {p['top1']}")
    L.append("")
    return L


def rich_entry(name: str, p: dict) -> list[str]:
    """A non-GoF pattern with full detail, a real case study and a diagram."""
    L = [f"### {name}", "", f"**{p['what']}**", ""]
    L.append(f"- **Where** — {p['where']}")
    L.append(f"- **How** — {p['how']}")
    L.append(f"- **Why** — {p['why']}")
    L.append(f"- **Advantages** — {p['adv']}")
    L.append(f"- **Disadvantages** — {p['dis']}")
    L.append(f"- **Trade-off** — *{p['tradeoff']}*")
    L.append("")
    if p.get("diagram"):
        L.append("```mermaid")
        L.append(p["diagram"].strip())
        L.append("```")
        L.append("")
    if p.get("case"):
        L.append(f"> **In the wild.** {p['case']}")
        L.append("")
    L.append(f"**What the top 1% do differently.** {p['top1']}")
    L.append("")
    return L


def family_section(title: str, blurb: str, rows: list, enriched: dict | None) -> list[str]:
    """Full entries where the data exists, an index table where it does not."""
    L = [f"## {title}", "", blurb, ""]
    if enriched:
        for row in rows:
            name = row[0]
            p = enriched.get(name)
            if p:
                L.extend(rich_entry(name, p))
            else:
                L.append(f"### {name}")
                L.append("")
                L.append(f"**{row[1]}**")
                L.append("")
        return L
    L.append("| Pattern | Intent |" + (" Seen as |" if len(rows[0]) > 2 else ""))
    L.append("|---|---|" + ("---|" if len(rows[0]) > 2 else ""))
    for row in rows:
        extra = f" {row[2]} |" if len(row) > 2 else ""
        L.append(f"| **{row[0]}** | {row[1]} |{extra}")
    L.append("")
    return L


def build() -> str:
    gof_count = sum(len(g) for _, _, g in GOF_GROUPS)
    total = gof_count + len(EIP) + len(DISTRIBUTED) + len(RESILIENCE) + len(DEPLOYMENT)

    L: list[str] = []
    A = L.append
    A("<!-- GENERATED by scripts/gen_pattern_catalogue.py -- do not edit by hand. -->")
    A("---")
    A("topic: Pattern Catalogue")
    A("category: Patterns")
    A("difficulty: Intermediate")
    A("---")
    A("")
    A("# Pattern Catalogue")
    A("")
    A(f"Every pattern family that bears on system design — **{total} patterns** across five "
      "families — listed so that what is *not* covered stays visible.")
    A("")
    A("| Family | Count | Level | Depth here |")
    A("|---|---|---|---|")
    A(f"| [Gang of Four](#gang-of-four) | {gof_count} | Objects and classes | Full entries |")
    A(f"| [Enterprise integration](#enterprise-integration-patterns) | {len(EIP)} | Messages between services | Index |")
    A(f"| [Distributed systems](#distributed-systems-patterns) | {len(DISTRIBUTED)} | Nodes and data | Index |")
    A(f"| [Resilience](#resilience-patterns) | {len(RESILIENCE)} | Behaviour under failure | Index |")
    A(f"| [Deployment](#deployment-patterns) | {len(DEPLOYMENT)} | Change without downtime | Index |")
    A("")
    A("Each Gang of Four entry carries **what · where · how · why · advantages · disadvantages · "
      "trade-off**, plus two fields you will not find in a normal reference: the *distributed "
      "counterpart*, and *what the top 1% do differently*. The other four families are indexed "
      "here and get full entries as their pages land — see [ROADMAP](../ROADMAP.md).")
    A("")

    A("## Why Gang of Four is in a system design repository")
    A("")
    A("Most system design material drops these on the grounds that they are \"just object-"
      "oriented design\". That throws away the most useful thing about them.")
    A("")
    A("**Nearly every GoF pattern has a distributed counterpart, and the counterpart is harder "
      "for the same reason every time:** the single-process version quietly relies on shared "
      "memory and a single clock. The distributed version has neither.")
    A("")
    A("| In one process | Across a cluster | What distribution added |")
    A("|---|---|---|")
    A("| Singleton — a static field | Leader election | Consensus, leases, fencing tokens, and "
      "two nodes that can both believe they hold it |")
    A("| Observer — a method call that cannot fail | Pub/sub | Delivery is not guaranteed, order "
      "is not guaranteed, the subscriber may be down |")
    A("| Memento — copy some fields | Distributed snapshot | \"A moment in time\" stops existing "
      "without coordination |")
    A("| Iterator — walk an array | Cursor pagination | The collection changes while you walk it |")
    A("| Mediator — a coordinating object | Message broker | It is now the availability ceiling "
      "for everything it mediates |")
    A("")
    A("Reading that table is the fastest way to see what distribution actually costs.")
    A("")

    A("## Gang of Four")
    A("")
    for title, _, group in GOF_GROUPS:
        A(f"**{title}** — " + " · ".join(f"[{n}](#{anchor(n)})" for n in group))
        A("")
    for title, blurb, group in GOF_GROUPS:
        A(f"## {title}")
        A("")
        A(blurb)
        A("")
        for name, p in group.items():
            L.extend(entry(name, p))

    for title, blurb, rows, enriched in [
        ("Enterprise integration patterns",
         "Hohpe and Woolf. The vocabulary of anything message-based — and the reason "
         "\"just put a queue in front of it\" is not a design.",
         EIP, getattr(EXTRA, "EIP", None)),
        ("Distributed systems patterns",
         "How nodes and data behave when there is no shared memory and no shared clock.",
         DISTRIBUTED, getattr(EXTRA, "DISTRIBUTED", None)),
        ("Resilience patterns",
         "How a system behaves when something it depends on is broken.",
         RESILIENCE, getattr(EXTRA, "RESILIENCE", None)),
        ("Deployment patterns",
         "Changing a running system without stopping it. These belong in a system design "
         "repository because the chain in "
         "[System Design Thinking](../SYSTEM-DESIGN-THINKING.md#part-1--the-chain) has "
         "*\"deploys meant downtime\"* as a reason the load balancer gets added — deployment "
         "is an architectural force, not an afterthought.",
         DEPLOYMENT, getattr(EXTRA, "DEPLOYMENT", None)),
    ]:
        L.extend(family_section(title, blurb, rows, enriched))

    A("Three resilience patterns are routinely conflated and are **not** the same thing: "
      "**rate limiting** caps a caller, **load shedding** drops low-value work to protect "
      "high-value work, and **backpressure** tells the producer to slow down. A system can need "
      "all three, and each fails differently in the absence of the others.")
    A("")

    A("## Related")
    A("")
    A("- [Component combination matrix](../14-component-combinations/MATRIX.md) — all 153 pairs, "
      "with real systems")
    A("- [System Design Thinking](../SYSTEM-DESIGN-THINKING.md) — the chain that forces these")
    A("- [Trade-off Framework](../TRADEOFF-FRAMEWORK.md) · [Glossary](../GLOSSARY.md)")
    A("")
    return "\n".join(L)


def build_json() -> str:
    """Machine-readable form for the visualizer.

    Emitted from the same tables that produce the markdown, so a pattern cannot
    be described one way on the page and another way in the app.
    """
    out = {"families": []}
    for title, blurb, group in GOF_GROUPS:
        out["families"].append({
            "id": f"gof-{title.lower()}",
            "name": f"Gang of Four — {title}",
            "blurb": blurb,
            "patterns": [
                {"name": n, "what": p["what"], "where": p["where"], "how": p["how"],
                 "why": p["why"], "adv": p["adv"], "dis": p["dis"],
                 "tradeoff": p["tradeoff"], "top1": p["top1"],
                 "bridge": p.get("bridge"), "harder": p.get("harder")}
                for n, p in group.items()
            ],
        })
    for fid, name, blurb, rows, keys in [
        ("eip", "Enterprise integration", "Messages between services.", EIP, ("what", "where")),
        ("distributed", "Distributed systems", "Nodes and data.", DISTRIBUTED, ("what", "level")),
        ("resilience", "Resilience", "Behaviour under failure.", RESILIENCE, ("what",)),
        ("deployment", "Deployment", "Change without downtime.", DEPLOYMENT, ("what",)),
    ]:
        enriched = getattr(EXTRA, fid.upper().replace("-", "_"), None) if EXTRA else None
        pats = []
        for row in rows:
            d = {"name": row[0], "what": row[1]}
            if len(row) > 2:
                d[keys[1]] = row[2]
            rich = (enriched or {}).get(row[0])
            if rich:
                d.update({k: rich[k] for k in
                          ("where", "how", "why", "adv", "dis", "tradeoff", "top1",
                           "case", "diagram")
                          if rich.get(k)})
            pats.append(d)
        out["families"].append({"id": fid, "name": name, "blurb": blurb, "patterns": pats})
    return json.dumps(out, indent=2, ensure_ascii=False) + chr(10)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    content = build()
    payload = build_json()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    current = OUT.read_text(encoding="utf-8") if OUT.exists() else None
    current_json = OUT_JSON.read_text(encoding="utf-8") if OUT_JSON.exists() else None

    if args.check:
        stale = [name for name, a, b in (
            ("CATALOGUE.md", current, content),
            ("patterns.json", current_json, payload),
        ) if a != b]
        if stale:
            print(f"stale: {', '.join(stale)} -- run: python scripts/gen_pattern_catalogue.py")
            return 1
        print("CATALOGUE.md and patterns.json match the generator")
        return 0

    OUT.write_text(content, encoding="utf-8", newline="\n")
    OUT_JSON.write_text(payload, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(content.splitlines())} lines)")
    print(f"wrote {OUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
