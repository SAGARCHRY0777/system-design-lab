#!/usr/bin/env python3
"""Generate 16-design-exercises/ from the scene decision files.

The visualizer's studio asks these as exercises. This renders the same data as
markdown so it is readable on GitHub, where most people meet this repository and
where no JavaScript runs.

The source is 19-diagrams/scenes/decisions/*.json -- the identical files the app
imports -- so the page and the app cannot disagree. That is the same property the
diagrams have, and it is the reason anything here is generated rather than
written twice.

Answers sit inside <details>. A parameter question whose answer is visible on the
same screen is not an exercise, it is a table.

    python scripts/gen_decisions.py            # write the pages
    python scripts/gen_decisions.py --check    # fail if any is missing or stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "19-diagrams" / "scenes"
OUT = ROOT / "16-design-exercises"

# Ordered to match the reading path: simplest system first.
SCENES = ["url-shortener", "social-feed", "ticket-booking",
          "chat-system", "notification-system", "payment-system"]

REVERSIBILITY = {
    "cheap": (
        "Reversible",
        "A config change. Get it wrong, notice, fix it the same day.",
    ),
    "costly": (
        "Costly to reverse",
        "Reversing this means changing code that already depends on it, or "
        "repairing data written under the old assumption.",
    ),
    "one-way": (
        "One-way door",
        "You do not get to change your mind. Reversing it is a migration "
        "measured in months, or it is simply not possible.",
    ),
}

VERDICT_MARK = {"correct": "**Correct.**", "defensible": "**Defensible.**", "wrong": "**No.**"}

WEIGHT = {"cheap": 0, "costly": 1, "one-way": 2}


def load(scene_id: str) -> tuple[dict, list[dict]]:
    scene = json.loads((SRC / f"{scene_id}.json").read_text(encoding="utf-8"))
    data = json.loads((SRC / "decisions" / f"{scene_id}.json").read_text(encoding="utf-8"))
    decisions = sorted(data["decisions"], key=lambda d: (d["v"], -WEIGHT[d["reversibility"]]))
    return scene, decisions


def scene_page(scene_id: str) -> str:
    scene, decisions = load(scene_id)
    versions = {v["v"]: v for v in scene["versions"]}

    out: list[str] = []
    out.append("---")
    out.append(f"topic: {scene['title']} — parameter decisions")
    out.append("category: Design exercise")
    out.append("difficulty: Advanced")
    out.append("---")
    out.append("")
    out.append(f"# {scene['title']} — parameter decisions")
    out.append("")
    problem = rel_problem(scene_id)
    built = f"[{scene['title']}]({problem})" if problem else f"**{scene['title']}**"
    out.append(
        f"{len(decisions)} decisions taken while building {built}. Not *which component* — "
        "that is the other exercise. These are the values you set once the component is "
        "there, which is the half that ends up in the postmortem."
    )
    out.append("")
    if not problem:
        out.append(
            f"> This system is animated, quizzed and gradeable in the "
            f"[lab](https://sagarchry0777.github.io/system-design-lab/), but its V1→V8 prose "
            f"page is not written yet — see [gaps](../GAPS.md)."
        )
        out.append("")
    out.append(
        "**Commit to an answer before opening the box.** A parameter question you read the "
        "answer to teaches nothing; the correction only lands if there was a prediction for it "
        "to contradict."
    )
    out.append("")

    counts = {k: sum(1 for d in decisions if d["reversibility"] == k) for k in REVERSIBILITY}
    ow, cost, cheap = counts["one-way"], counts["costly"], counts["cheap"]
    out.append(
        f"Of these {len(decisions)}: "
        f"**{ow} {'is a one-way door' if ow == 1 else 'are one-way doors'}**, "
        f"{cost} {'is' if cost == 1 else 'are'} costly to reverse, "
        f"{cheap} {'is' if cheap == 1 else 'are'} config. "
        "Sort your design argument accordingly."
    )
    out.append("")

    for i, d in enumerate(decisions, 1):
        label, blurb = REVERSIBILITY[d["reversibility"]]
        ver = versions.get(d["v"], {})
        out.append("---")
        out.append("")
        out.append(f"## {i}. {d['parameter']}")
        out.append("")
        out.append(f"> **{label}** — {blurb}")
        out.append("")
        out.append(f"**At V{d['v']}** ({ver.get('label', '')}): {ver.get('trigger', '')}")
        out.append("")

        # The architecture this decision is actually about. A parameter question
        # read without the system in front of you is a vocabulary question --
        # "what do you shard on" only means something once you can see that the
        # read path carries a code and nothing else.
        svg = f"../19-diagrams/generated/{scene_id}-v{d['v']}.svg"
        if (ROOT / "19-diagrams" / "generated" / f"{scene_id}-v{d['v']}.svg").exists():
            out.append(f'<img src="{svg}" alt="{scene["title"]} at version {d["v"]}: '
                       f'{ver.get("label", "")}" width="740">')
            out.append("")

        out.append(f"**{d['question']}**")
        out.append("")
        for o in d["options"]:
            out.append(f"- {o['value']}")
        out.append("")
        out.append("<details>")
        out.append("<summary>Commit to one, then open this</summary>")
        out.append("")
        for o in d["options"]:
            out.append(f"**{o['value']}** — {VERDICT_MARK[o['verdict']]} {o['because']}")
            out.append("")
        out.append(f"**If you need to change your mind:** {d['reversal']}")
        out.append("")
        out.append("</details>")
        out.append("")

    out.append("---")
    out.append("")
    out.append("## Related")
    out.append("")
    if problem:
        out.append(f"- [{scene['title']} — the full design]({problem})")
    else:
        out.append("- [Real-world problems](../15-real-world-problems/) — the systems that "
                   f"*do* have a written V1→V8 design ({scene['title']} does not yet)")
    out.append("- [All parameter decisions](README.md)")
    out.append("- [Trade-off framework](../TRADEOFF-FRAMEWORK.md)")
    out.append("")
    return "\n".join(out)


def has_problem(scene_id: str) -> bool:
    return (ROOT / "15-real-world-problems" / scene_id / "README.md").exists()


def rel_problem(scene_id: str) -> str | None:
    """The worked problem page, or None if this scene does not have one yet.

    Returning a fallback here was a quiet bug: social feed and ticket booking
    have scenes but no written problem, so both pages advertised
    "<title> — the full design" pointing at the case-study hub. The link
    RESOLVED, so check_links.py was satisfied; the label was simply false. A
    working link that lies is worse than a broken one, because nothing flags it.
    """
    return f"../15-real-world-problems/{scene_id}/" if has_problem(scene_id) else None


def index_page() -> str:
    rows = []
    totals = {k: 0 for k in REVERSIBILITY}
    total = 0
    for sid in SCENES:
        scene, decisions = load(sid)
        total += len(decisions)
        counts = {k: sum(1 for d in decisions if d["reversibility"] == k) for k in REVERSIBILITY}
        for k in REVERSIBILITY:
            totals[k] += counts[k]
        rows.append(
            f"| [{scene['title']}]({sid}.md) | {len(decisions)} | "
            f"{counts['one-way']} | {counts['costly']} | {counts['cheap']} |"
        )

    out: list[str] = []
    out.append("---")
    out.append("topic: Design exercises — parameter decisions")
    out.append("category: Design exercise")
    out.append("difficulty: Advanced")
    out.append("---")
    out.append("")
    out.append("# Design exercises — the parameters")
    out.append("")
    out.append(
        "Choosing a component is the visible half of design, because it is the half a "
        "whiteboard diagram shows. Choosing what to **set it to** is the other half, and it is "
        "the one that ends up in the incident review. Nobody writes *\"we should not have used "
        "a cache.\"* They write *\"the TTL was wrong\"* and *\"we sharded on the wrong column.\"*"
    )
    out.append("")
    out.append(
        f"These are **{total} parameter decisions** taken across the six systems in this "
        "repository, each at the point in that system's evolution where it actually came up."
    )
    out.append("")
    out.append("## The thing worth learning here is not the values")
    out.append("")
    out.append(
        "It is which decisions you are allowed to get wrong. Every decision below is labelled:"
    )
    out.append("")
    out.append("| Label | Meaning | How to treat it |")
    out.append("|---|---|---|")
    out.append(
        "| **Reversible** | A config change. | Decide fast, ship it, correct it with "
        "production data. Arguing for a week costs more than being wrong. |"
    )
    out.append(
        "| **Costly to reverse** | Code and data already depend on it. | Worth a design "
        "review. Write down the assumption you are making so the next person can find it. |"
    )
    out.append(
        "| **One-way door** | A migration measured in months, or impossible. | This is where "
        "the argument belongs. Get more people in the room. |"
    )
    out.append("")
    out.append(
        f"Across these six systems: **{totals['one-way']} one-way doors**, "
        f"{totals['costly']} costly, {totals['cheap']} reversible."
    )
    out.append("")
    out.append(
        "The uncomfortable pattern is that **one-way doors cluster at the beginning.** The URL "
        "shortener's code length is fixed at V1, serving 10,000 requests a day, when it feels "
        "like the least consequential thing on the board — and every code ever issued is a "
        "public URL that someone has printed on a poster. The chat system's ordering key is "
        "chosen before anyone has hit a clock-skew bug. You make your most permanent decisions "
        "when you know the least, which is an argument for recognising them, not for "
        "pretending you can avoid them."
    )
    out.append("")
    out.append("## The systems")
    out.append("")
    out.append("| System | Decisions | One-way | Costly | Reversible |")
    out.append("|---|---|---|---|---|")
    out.extend(rows)
    out.append("")
    out.append("## Where the one-way doors are")
    out.append("")
    out.append(
        "Plotted against the version they are taken at. The pattern is the "
        "uncomfortable part — the decisions you cannot undo are the ones you make first."
    )
    out.append("")
    out.append("```mermaid")
    out.append("%%{init: {'theme':'base'}}%%")
    out.append("timeline")
    out.append("    title Parameter decisions by the version that forces them")
    for band, label in ((range(1, 3), "V1-V2 · smallest system"),
                        (range(3, 6), "V3-V5 · growing"),
                        (range(6, 99), "V6+ · at scale")):
        items = []
        for sid in SCENES:
            scene, decisions = load(sid)
            for d in decisions:
                if d["v"] in band and d["reversibility"] == "one-way":
                    items.append(f"{scene['title']}: {d['parameter']}")
        out.append(f"    {label} : " + " : ".join(items or ["(none)"]))
    out.append("```")
    out.append("")
    # Derived, not asserted. An earlier draft of this paragraph claimed "four of
    # the five sit at V1-V3" and the real answer was two -- a made-up number
    # inside a page arguing for measured ones.
    oneway_vs = sorted(d["v"] for sid in SCENES for d in load(sid)[1]
                       if d["reversibility"] == "one-way")
    med = oneway_vs[len(oneway_vs) // 2]
    early = sum(1 for v in oneway_vs if v <= med)
    out.append(
        f"They land at V{', V'.join(str(v) for v in oneway_vs)} — {early} of "
        f"{len(oneway_vs)} by V{med}, roughly the midpoint of a system's life here and "
        "long before there is enough traffic to prove which choice was right. An ID "
        "scheme, a feed row's contents and an ordering key all have to be settled while "
        "the evidence that would settle them does not exist yet. **That is the argument "
        "for recognising a one-way door, not for expecting to avoid one.**"
    )
    out.append("")
    out.append("## Do these interactively instead")
    out.append("")
    out.append(
        "The [design studio](https://sagarchry0777.github.io/system-design-lab/) asks these "
        "in sequence, after first making you choose the components — so the parameter question "
        "arrives where it does in real life: once you have already committed to the design. It "
        "also remembers which ones you got wrong."
    )
    out.append("")
    out.append("## Related")
    out.append("")
    out.append("- [Trade-off framework](../TRADEOFF-FRAMEWORK.md) — the axes these sit on")
    out.append("- [System design thinking](../SYSTEM-DESIGN-THINKING.md) — the chain these come from")
    out.append("- [Real-world problems](../15-real-world-problems/) — the systems being configured")
    out.append("- [Anti-patterns](../anti-patterns/) — what the wrong answers turn into")
    out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    pages = {OUT / "README.md": index_page()}
    for sid in SCENES:
        pages[OUT / f"{sid}.md"] = scene_page(sid)

    stale, written = [], 0
    for path, text in pages.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        if args.check:
            stale.append(path.relative_to(ROOT))
        else:
            path.write_text(text, encoding="utf-8", newline="\n")
            written += 1

    if args.check:
        if stale:
            print("Design-exercise pages are missing or stale -- run: "
                  "python scripts/gen_decisions.py")
            for s in stale:
                print(f"  {s}")
            return 1
        print(f"design exercises current across {len(pages)} pages")
        return 0

    print(f"wrote {written} of {len(pages)} design-exercise page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
