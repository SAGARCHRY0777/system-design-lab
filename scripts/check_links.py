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
SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".venv", ".pytest_cache"}

# Templates are written with the paths a COPY will need -- a concept page lives
# two levels deep, so its links are ../../GLOSSARY.md. Resolved from the
# template's own location those point outside the repository, correctly. The
# template is the one file whose links are supposed to be wrong where it sits.
SKIP_TREES = {"_templates"}


def markdown_files() -> list[Path]:
    out = []
    for p in ROOT.rglob("*.md"):
        parts = p.relative_to(ROOT).parts
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if parts and parts[0] in SKIP_TREES:
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


def orphans(files: list[Path]) -> list[Path]:
    """Pages that nothing links to.

    A broken link is loud -- someone clicks it and complains. An orphaned page
    is silent: it exists, it is committed, and no reader can reach it. That is
    strictly worse, and it is exactly what happened to the observability page,
    which sat on GitHub for a full commit with nothing pointing at it.
    """
    linked: set[Path] = set()
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            for target in LINK.findall(line):
                if target.startswith(SKIP_PREFIXES):
                    continue
                clean = unquote(target.split("#", 1)[0]).strip()
                if not clean:
                    continue
                r = (path.parent / clean).resolve()
                # A link to a directory counts as linking its README.
                linked.add(r / "README.md" if r.is_dir() else r)

    roots = {(ROOT / "README.md").resolve()}
    return [f for f in files if f.resolve() not in linked and f.resolve() not in roots]


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

    lost = orphans(files)
    if lost:
        print("ORPHANED -- committed but unreachable, nothing links to these:")
        for f in lost:
            print(f"        {f.relative_to(ROOT)}")

    print()
    if total_bad or lost:
        if total_bad:
            print(f"{total_bad} broken link(s) across {checked} markdown file(s)")
        if lost:
            print(f"{len(lost)} orphaned page(s)")
        return 1
    print(f"all relative links resolve, no orphans ({checked} markdown file(s) checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
