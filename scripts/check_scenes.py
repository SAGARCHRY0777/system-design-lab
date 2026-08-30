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

# A decision is a parameter choice rather than a component choice: you already
# decided to shard, this is what you shard ON. `reversibility` is the field that
# earns the block its place -- a TTL is a config change and a shard key is a
# migration, and knowing which is which is the whole skill being taught.
REVERSIBILITY = {"cheap", "costly", "one-way"}
VERDICTS = {"correct", "defensible", "wrong"}


def load_decisions(scene_id: str) -> tuple[list[dict], list[str]]:
    """Decisions live in scenes/decisions/<id>.json, beside the scene.

    They are a separate file for a measured reason rather than a stylistic one:
    the app imports every scene into its main bundle because the default view
    needs them, and 33 KB of decision prose that only the lazily-loaded studio
    reads was riding along on the critical path. Splitting the file moved it into
    the chunk that actually uses it.
    """
    path = SCENES / "decisions" / f"{scene_id}.json"
    if not path.exists():
        return [], [f"no decisions file at {path.relative_to(ROOT)}"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [], [f"decisions file is invalid JSON: {exc}"]
    if data.get("scene") != scene_id:
        return [], [f"decisions file declares scene {data.get('scene')!r}, expected {scene_id!r}"]
    return data.get("decisions", []), []


def check_decisions(decisions: list[dict], versions: set[int]) -> list[str]:
    errs: list[str] = []
    seen: set[str] = set()

    for dec in decisions:
        did = dec.get("id", "?")
        tag = f"decision {did!r}"

        if did in seen:
            errs.append(f"{tag}: duplicate id")
        seen.add(did)

        for field in ("parameter", "question", "reversibility", "reversal", "options"):
            if not dec.get(field):
                errs.append(f"{tag}: missing {field!r}")
        if errs and not dec.get("options"):
            continue

        if dec.get("v") not in versions:
            errs.append(f"{tag}: v={dec.get('v')} is not a version of this scene")

        rev = dec.get("reversibility")
        if rev not in REVERSIBILITY:
            errs.append(f"{tag}: reversibility {rev!r} not in {sorted(REVERSIBILITY)}")

        options = dec.get("options", [])
        if len(options) < 3:
            errs.append(f"{tag}: {len(options)} option(s) -- fewer than three is a coin flip")

        for opt in options:
            if not opt.get("value"):
                errs.append(f"{tag}: an option has no value")
            if opt.get("verdict") not in VERDICTS:
                errs.append(f"{tag}: option {opt.get('value')!r} has verdict "
                            f"{opt.get('verdict')!r}, not in {sorted(VERDICTS)}")
            # The explanation IS the teaching. A stub here is worse than no
            # question, because it tells a reader they were wrong and not why.
            if len(opt.get("because", "")) < 60:
                errs.append(f"{tag}: option {opt.get('value')!r} has no real explanation")

        # The load-bearing invariant. Two correct answers make the decision
        # ungradeable; none makes it unwinnable. Either way a reader is told they
        # are wrong when they are not, which destroys trust in every other
        # answer in the app.
        n_correct = sum(1 for o in options if o.get("verdict") == "correct")
        if n_correct != 1:
            errs.append(f"{tag}: {n_correct} options marked 'correct' -- must be exactly 1")

    return errs


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

    decisions, load_errs = load_decisions(scene["id"])
    errs += load_errs
    errs += check_decisions(decisions, seen_versions)

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
