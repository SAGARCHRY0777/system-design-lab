#!/usr/bin/env python3
"""Validate every scene against the rules in 19-diagrams/scenes/SCHEMA.md.

A scene drives both the committed SVGs and the interactive visualizer, so a
malformed one breaks two things at once and does it silently -- a flow whose
path crosses an inactive node simply renders a packet teleporting through empty
space, which looks fine and teaches something false.

Exit 0 if every scene is valid, 1 otherwise.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "19-diagrams" / "scenes"

NODE_KINDS = {"client", "edge", "lb", "service", "cache", "store", "queue", "external"}
EDGE_KINDS = {"sync", "async", "replication"}


def check_scene(path: Path) -> list[str]:
    errs: list[str] = []
    try:
        scene = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid JSON: {exc}"]

    for field in ("id", "title", "summary", "nodes", "versions"):
        if field not in scene:
            errs.append(f"missing top-level field {field!r}")
    if errs:
        return errs

    if scene["id"] != path.stem:
        errs.append(f"id {scene['id']!r} does not match filename {path.stem!r}")

    nodes = scene["nodes"]
    for nid, node in nodes.items():
        if node.get("kind") not in NODE_KINDS:
            errs.append(f"node {nid!r}: kind {node.get('kind')!r} not in {sorted(NODE_KINDS)}")
        if not node.get("label"):
            errs.append(f"node {nid!r}: missing label")

    seen_versions: set[int] = set()
    used_nodes: set[str] = set()
    prev_v = None

    for ver in scene["versions"]:
        v = ver.get("v")
        tag = f"v{v}"
        if v in seen_versions:
            errs.append(f"{tag}: duplicate version number")
        seen_versions.add(v)
        if prev_v is not None and v <= prev_v:
            errs.append(f"{tag}: versions must be in ascending order (after v{prev_v})")
        prev_v = v

        # `trigger` is the field that turns a diagram into a lesson. A version
        # without one is the thing this repository exists to avoid.
        if not ver.get("trigger"):
            errs.append(f"{tag}: missing 'trigger' -- every version must say WHY it exists")

        active = set(ver.get("active", []))
        used_nodes |= active
        for nid in active:
            if nid not in nodes:
                errs.append(f"{tag}: active node {nid!r} is not declared in 'nodes'")

        for e in ver.get("edges", []):
            if e.get("kind") not in EDGE_KINDS:
                errs.append(f"{tag}: edge {e.get('from')}->{e.get('to')} has kind {e.get('kind')!r}")
            for end in ("from", "to"):
                if e.get(end) not in active:
                    errs.append(f"{tag}: edge endpoint {e.get(end)!r} is not active")

        bn = ver.get("bottleneck")
        if bn is not None and bn not in active:
            errs.append(f"{tag}: bottleneck {bn!r} is not an active node")

        metrics = ver.get("metrics", {})
        for key in ("p50_ms", "p99_ms"):
            if key not in metrics:
                errs.append(f"{tag}: metrics missing {key}")
        if metrics.get("p99_ms", 1) < metrics.get("p50_ms", 0):
            errs.append(f"{tag}: p99 is below p50, which cannot happen")

    versions_by_v = {ver["v"]: ver for ver in scene["versions"]}

    for flow in scene.get("flows", []):
        fid = flow.get("id", "?")
        lo = flow.get("minVersion", min(seen_versions))
        hi = flow.get("maxVersion", max(seen_versions))
        for v, ver in versions_by_v.items():
            if not (lo <= v <= hi):
                continue
            active = set(ver.get("active", []))
            missing = [n for n in flow.get("path", []) if n not in active]
            if missing:
                errs.append(
                    f"flow {fid!r}: offered at v{v} but path crosses inactive node(s) {missing}"
                )
        used_nodes |= set(flow.get("path", []))

    for fail in scene.get("failures", []):
        node = fail.get("node")
        if node not in nodes:
            errs.append(f"failure {fail.get('id')!r}: node {node!r} is not declared")
        if "survivable" not in fail:
            errs.append(f"failure {fail.get('id')!r}: missing 'survivable'")
        if not fail.get("effect"):
            errs.append(f"failure {fail.get('id')!r}: missing 'effect'")
        used_nodes.add(node)

    for nid in nodes:
        if nid not in used_nodes:
            errs.append(f"node {nid!r} is declared but never used by any version, flow or failure")

    return errs


def main() -> int:
    if not SCENES.is_dir():
        print(f"no scenes directory at {SCENES}")
        return 1

    files = sorted(SCENES.glob("*.json"))
    if not files:
        print("no scenes found")
        return 1

    failed = 0
    for path in files:
        errs = check_scene(path)
        if errs:
            failed += 1
            print(f"FAIL  {path.relative_to(ROOT)}")
            for e in errs:
                print(f"        {e}")
        else:
            print(f"ok    {path.relative_to(ROOT)}")

    print()
    print(f"{len(files) - failed}/{len(files)} scenes valid")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
