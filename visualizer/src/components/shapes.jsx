import { NODE_W, NODE_H } from '../lib/layout.js'

/**
 * Node shapes and edge geometry, shared by every diagram in the app.
 *
 * Extracted from Canvas so the studio and the quiz can draw the same
 * architecture the animation draws. A second implementation would drift, and
 * the drift would be silent: two pictures of the same system, both plausible,
 * disagreeing about which box is a cylinder.
 *
 * Shapes follow the notation contract in 19-diagrams/README.md, because the
 * point of a contract is that the same shape means the same thing here and in
 * every committed SVG. The one that carries real weight: `cache` is dashed and
 * `store` is a cylinder. Dashed means safe to lose.
 */
export function Shape({ kind, x, y, className }) {
  const w = NODE_W
  const h = NODE_H
  const common = { className, vectorEffect: 'non-scaling-stroke' }

  switch (kind) {
    case 'client':
      return <rect {...common} x={x} y={y} width={w} height={h} rx={26} />

    case 'edge': {
      const i = 16
      return <polygon {...common} points={`${x + i},${y} ${x + w - i},${y} ${x + w},${y + h} ${x},${y + h}`} />
    }

    case 'lb': {
      const i = 18
      return (
        <polygon
          {...common}
          points={`${x + i},${y} ${x + w - i},${y} ${x + w},${y + h / 2} ${x + w - i},${y + h} ${x + i},${y + h} ${x},${y + h / 2}`}
        />
      )
    }

    case 'cache':
      return <rect {...common} x={x} y={y} width={w} height={h} rx={6} strokeDasharray="7 5" />

    case 'store': {
      const ry = 9
      return (
        <g className={className}>
          <path
            vectorEffect="non-scaling-stroke"
            d={`M${x},${y + ry} a${w / 2},${ry} 0 0 1 ${w},0 v${h - ry * 2} a${w / 2},${ry} 0 0 1 ${-w},0 z`}
          />
          <path
            vectorEffect="non-scaling-stroke"
            fill="none"
            d={`M${x},${y + ry} a${w / 2},${ry} 0 0 0 ${w},0`}
          />
        </g>
      )
    }

    case 'queue': {
      const n = 3
      return (
        <g className={className}>
          <rect vectorEffect="non-scaling-stroke" x={x} y={y} width={w} height={h} rx={4} />
          {Array.from({ length: n - 1 }, (_, i) => (
            <line
              key={i}
              vectorEffect="non-scaling-stroke"
              x1={x + (w / n) * (i + 1)}
              y1={y + 8}
              x2={x + (w / n) * (i + 1)}
              y2={y + h - 8}
              opacity="0.35"
            />
          ))}
        </g>
      )
    }

    default:
      return <rect {...common} x={x} y={y} width={w} height={h} rx={6} />
  }
}

/**
 * Edge path. Same-column edges (replication between siblings) bow outward so
 * they do not disappear behind the nodes they connect.
 */
export function edgePath(a, b) {
  const dx = b.cx - a.cx
  if (Math.abs(dx) < 4) {
    const bow = 54
    return `M${a.cx + NODE_W / 2 - 8},${a.cy} C${a.cx + bow},${a.cy} ${b.cx + bow},${b.cy} ${b.cx + NODE_W / 2 - 8},${b.cy}`
  }
  const fromX = dx > 0 ? a.cx + NODE_W / 2 : a.cx - NODE_W / 2
  const toX = dx > 0 ? b.cx - NODE_W / 2 - 9 : b.cx + NODE_W / 2 + 9
  const mid = (fromX + toX) / 2
  return `M${fromX},${a.cy} C${mid},${a.cy} ${mid},${b.cy} ${toX},${b.cy}`
}

/** The two arrowheads every diagram needs. Rendered once per <svg>. */
export function ArrowDefs() {
  return (
    <defs>
      <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" className="arrowhead" />
      </marker>
      <marker id="arrow-async" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" className="arrowhead async" />
      </marker>
    </defs>
  )
}

/**
 * An edge label: plain text at the midpoint on a background plate, NOT a
 * textPath. A textPath is clipped to the length of its path, so "SELECT then
 * UPDATE" on a short edge rendered as "ELECT then UPDAT" -- trimmed at both
 * ends, which reads as a typo rather than a layout bug.
 */
export function EdgeLabel({ a, b, label }) {
  const mx = (a.cx + b.cx) / 2
  const my = (a.cy + b.cy) / 2 - 9
  const w = label.length * 5.4 + 8
  return (
    <g className="edge-label-g">
      <rect x={mx - w / 2} y={my - 8} width={w} height={12} rx={2} className="edge-label-bg" />
      <text className="edge-label" x={mx} y={my} textAnchor="middle">{label}</text>
    </g>
  )
}
