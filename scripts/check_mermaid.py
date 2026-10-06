#!/usr/bin/env python3
"""Validate every Mermaid block in the repository.

A broken Mermaid block does not fail loudly. GitHub renders it as a grey box
containing an error message, and only someone who scrolls to that exact spot
ever finds out. There is no build step to catch it, so it is checked here.

Two severities, deliberately:

  ERROR    structurally broken -- empty, no recognised diagram type, unbalanced
           brackets or quotes. These will definitely not render.
  WARNING  characters that are hazardous in the position they appear: an
           unquoted '&' or '(' inside a flowchart node label. Both end the
           label early in flowchart syntax. They do not fail the build.

           Parentheses in SEQUENCE message text were warned about here until
           the claim was tested against the bundled mermaid: every flagged
           line parsed, including 'S256(x)' and 'replicate (async, ~200ms)'.
           Message text runs to end of line and is not re-parsed, so the rule
           only ever produced false positives -- nine of them, permanently,
           which is how a warning stops being read.

    python scripts/check_mermaid.py
    python scripts/check_mermaid.py --strict   # warnings become errors
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".venv", ".pytest_cache"}

BLOCK = re.compile(r"```mermaid\n(.*?)```", re.S)

TYPES = (
    "flowchart", "graph", "sequenceDiagram", "stateDiagram-v2", "stateDiagram",
    "classDiagram", "erDiagram", "journey", "gantt", "pie", "mindmap", "timeline",
)


def first_directive(body: str) -> str | None:
    for raw in body.splitlines():
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue
        return line
    return None


def check_block(body: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    directive = first_directive(body)
    if directive is None:
        return (["empty diagram"], [])

    if not any(directive.startswith(t) for t in TYPES):
        errors.append(f"unrecognised diagram type: {directive!r}")

    content = [ln for ln in body.splitlines() if ln.strip() and not ln.strip().startswith("%%")]
    if len(content) < 2:
        errors.append("diagram has a type but no content")

    # Strip Mermaid's own syntax before counting brackets. The async message
    # arrows `-)` and `--)` contain a closing paren that is punctuation, not a
    # bracket -- counting them naively reports every correct async sequence
    # diagram as unbalanced, which is how this check first failed.
    counting = re.sub(r"--?\)", "", body)
    for pair in ("[]", "{}", "()"):
        if counting.count(pair[0]) != counting.count(pair[1]):
            errors.append(f"unbalanced {pair[0]}{pair[1]}: "
                          f"{counting.count(pair[0])} vs {counting.count(pair[1])}")
    if body.count('"') % 2:
        errors.append("odd number of double quotes")

    is_sequence = directive.startswith("sequenceDiagram")
    for i, raw in enumerate(body.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue

        # An unquoted ampersand inside a node label joins nodes in flowchart
        # syntax rather than printing.
        # A[Cache (Redis)] is a real parse error -- '(' opens a shape, so the
        # label ends early. [(cyl)], ([stadium]) and ((circle)) are shape
        # syntax, not labels, and the negative lookahead leaves them alone.
        if not is_sequence:
            for label in re.findall(r"\[(?!\(|\[)([^\[\]]*)\]", line):
                if label.startswith('"') and label.endswith('"'):
                    continue
                if "&" in label:
                    warnings.append(f"line {i}: unquoted '&' in a node label")
                if "(" in label or ")" in label:
                    warnings.append(f"line {i}: unquoted parentheses in a node label")

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = ap.parse_args()

    files = sorted(
        p for p in ROOT.rglob("*.md")
        if not any(part in SKIP_DIRS for part in p.parts)
    )

    n_blocks = n_err = n_warn = 0
    for path in files:
        for idx, body in enumerate(BLOCK.findall(path.read_text(encoding="utf-8")), 1):
            n_blocks += 1
            errors, warnings = check_block(body)
            rel = path.relative_to(ROOT)
            for e in errors:
                print(f"ERROR    {rel} block {idx}: {e}")
                n_err += 1
            for w in warnings:
                print(f"warning  {rel} block {idx}: {w}")
                n_warn += 1

    print()
    print(f"{n_blocks} mermaid block(s) across {len(files)} file(s): "
          f"{n_err} error(s), {n_warn} warning(s)")
    return 1 if n_err or (args.strict and n_warn) else 0


if __name__ == "__main__":
    sys.exit(main())
