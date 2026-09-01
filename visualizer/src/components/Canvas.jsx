import { ArrowDefs, EdgeLabel, Shape, edgePath } from './shapes.jsx'

/**
 * The animated architecture canvas.
 *
 * Shapes, edge geometry and labels live in shapes.jsx so the studio and the
 * quiz draw the same picture this does -- see the note there on why a second
 * implementation would drift silently.
 */
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
      <ArrowDefs />

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
            {e.label && <EdgeLabel a={a} b={b} label={e.label} />}
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
