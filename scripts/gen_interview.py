#!/usr/bin/env python3
"""Generate the interview question bank.

Nine tracks, authored once in `interview_data.py`, emitted twice: as
`QUESTIONS.md` for reading on GitHub, and as `questions.json` for the
visualizer's interview tab. Same discipline as the pattern catalogue -- a
question cannot say one thing on the page and another thing in the app,
because there is only one copy of it.

The generator also validates, and the validation is not decoration. It
enforces the three things that decay first in a question bank: a `level`
outside the three allowed values, a `seeAlso` pointing at a page that has
since been renamed, and a follow-up chain that has been trimmed to one
question -- at which point it has stopped being an escalation and gone back
to being trivia.

    python scripts/gen_interview.py            # write both outputs
    python scripts/gen_interview.py --check    # fail if either is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from interview_data import TRACKS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "20-system-design-interview" / "QUESTIONS.md"
# The visualizer imports this, so the app and the markdown cannot drift.
OUT_JSON = ROOT / "20-system-design-interview" / "questions.json"

LEVELS = ("basic", "intermediate", "advanced")
LEVEL_LABEL = {
    "basic": "Basic",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
}


def slug(text: str) -> str:
    keep = [c.lower() if c.isalnum() else "-" for c in text]
    return "".join(keep).strip("-").replace("--", "-")


def numbered(track: dict) -> list[tuple[str, dict]]:
    """Attach `track-N` ids in authored order.

    Questions are authored basic-first, so the id order and the reading
    order of the page are the same number. That is worth keeping: `caching-4`
    should be findable by counting down the page.
    """
    return [(f"{track['id']}-{i}", q) for i, q in enumerate(track["questions"], 1)]


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------

def validate() -> list[str]:
    problems: list[str] = []
    seen_track_ids: set[str] = set()

    for track in TRACKS:
        tid = track["id"]
        if tid in seen_track_ids:
            problems.append(f"duplicate track id: {tid}")
        seen_track_ids.add(tid)

        n = len(track["questions"])
        if not 4 <= n <= 6:
            problems.append(f"{tid}: {n} questions, expected 4-6")

        levels = [q["level"] for q in track["questions"]]
        if levels != sorted(levels, key=LEVELS.index):
            problems.append(f"{tid}: questions are not authored basic -> advanced")
        for want in LEVELS:
            if want not in levels:
                problems.append(f"{tid}: no {want} question")

        for qid, q in numbered(track):
            if q["level"] not in LEVELS:
                problems.append(f"{qid}: level {q['level']!r} not one of {LEVELS}")
            if not 2 <= len(q["followUps"]) <= 3:
                problems.append(
                    f"{qid}: {len(q['followUps'])} follow-ups, expected 2-3")
            if not q["redFlags"]:
                problems.append(f"{qid}: no red flags")
            see = q["seeAlso"]
            if see.startswith(("./", "/")):
                problems.append(f"{qid}: seeAlso must be repo-relative: {see}")
            elif not (ROOT / see).exists():
                problems.append(f"{qid}: seeAlso does not exist: {see}")

    return problems


# --------------------------------------------------------------------------
# markdown
# --------------------------------------------------------------------------

def render_question(number: int, q: dict) -> list[str]:
    L: list[str] = []
    A = L.append

    A(f"**{number}.** {q['q']}")
    A("")
    A(f"> **What they are really asking** — {q['asking']}")
    A("")
    A("<details><summary>Answer</summary>")
    A("")
    A(q["answer"])
    A("")
    A("</details>")
    A("")
    A("**Red flags**")
    A("")
    for flag in q["redFlags"]:
        A(f"- {flag}")
    A("")

    for i, f in enumerate(q["followUps"], 1):
        A(f"**Follow-up {i}.** {f['q']}")
        A("")
        A("<details><summary>Answer</summary>")
        A("")
        A(f["answer"])
        A("")
        A("</details>")
        A("")

    A(f"→ [{q['seeAlso']}](../{q['seeAlso']})")
    A("")
    return L


def build() -> str:
    n_tracks = len(TRACKS)
    n_questions = sum(len(t["questions"]) for t in TRACKS)
    n_follow = sum(len(q["followUps"]) for t in TRACKS for q in t["questions"])
    n_flags = sum(len(q["redFlags"]) for t in TRACKS for q in t["questions"])
    by_level = {lv: sum(1 for t in TRACKS for q in t["questions"] if q["level"] == lv)
                for lv in LEVELS}

    L: list[str] = []
    A = L.append

    A("<!-- GENERATED by scripts/gen_interview.py -- do not edit by hand. -->")
    A("---")
    A("topic: Interview Questions")
    A("category: Interview")
    A("difficulty: n/a")
    A("---")
    A("")
    A("# Interview Questions")
    A("")
    A(f"`[BEGINNER → EXPERT]` · **{n_questions} questions** across **{n_tracks} tracks**, each "
      f"with a follow-up chain — **{n_follow} follow-ups** in total, and "
      f"{n_flags} named red flags.")
    A("")
    A("---")
    A("")

    # --- how to use it -----------------------------------------------------
    A("## How to use this")
    A("")
    A("Not a list of answers to memorise. Three things on this page matter more than the "
      "answer text, and they are the reason it is laid out like this.")
    A("")
    A("**1 · The `What they are really asking` line matters more than the answer.** Almost "
      "every question here has a surface reading and an actual one. *\"What is a cache?\"* is "
      "not a vocabulary check — it is asking whether you know a cache is a bet on **skew**, "
      "and a candidate who defines it correctly and never says the word *skew* has answered "
      "the wrong question fluently. Read that line first, then decide what your answer was "
      "actually being scored on.")
    A("")
    A("**2 · The follow-ups are the real test.** Anyone can recite a first answer; the "
      "internet is full of them, and an interviewer has heard yours before. The follow-ups "
      "here are **ordered**, and each one is the question that naturally falls out of the "
      "previous *answer* — which is exactly how a real interviewer digs. If your first answer "
      "cannot survive being asked *\"and then what breaks?\"* twice, it was recall rather than "
      "understanding, and the second follow-up is where that becomes visible.")
    A("")
    A("**3 · Some of these are judgement questions, and the strong answer is \"no\".** At "
      "least one question in every track is a proposal you should decline. Adding a cache to "
      "uniformly random reads, sharding at 3 TB, splitting into microservices before naming a "
      "bottleneck — the candidate who designs the thing they were handed has failed the "
      "question. **If your options table has no row for \"do nothing\", you have not finished "
      "thinking.**")
    A("")
    A("Answers are folded. Say yours out loud first — an answer you can *recognise* is not an "
      "answer you can *give*, and the gap between the two is the entire difference between "
      "reading this page and practising with it.")
    A("")

    # --- counts ------------------------------------------------------------
    A("## Coverage")
    A("")
    A("| Track | What it probes | Basic | Interm. | Adv. | Total |")
    A("|---|---|:-:|:-:|:-:|:-:|")
    for t in TRACKS:
        counts = {lv: sum(1 for q in t["questions"] if q["level"] == lv) for lv in LEVELS}
        A(f"| [{t['name']}](#{slug(t['name'])}) | {t['blurb']} "
          f"| {counts['basic']} | {counts['intermediate']} | {counts['advanced']} "
          f"| **{len(t['questions'])}** |")
    A(f"| | | **{by_level['basic']}** | **{by_level['intermediate']}** "
      f"| **{by_level['advanced']}** | **{n_questions}** |")
    A("")
    A(f"Every question carries a `→` link to the page it came from. If an answer did not "
      f"land, that link is the fix — the question was written from that page and the page "
      f"has the reasoning at full length.")
    A("")
    A("Not sure which track to start with? The [diagnostic](../DIAGNOSTIC.md) is twelve "
      "questions that route you to one.")
    A("")

    # --- the tracks --------------------------------------------------------
    for t in TRACKS:
        A("---")
        A("")
        A(f"## {t['name']}")
        A("")
        A(f"*{t['blurb']}*")
        A("")
        pairs = numbered(t)
        for lv in LEVELS:
            group = [(qid, q) for qid, q in pairs if q["level"] == lv]
            if not group:
                continue
            A(f"### {t['name']} · {LEVEL_LABEL[lv]}")
            A("")
            for qid, q in group:
                number = int(qid.rsplit("-", 1)[1])
                L.extend(render_question(number, q))

    # --- related -----------------------------------------------------------
    A("---")
    A("")
    A("## Related")
    A("")
    A("- [Interview section index](README.md) — the 5 / 15 / 30 / 45-minute approaches")
    A("- [Design checklist](../DESIGN-CHECKLIST.md) — the 45-minute short form, minute by "
      "minute")
    A("- [System design thinking](../SYSTEM-DESIGN-THINKING.md) — the chain, and the 18-step "
      "method")
    A("- [Diagnostic](../DIAGNOSTIC.md) — twelve questions that tell you which page to open "
      "first")
    A("- [Estimation guide](../ESTIMATION-GUIDE.md) — the arithmetic, in your head")
    A("- [Trade-off framework](../TRADEOFF-FRAMEWORK.md) — how to choose out loud")
    A("- [Glossary](../GLOSSARY.md) — every term used above, defined once")
    A("")
    return "\n".join(L)


# --------------------------------------------------------------------------
# json
# --------------------------------------------------------------------------

def build_json() -> str:
    """Machine-readable form for the visualizer.

    Emitted from the same table that produces the markdown, so a question
    cannot be phrased one way on the page and another way in the app.
    """
    out = {"tracks": []}
    for t in TRACKS:
        out["tracks"].append({
            "id": t["id"],
            "name": t["name"],
            "blurb": t["blurb"],
            "questions": [
                {
                    "id": qid,
                    "level": q["level"],
                    "q": q["q"],
                    "asking": q["asking"],
                    "answer": q["answer"],
                    "redFlags": list(q["redFlags"]),
                    "followUps": [{"q": f["q"], "answer": f["answer"]}
                                  for f in q["followUps"]],
                    "seeAlso": q["seeAlso"],
                }
                for qid, q in numbered(t)
            ],
        })
    return json.dumps(out, indent=2, ensure_ascii=False) + chr(10)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    problems = validate()
    if problems:
        print("interview_data.py is invalid:")
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
            ("QUESTIONS.md", current, content),
            ("questions.json", current_json, payload),
        ) if a != b]
        if stale:
            print(f"stale: {', '.join(stale)} -- run: python scripts/gen_interview.py")
            return 1
        print("QUESTIONS.md and questions.json match the generator")
        return 0

    OUT.write_text(content, encoding="utf-8", newline="\n")
    OUT_JSON.write_text(payload, encoding="utf-8", newline="\n")
    n_q = sum(len(t["questions"]) for t in TRACKS)
    n_f = sum(len(q["followUps"]) for t in TRACKS for q in t["questions"])
    print(f"wrote {OUT.relative_to(ROOT)} ({len(content.splitlines())} lines)")
    print(f"wrote {OUT_JSON.relative_to(ROOT)} "
          f"({len(TRACKS)} tracks, {n_q} questions, {n_f} follow-ups)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
