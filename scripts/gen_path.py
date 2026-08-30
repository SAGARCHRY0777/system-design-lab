#!/usr/bin/env python3
"""Inject a previous/next navigation footer along the reading path.

The repository has a dense cross-link graph -- good for reference, and the
wrong shape for learning. A reader who finishes the foundations index is offered
twenty-two outbound links and no indication which one continues the sequence.
Dense linking answers "what else is related"; it does not answer "what do I read
next", and a learner needs exactly one obvious answer to that.

So there is one canonical path, defined below, and every page on it gets a
footer naming its neighbours. Pages off the path are untouched -- being a
reference page is a legitimate thing to be.

The footer sits between HTML markers so it can be regenerated in place. Anything
a human writes outside them survives.

    python scripts/gen_path.py            # write the footers
    python scripts/gen_path.py --check    # fail if any is missing or stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BEGIN = "<!-- PATH:BEGIN -->"
END = "<!-- PATH:END -->"

# The canonical reading order. Each entry is (path, short label).
# Ordered so that every page's prerequisite comes before it -- this is the same
# order the README's "where to start" advertises, made real.
PATH: list[tuple[str, str]] = [
    ("SYSTEM-DESIGN-THINKING.md", "System design thinking"),
    ("ESTIMATION-GUIDE.md", "Estimation"),
    ("TRADEOFF-FRAMEWORK.md", "Trade-off framework"),
    ("00-foundations/README.md", "Foundations"),
    ("00-foundations/latency/README.md", "Latency"),
    ("00-foundations/throughput/README.md", "Throughput"),
    ("00-foundations/scalability/README.md", "Scalability"),
    ("00-foundations/availability/README.md", "Availability"),
    ("00-foundations/reliability/README.md", "Reliability"),
    ("00-foundations/consistency/README.md", "Consistency"),
    ("00-foundations/cap-theorem/README.md", "CAP theorem"),
    ("03-load-balancing/fundamentals/README.md", "Load balancer"),
    ("04-caching/fundamentals/README.md", "Cache"),
    ("05-databases/fundamentals/README.md", "Database"),
    ("05-databases/replication/README.md", "Replication"),
    ("05-databases/sharding/README.md", "Sharding"),
    ("06-messaging/queues/README.md", "Queue"),
    ("06-messaging/workers/README.md", "Worker"),
    ("08-reliability/README.md", "Reliability patterns"),
    ("08-reliability/timeouts/README.md", "Timeouts"),
    ("08-reliability/retries/README.md", "Retries"),
    ("08-reliability/circuit-breaker/README.md", "Circuit breaker"),
    ("11-observability/README.md", "Observability"),
    ("14-component-combinations/README.md", "Combinations"),
    ("15-real-world-problems/url-shortener/README.md", "URL shortener, V1 to V8"),
    ("17-case-studies/README.md", "Case studies"),
    ("20-system-design-interview/README.md", "Interview"),
]


def rel(frm: str, to: str) -> str:
    """Relative link from one repo path to another."""
    depth = len(Path(frm).parts) - 1
    return "../" * depth + to


def block(i: int) -> str:
    total = len(PATH)
    here_path, here_label = PATH[i]
    prev = PATH[i - 1] if i > 0 else None
    nxt = PATH[i + 1] if i + 1 < total else None

    lines = [BEGIN, "", "---", ""]
    lines.append(f"<sub>**The reading path** · step {i + 1} of {total} · *{here_label}*</sub>")
    lines.append("")
    parts = []
    if prev:
        parts.append(f"◀ **Previous** [{prev[1]}]({rel(here_path, prev[0])})")
    if nxt:
        parts.append(f"**Next** [{nxt[1]}]({rel(here_path, nxt[0])}) ▶")
    else:
        parts.append("**End of the path.** From here: "
                     f"[the gaps]({rel(here_path, 'GAPS.md')}) — what this repository "
                     "deliberately does not cover.")
    lines.append(" &nbsp;·&nbsp; ".join(parts))
    lines.append("")
    lines.append(END)
    return "\n".join(lines)


def apply(text: str, new: str) -> str:
    if BEGIN in text and END in text:
        head = text[: text.index(BEGIN)]
        tail = text[text.index(END) + len(END):]
        return head + new + tail
    return text.rstrip() + "\n\n" + new + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    missing = [p for p, _ in PATH if not (ROOT / p).exists()]
    if missing:
        print("Path references files that do not exist:")
        for m in missing:
            print(f"  {m}")
        return 1

    stale, written = [], 0
    for i, (p, _) in enumerate(PATH):
        f = ROOT / p
        current = f.read_text(encoding="utf-8")
        updated = apply(current, block(i))
        if current == updated:
            continue
        if args.check:
            stale.append(p)
        else:
            f.write_text(updated, encoding="utf-8", newline="\n")
            written += 1

    if args.check:
        if stale:
            print("Reading-path footers are missing or stale -- run: python scripts/gen_path.py")
            for s in stale:
                print(f"  {s}")
            return 1
        print(f"reading path intact across {len(PATH)} pages")
        return 0

    print(f"wrote the reading-path footer on {written} of {len(PATH)} page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
