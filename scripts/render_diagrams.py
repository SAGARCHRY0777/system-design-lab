#!/usr/bin/env python3
"""Render each scene version to an animated SVG committed into the repository.

Why generate rather than hand-draw: the same scene file drives the interactive
visualizer. Hand-drawn diagrams drift from the app within about two edits, and
a reader has no way to tell which one is lying.

SMIL <animateMotion> is used rather than CSS because GitHub renders markdown
images in a context where CSS animation does not run but SMIL does -- the same
mechanism the animated SVGs on the profile README rely on.

    python scripts/render_diagrams.py            # write SVGs
    python scripts/render_diagrams.py --check    # fail if any committed SVG is stale

Layout mirrors visualizer/src/lib/layout.js. The two must agree, so any change
here needs the same change there; check_scenes.py does not catch a divergence.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
SCENES = ROOT / "19-diagrams" / "scenes"
OUT = ROOT / "19-diagrams" / "generated"

NODE_W, NODE_H = 132, 60
COL_GAP, ROW_GAP = 88, 30
PAD_X, PAD_Y = 40, 40
SPEED = 260.0  # px/sec, matching the app so motion reads the same in both

CSS = """
.bg{fill:#0e1414}
.shape{fill:#111818;stroke:#344544;stroke-width:1.6}
.shape.cache{stroke-dasharray:7 5}
.shape.bottleneck{stroke:#d9a441;stroke-width:2.2}
.lbl{fill:#e4ecea;font:500 12.5px system-ui,sans-serif}
.note{fill:#6f817d;font:10px system-ui,sans-serif}
.edge{fill:none;stroke:#344544;stroke-width:1.6}
.edge.async{stroke-dasharray:6 5}
.edge.replication{stroke-dasharray:2 4;stroke-width:2.6;opacity:.8}
.elbl{fill:#6f817d;font:10px system-ui,sans-serif}
.head{fill:#344544}
.title{fill:#e4ecea;font:600 14px system-ui,sans-serif}
.sub{fill:#9fb0ac;font:12px system-ui,sans-serif}
.tag{fill:#4fc3a1;font:600 11px ui-monospace,monospace}
.halo{fill:#4fc3a1;opacity:.2}
.core{fill:#4fc3a1}
"""


def ranks(version: dict) -> dict[str, int]:
    rank = {n: 0 for n in version["active"]}
    edges = [e for e in version["edges"] if e["kind"] != "replication"]
    for _ in range(len(version["active"]) + 1):
        moved = False
        for e in edges:
            if rank[e["to"]] < rank[e["from"]] + 1:
                rank[e["to"]] = rank[e["from"]] + 1
                moved = True
        if not moved:
            break
    return rank


def layout(version: dict):
    rank = ranks(version)
    cols: dict[int, list[str]] = {}
    for nid in version["active"]:
        cols.setdefault(rank[nid], []).append(nid)

    keys = sorted(cols)
    tallest = max((len(cols[c]) for c in keys), default=1)
    height = PAD_Y * 2 + tallest * NODE_H + (tallest - 1) * ROW_GAP
    width = PAD_X * 2 + len(keys) * NODE_W + (len(keys) - 1) * COL_GAP

    pos = {}
    for ci, c in enumerate(keys):
        ids = cols[c]
        col_h = len(ids) * NODE_H + (len(ids) - 1) * ROW_GAP
        top = (height - col_h) / 2
        for ri, nid in enumerate(ids):
            x = PAD_X + ci * (NODE_W + COL_GAP)
            y = top + ri * (NODE_H + ROW_GAP)
            pos[nid] = (x, y, x + NODE_W / 2, y + NODE_H / 2)
    return pos, width, height


def shape(kind: str, x: float, y: float, extra: str) -> str:
    w, h = NODE_W, NODE_H
    cls = f"shape {kind}{extra}"
    if kind == "client":
        return f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="26"/>'
    if kind == "edge":
        i = 16
        return f'<polygon class="{cls}" points="{x+i},{y} {x+w-i},{y} {x+w},{y+h} {x},{y+h}"/>'
    if kind == "lb":
        i = 18
        pts = f"{x+i},{y} {x+w-i},{y} {x+w},{y+h/2} {x+w-i},{y+h} {x+i},{y+h} {x},{y+h/2}"
        return f'<polygon class="{cls}" points="{pts}"/>'
    if kind == "store":
        ry = 9
        body = f"M{x},{y+ry} a{w/2},{ry} 0 0 1 {w},0 v{h-ry*2} a{w/2},{ry} 0 0 1 {-w},0 z"
        lip = f"M{x},{y+ry} a{w/2},{ry} 0 0 0 {w},0"
        return (f'<path class="{cls}" d="{body}"/>'
                f'<path class="{cls}" fill="none" d="{lip}"/>')
    if kind == "queue":
        bars = "".join(
            f'<line class="{cls}" x1="{x+(w/3)*(i+1)}" y1="{y+8}" '
            f'x2="{x+(w/3)*(i+1)}" y2="{y+h-8}" opacity="0.35"/>'
            for i in range(2)
        )
        return f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="4"/>{bars}'
    return f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="6"/>'


def edge_path(a, b) -> str:
    ax, ay, acx, acy = a
    bx, by, bcx, bcy = b
    if abs(bcx - acx) < 4:
        bow = 54
        return (f"M{acx + NODE_W/2 - 8},{acy} C{acx+bow},{acy} "
                f"{bcx+bow},{bcy} {bcx + NODE_W/2 - 8},{bcy}")
    fwd = bcx > acx
    fx = acx + NODE_W / 2 if fwd else acx - NODE_W / 2
    tx = bcx - NODE_W / 2 - 9 if fwd else bcx + NODE_W / 2 + 9
    mid = (fx + tx) / 2
    return f"M{fx},{acy} C{mid},{acy} {mid},{bcy} {tx},{bcy}"


def pick_flow(scene: dict, version: dict):
    """The flow a static reader most needs to see: the primary request path."""
    v = version["v"]
    active = set(version["active"])
    candidates = [
        f for f in scene.get("flows", [])
        if f.get("minVersion", 1) <= v <= f.get("maxVersion", 10**9)
        and all(n in active for n in f["path"])
    ]
    if not candidates:
        return None
    # Prefer the longest path -- it exercises the most of the architecture.
    return max(candidates, key=lambda f: len(f["path"]))


def render(scene: dict, version: dict) -> str:
    pos, width, height = layout(version)
    head = 62
    total_h = height + head

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {total_h}" '
        f'width="{width}" height="{total_h}" role="img" '
        f'aria-label="{escape(scene["title"])} version {version["v"]}: {escape(version["label"])}">',
        f"<style>{CSS}</style>",
        f'<rect class="bg" width="{width}" height="{total_h}"/>',
        f'<text class="tag" x="{PAD_X}" y="26">V{version["v"]}</text>',
        f'<text class="title" x="{PAD_X + 30}" y="26">{escape(scene["title"])}</text>',
        f'<text class="sub" x="{PAD_X}" y="46">{escape(version["label"])} · '
        f'p50 {version["metrics"]["p50_ms"]}ms · p99 {version["metrics"]["p99_ms"]}ms</text>',
        f'<g transform="translate(0 {head})">',
    ]

    on = set(version["active"])
    for i, e in enumerate(version["edges"]):
        if e["from"] not in on or e["to"] not in on:
            continue
        d = edge_path(pos[e["from"]], pos[e["to"]])
        parts.append(f'<path id="e{i}" class="edge {e["kind"]}" d="{d}"/>')
        if e.get("label"):
            parts.append(
                f'<text class="elbl" dy="-6"><textPath href="#e{i}" '
                f'startOffset="50%" text-anchor="middle">{escape(e["label"])}</textPath></text>'
            )

    for nid in version["active"]:
        node = scene["nodes"][nid]
        x, y, cx, cy = pos[nid]
        extra = " bottleneck" if version.get("bottleneck") == nid else ""
        parts.append(shape(node["kind"], x, y, extra))
        ly = cy - 3 if node.get("note") else cy + 5
        parts.append(f'<text class="lbl" x="{cx}" y="{ly}" text-anchor="middle">{escape(node["label"])}</text>')
        if node.get("note"):
            parts.append(f'<text class="note" x="{cx}" y="{cy+14}" text-anchor="middle">{escape(node["note"])}</text>')

    flow = pick_flow(scene, version)
    if flow:
        pts = [(pos[n][2], pos[n][3]) for n in flow["path"]]
        d = "M" + " L".join(f"{x},{y}" for x, y in pts)
        length = sum(
            ((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** 0.5
            for i in range(len(pts) - 1)
        )
        dur = max(1.6, length / SPEED)
        parts.append(
            f'<g><circle class="halo" r="11"/><circle class="core" r="5.5"/>'
            f'<animateMotion dur="{dur:.2f}s" repeatCount="indefinite" path="{d}"/></g>'
        )

    parts.append("</g></svg>")
    return "\n".join(parts) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if any committed SVG differs from what the scene produces")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    stale, written = [], 0

    for path in sorted(SCENES.glob("*.json")):
        scene = json.loads(path.read_text(encoding="utf-8"))
        for version in scene["versions"]:
            svg = render(scene, version)
            dest = OUT / f"{scene['id']}-v{version['v']}.svg"
            current = dest.read_text(encoding="utf-8") if dest.exists() else None
            if current == svg:
                continue
            if args.check:
                stale.append(dest.relative_to(ROOT))
            else:
                dest.write_text(svg, encoding="utf-8", newline="\n")
                written += 1

    if args.check:
        if stale:
            print("Stale diagrams -- run: python scripts/render_diagrams.py")
            for s in stale:
                print(f"  {s}")
            return 1
        print("all committed diagrams match their scenes")
        return 0

    print(f"wrote {written} diagram(s) to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
