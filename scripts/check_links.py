#!/usr/bin/env python3
"""Verify every relative markdown link resolves to a real file.

The cross-link graph IS the value of this repository -- a concept is explained
once and linked from everywhere else, so a dead link is not cosmetic, it is a
hole in the knowledge graph. This is the check most worth having.

Skips absolute URLs, mailto:, and pure anchors. Anchor fragments on relative
links are stripped before resolving, so `../GLOSSARY.md#quorum` is validated as
`../GLOSSARY.md`.

Exit 0 if every link resolves, 1 otherwise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent

# [text](target) -- avoids images only in the sense that ![...] also matches,
# which is intended: a broken image path is just as much a hole.
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")

SKIP_PREFIXES = ("http://", "https://", "mailto:", "#", "tel:", "data:")
SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".venv"}


def markdown_files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out.append(p)
    return sorted(out)


def check(path: Path) -> list[tuple[int, str]]:
    bad: list[tuple[int, str]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for target in LINK.findall(line):
            if target.startswith(SKIP_PREFIXES):
                continue
            clean = unquote(target.split("#", 1)[0]).strip()
            if not clean:
                continue  # pure anchor into the same document
            resolved = (path.parent / clean).resolve()
            if not resolved.exists():
                bad.append((lineno, target))
    return bad


def main() -> int:
    files = markdown_files()
    total_bad = 0
    checked = 0

    for path in files:
        bad = check(path)
        checked += 1
        if bad:
            total_bad += len(bad)
            print(f"FAIL  {path.relative_to(ROOT)}")
            for lineno, target in bad:
                print(f"        line {lineno}: {target}")

    print()
    if total_bad:
        print(f"{total_bad} broken link(s) across {checked} markdown file(s)")
        return 1
    print(f"all relative links resolve ({checked} markdown file(s) checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
