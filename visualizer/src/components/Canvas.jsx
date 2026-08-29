import { NODE_W, NODE_H } from '../lib/layout.js'

/**
 * Shapes follow the notation contract in 19-diagrams/README.md, because the
 * whole point of a contract is that the same shape means the same thing here
 * and in every committed SVG.
 *
 * The one that carries real weight: `cache` is dashed and `store` is a
 * cylinder. Dashed means safe to lose.
 */
function Shape({ kind, x, y, className }) {
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
function edgePath(a, b) {
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

export default function Canvas({
  scene, version, positions, width, height,
  packet, activeNode, activeHopEdge, downNodes, bottleneck, edges,
}) {
  return (
    <svg
      className="canvas"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`${scene.title}, version ${version.v}: ${version.label}`}
    >
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" className="arrowhead" />
        </marker>
        <marker id="arrow-async" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" className="arrowhead async" />
        </marker>
      </defs>

      {edges.map((e, i) => {
        const a = positions[e.from]
        const b = positions[e.to]
        if (!a || !b) return null
        const dead = downNodes.has(e.from) || downNodes.has(e.to)
        const lit = activeHopEdge && activeHopEdge.from === e.from && activeHopEdge.to === e.to
        const cls = ['edge', `edge-${e.kind}`, dead && 'edge-dead', lit && 'edge-lit'].filter(Boolean).join(' ')
        const d = edgePath(a, b)
        return (
          <g key={`${e.from}-${e.to}-${i}`}>
            <path
              d={d}
              className={cls}
              markerEnd={e.kind === 'async' ? 'url(#arrow-async)' : 'url(#arrow)'}
            />
            {e.label && (
              <text className="edge-label" dy="-6">
                <textPath href={`#lbl-${i}`} startOffset="50%" textAnchor="middle">{e.label}</textPath>
              </text>
            )}
            <path id={`lbl-${i}`} d={d} fill="none" stroke="none" />
          </g>
        )
      })}

      {version.active.map(id => {
        const n = scene.nodes[id]
        const p = positions[id]
        if (!n || !p) return null
        const down = downNodes.has(id)
        const isBottleneck = bottleneck === id && !down
        // The node currently doing work is lit. Without this the packet looks
        // like it is gliding past components rather than being processed by them.
        const working = activeNode === id
        const cls = [
          'node', `node-${n.kind}`,
          down && 'node-down',
          isBottleneck && 'node-bottleneck',
          working && 'node-active',
        ].filter(Boolean).join(' ')
        return (
          <g key={id} className={cls}>
            <Shape kind={n.kind} x={p.x} y={p.y} className="node-shape" />
            <text className="node-label" x={p.cx} y={n.note ? p.cy - 3 : p.cy + 5} textAnchor="middle">
              {n.label}
            </text>
            {n.note && (
              <text className="node-note" x={p.cx} y={p.cy + 14} textAnchor="middle">{n.note}</text>
            )}
            {down && <text className="node-tag" x={p.cx} y={p.y - 8} textAnchor="middle">DOWN</text>}
            {isBottleneck && <text className="node-tag warn" x={p.cx} y={p.y - 8} textAnchor="middle">BOTTLENECK</text>}
          </g>
        )
      })}

      {packet && (
        <g
          className={packet.failed ? 'packet failed' : 'packet'}
          transform={`translate(${packet.x} ${packet.y})`}
        >
          <circle r={packet.failed ? 14 : 11} className="packet-halo" />
          <circle r="5.5" className="packet-core" />
          {packet.failed && (
            <>
              <line x1="-5" y1="-5" x2="5" y2="5" className="packet-x" />
              <line x1="5" y1="-5" x2="-5" y2="5" className="packet-x" />
            </>
          )}
        </g>
      )}
    </svg>
  )
}
