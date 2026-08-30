#!/usr/bin/env python3
"""Generate the case study section.

Ten systems, authored once in `case_study_data.py`, emitted twice: as
`CASE-STUDIES.md` for reading on GitHub, and as `cases.json` for the
visualizer's case study tab. Same discipline as the pattern catalogue and the
interview bank -- a case cannot say one thing on the page and another thing in
the app, because there is only one copy of it.

The validation is not decoration. Four things decay first in a collection of
case studies, and each has a check:

  1. `doesNotApply` shrinks to a stub. The honest half is always the first
     casualty, and a case study without it is marketing for somebody else's
     architecture. Length-checked, because a two-word disclaimer is the shape
     the decay takes.
  2. A `keyDecision` loses its `cost`. A decision without a cost was not a
     decision, it was a preference, and a catalogue of preferences teaches
     nothing.
  3. The Mermaid diagram acquires a character that breaks GitHub's renderer
     silently, or a colour outside the palette. Checked here as well as by
     check_mermaid.py, because here the fix is one line in the data.
  4. A `seeAlso` points at a page that has since been renamed.

    python scripts/gen_case_studies.py            # write both outputs
    python scripts/gen_case_studies.py --check    # fail if either is stale
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from case_study_data import CASES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "17-case-studies" / "CASE-STUDIES.md"
# The visualizer imports this, so the app and the markdown cannot drift.
OUT_JSON = ROOT / "17-case-studies" / "cases.json"

# The four the notation contract allows. `graph` is deliberately excluded --
# it is the deprecated spelling of flowchart and having both invites drift.
DIAGRAM_TYPES = ("flowchart TD", "flowchart LR", "sequenceDiagram", "stateDiagram-v2")

# Every style line must be one of these exactly. Three semantic colours: accent
# for the mechanism that works, amber for the thing to think hardest about, red
# for the failure. A fourth colour would mean nothing, so there is not one.
PALETTE = {
    "fill:#1c6853,stroke:#4fc3a1,color:#e4ecea",   # accent
    "fill:#2a2317,stroke:#d9a441,color:#e4ecea",   # amber
    "fill:#2b1c17,stroke:#e0705a,color:#e4ecea",   # red
}

# Characters that break a Mermaid label or a sequence message. `&` joins nodes,
# `;` ends a statement, `#` opens an entity code, and unquoted parentheses are
# the classic parser trip in sequence message text.
HAZARDS = "&;#()"

# The fields whose absence would make a case study pointless rather than merely
# thin. The numbers are floors, not targets.
MIN_LENGTH = {"problem": 200, "approach": 300, "surprise": 300,
              "applies": 150, "doesNotApply": 250}

LABEL = re.compile(r"\[([^\]]*)\]")
ARROW = re.compile(r"(->>|-->>|-\)|--\)|--x|-x|->|-->)")


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def check_diagram(cid: str, body: str) -> list[str]:
    """Enforce the diagram contract at authoring time.

    check_mermaid.py runs over the committed markdown and catches the same
    class of problem, but it catches it after the file has been written and
    reports a line number in generated output. Here the error names the case,
    which is the thing you actually have to edit.
    """
    problems: list[str] = []

    if "```" in body:
        problems.append(f"{cid}: diagram contains a fence -- the generator adds them")

    lines = [ln for ln in body.splitlines() if ln.strip()]
    if not lines:
        return [f"{cid}: empty diagram"]

    directive = lines[0].strip()
    if directive not in DIAGRAM_TYPES:
        problems.append(f"{cid}: diagram type {directive!r} not one of {DIAGRAM_TYPES}")
    is_flow = directive.startswith("flowchart")
    is_seq = directive.startswith("sequenceDiagram")

    styles = [ln.strip() for ln in lines if ln.strip().startswith("style ")]
    if len(styles) > 2:
        problems.append(f"{cid}: {len(styles)} style lines, at most 2 -- "
                        f"a diagram that highlights everything highlights nothing")
    for s in styles:
        parts = s.split(None, 2)
        if len(parts) != 3 or parts[2] not in PALETTE:
            problems.append(f"{cid}: style outside the palette: {s!r}")

    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith(("style ", "note ", "end", "state ", "participant ")):
            continue

        # Flowchart node labels: `X["..."]`. Every one must be quoted, because
        # an unquoted label containing a comma or a hazard renders as a parse
        # error inside a grey box that nobody scrolls to.
        if is_flow:
            for label in LABEL.findall(stripped):
                if label == "*":
                    continue
                if not (label.startswith('"') and label.endswith('"')):
                    problems.append(f"{cid}: unquoted node label: {label!r}")
                    continue
                inner = label[1:-1]
                bad = [c for c in HAZARDS if c in inner]
                if bad:
                    problems.append(f"{cid}: hazardous {''.join(bad)!r} in label: {inner!r}")

        # Sequence message text is never quoted, so the hazards apply directly.
        if is_seq and ":" in stripped and ARROW.search(stripped):
            msg = re.sub(r"--?\)", "", stripped).split(":", 1)[1]
            bad = [c for c in HAZARDS if c in msg]
            if bad:
                problems.append(f"{cid}: hazardous {''.join(bad)!r} in message: {msg.strip()!r}")

    counting = re.sub(r"--?\)", "", body)
    for pair in ("[]", "{}", "()"):
        if counting.count(pair[0]) != counting.count(pair[1]):
            problems.append(f"{cid}: unbalanced {pair}")
    if body.count('"') % 2:
        problems.append(f"{cid}: odd number of double quotes in the diagram")

    return problems


def validate() -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()

    for case in CASES:
        cid = case["id"]
        if cid in seen:
            problems.append(f"duplicate case id: {cid}")
        seen.add(cid)
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", cid):
            problems.append(f"{cid}: id must be a lowercase slug")

        if not re.fullmatch(r"\d{4}", case["year"]):
            problems.append(f"{cid}: year {case['year']!r} is not four digits")

        # A case with no primary source is an anecdote. That is the one thing
        # this section is not allowed to contain.
        if not case["sourceUrl"].startswith("https://"):
            problems.append(f"{cid}: sourceUrl is not https: {case['sourceUrl']!r}")
        if not case["source"].strip():
            problems.append(f"{cid}: no named source")

        n = len(case["keyDecisions"])
        if not 3 <= n <= 4:
            problems.append(f"{cid}: {n} key decisions, expected 3-4")
        for i, d in enumerate(case["keyDecisions"], 1):
            for field in ("decision", "why", "cost"):
                if not d[field].strip():
                    problems.append(f"{cid}: decision {i} has no {field}")
            # The cost is the whole point of the field, so it is held to a
            # length the word "complexity" cannot satisfy on its own.
            if len(d["cost"]) < 80:
                problems.append(f"{cid}: decision {i} cost is too thin to be a real cost")

        c = len(case["constraints"])
        if not 2 <= c <= 4:
            problems.append(f"{cid}: {c} constraints, expected 2-4")

        for field, floor in MIN_LENGTH.items():
            if len(case[field]) < floor:
                problems.append(f"{cid}: {field} is {len(case[field])} chars, "
                                f"expected at least {floor}")

        s = len(case["seeAlso"])
        if not 2 <= s <= 4:
            problems.append(f"{cid}: {s} seeAlso links, expected 2-4")
        for see in case["seeAlso"]:
            if see.startswith(("./", "/", "../")):
                problems.append(f"{cid}: seeAlso must be repo-relative: {see}")
            elif not (ROOT / see).exists():
                problems.append(f"{cid}: seeAlso does not exist: {see}")

        if not case["question"].strip() or not case["answer"].strip():
            problems.append(f"{cid}: no folded question and answer")

        problems.extend(check_diagram(cid, case["diagram"]))

    return problems


# --------------------------------------------------------------------------
# markdown
# --------------------------------------------------------------------------

def render_case(number: int, case: dict) -> list[str]:
    L: list[str] = []
    A = L.append

    # An explicit anchor rather than a heading-derived one: it is exact, it
    # survives a retitle, and it is the same string as the JSON id, so the app
    # can deep-link into this page.
    A(f'<a id="{case["id"]}"></a>')
    A("")
    A(f"## {number}. {case['system']} · {case['title']}")
    A("")
    A(f"`{case['year']}` · {case['scale']}")
    A("")
    A(f"**Source** — [{case['source']}]({case['sourceUrl']})")
    A("")

    A("### The problem")
    A("")
    A(case["problem"])
    A("")

    A("### What they could not change")
    A("")
    for con in case["constraints"]:
        A(f"- {con}")
    A("")

    A("### What they built")
    A("")
    A(case["approach"])
    A("")
    A("```mermaid")
    A(case["diagram"])
    A("```")
    A("")

    A("### Key decisions")
    A("")
    for i, d in enumerate(case["keyDecisions"], 1):
        A(f"**{i} · {d['decision']}**")
        A("")
        A(f"- *Why* — {d['why']}")
        A(f"- *Cost* — {d['cost']}")
        A("")

    A("### The surprise")
    A("")
    A(f"> {case['surprise']}")
    A("")

    A("### When it applies to you")
    A("")
    A(case["applies"])
    A("")

    A("### When copying it would be wrong")
    A("")
    A(case["doesNotApply"])
    A("")

    A("<details><summary><b>What would you have done?</b></summary>")
    A("")
    A(f"**{case['question']}**")
    A("")
    A(case["answer"])
    A("")
    A("</details>")
    A("")
    A(" · ".join(f"[{s}](../{s})" for s in case["seeAlso"]))
    A("")
    return L


def build() -> str:
    n = len(CASES)
    n_dec = sum(len(c["keyDecisions"]) for c in CASES)
    years = sorted(c["year"] for c in CASES)

    L: list[str] = []
    A = L.append

    A("<!-- GENERATED by scripts/gen_case_studies.py -- do not edit by hand. -->")
    A("---")
    A("topic: Case Studies")
    A("category: Case studies")
    A("difficulty: Intermediate → Advanced")
    A("---")
    A("")
    A("# Case Studies")
    A("")
    A(f"`[INTERMEDIATE → ADVANCED]` · **{n} systems**, {years[0]}–{years[-1]}, every one with a "
      f"public primary source — **{n_dec} decisions** with the cost of each one stated, and for "
      f"every case an honest paragraph on when copying it would be a mistake.")
    A("")
    A("---")
    A("")

    # --- how to read one ----------------------------------------------------
    A("## How to read a case study")
    A("")
    A("These are the systems everyone cites and almost nobody reads. That gap is where the damage "
      "happens: an architecture arrives in a design review with a famous company's name attached "
      "and no constraints attached, and the constraints were the entire reason it looked like "
      "that.")
    A("")
    A("**The `When copying it would be wrong` section matters more than the architecture.** It is "
      "last on the page and it is first in importance. Every system here was built by a team "
      "operating three or four orders of magnitude above you, against a constraint you do not "
      "have — a 99.9th-percentile revenue SLA, a fan-out of a thousand servers, atomic clocks in "
      "the rack. Dynamo's design in a system with one datacentre and forty requests a second is "
      "not a bold choice, it is a straightforward and expensive mistake, and the same is true of "
      "most of the others. Read that section first if you are in a hurry. It is the only section "
      "that can save you a quarter.")
    A("")
    A("**Read the constraints before the solution.** A design is only interesting relative to what "
      "it could not change. Facebook could not stop product teams widening the fan-out; Google "
      "could change the hardware in the rack, which almost nobody can; Discord could not take the "
      "product offline. Strip the constraints away and every one of these becomes an arbitrary "
      "preference you are free to copy — which is exactly how they get copied.")
    A("")
    A("**Every decision here has a cost, because a decision without one was not a decision.** If "
      "you can only remember one thing from a case, make it the cost rather than the choice. The "
      "choice is the part you will be tempted to repeat; the cost is the part that tells you "
      "whether you can afford to.")
    A("")
    A("**The surprise is why each case is here at all.** Not the architecture — the thing that "
      "reverses when you look closely. Facebook's leases fix a bug most engineers have never heard "
      "of. Dynamo's elaborate conflict machinery fires roughly once in ten thousand reads. "
      "Google's answer to tail latency is to do the work twice and it costs 2%. Exceeding your "
      "reliability target is a failure, and Google's response was to cause an outage on purpose. "
      "If a case here ever stops surprising you, it has stopped earning its place.")
    A("")
    A("Every figure on this page comes from the named primary source and was checked against it. "
      "Where a number could not be verified it is described qualitatively instead, deliberately — "
      "a case study that invents a number is worse than no case study, because it launders a guess "
      "through somebody else's reputation.")
    A("")

    # --- the index ----------------------------------------------------------
    A("## The cases")
    A("")
    A("| | System | What it is about | Year | The surprise, in one line |")
    A("|:-:|---|---|:-:|---|")
    for i, c in enumerate(CASES, 1):
        A(f"| {i} | [{c['system']}](#{c['id']}) | {c['title']} | {c['year']} "
          f"| {one_line(c['surprise'])} |")
    A("")
    A("Each case is self-contained. There is no reading order, but if you want one, read the "
      "[tail at scale](#google-tail-at-scale) first — it is the shortest route to understanding "
      "why every other system on this page is shaped the way it is.")
    A("")

    for i, c in enumerate(CASES, 1):
        A("---")
        A("")
        L.extend(render_case(i, c))

    # --- related -----------------------------------------------------------
    A("---")
    A("")
    A("## Related")
    A("")
    A("- [Case study index](README.md) — how this section is built, and what is deliberately "
      "not here")
    A("- [Pattern catalogue](../13-design-patterns/CATALOGUE.md) — the reusable form of most of "
      "the mechanisms above")
    A("- [Combination matrix](../14-component-combinations/MATRIX.md) — every component pair, with "
      "the real system that runs it")
    A("- [URL shortener](../15-real-world-problems/url-shortener/) — the same reasoning applied to "
      "one problem, V1 to V8")
    A("- [Trade-off framework](../TRADEOFF-FRAMEWORK.md) — how to make and state a decision with a "
      "cost attached")
    A("- [Interview questions](../20-system-design-interview/QUESTIONS.md) — several of these "
      "mechanisms, as questions")
    A("- [Glossary](../GLOSSARY.md) — every term above, defined once")
    A("")
    return "\n".join(L)


def one_line(surprise: str) -> str:
    """First sentence of the surprise, for the index table.

    The index is the only place a reader decides whether to read a case, so it
    gets the hook rather than a description of the topic.
    """
    first = re.split(r"(?<=[.!?]) ", surprise.strip())[0]
    return first.replace("|", "-")


# --------------------------------------------------------------------------
# json
# --------------------------------------------------------------------------

def build_json() -> str:
    """Machine-readable form for the visualizer.

    The schema is fixed and owned by the app, so this emits exactly the agreed
    fields and no more -- `question` and `answer` live in the data module and
    stay on the markdown page.
    """
    out = {"cases": [
        {
            "id": c["id"],
            "system": c["system"],
            "title": c["title"],
            "year": c["year"],
            "scale": c["scale"],
            "problem": c["problem"],
            "constraints": list(c["constraints"]),
            "approach": c["approach"],
            "keyDecisions": [
                {"decision": d["decision"], "why": d["why"], "cost": d["cost"]}
                for d in c["keyDecisions"]
            ],
            "surprise": c["surprise"],
            "applies": c["applies"],
            "doesNotApply": c["doesNotApply"],
            "source": c["source"],
            "sourceUrl": c["sourceUrl"],
            "seeAlso": list(c["seeAlso"]),
            "diagram": c["diagram"],
        }
        for c in CASES
    ]}
    return json.dumps(out, indent=2, ensure_ascii=False) + chr(10)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    problems = validate()
    if problems:
        print("case_study_data.py is invalid:")
        for p in problems:
            print(f"        {p}")
        return 1

    content = build()
    payload = build_json()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    current = OUT.read_text(encoding="utf-8") if OUT.exists() else None
    current_json = OUT_JSON.read_text(encoding="utf-8") if OUT_JSON.exists() else None

    if args.check:
        stale = [name for name, a, b in (
            ("CASE-STUDIES.md", current, content),
            ("cases.json", current_json, payload),
        ) if a != b]
        if stale:
            print(f"stale: {', '.join(stale)} -- run: python scripts/gen_case_studies.py")
            return 1
        print("CASE-STUDIES.md and cases.json match the generator")
        return 0

    OUT.write_text(content, encoding="utf-8", newline="\n")
    OUT_JSON.write_text(payload, encoding="utf-8", newline="\n")
    n_dec = sum(len(c["keyDecisions"]) for c in CASES)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(content.splitlines())} lines)")
    print(f"wrote {OUT_JSON.relative_to(ROOT)} "
          f"({len(CASES)} cases, {n_dec} decisions, {len(CASES)} primary sources)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
