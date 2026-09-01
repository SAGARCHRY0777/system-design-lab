import { useMemo } from 'react'
import { activeEdges, layout } from '../lib/layout.js'
import { ArrowDefs, EdgeLabel, Shape, edgePath } from './shapes.jsx'

/**
 * A static architecture diagram.
 *
 * The animated canvas answers "what happens when a request runs". This answers
 * the simpler question the rest of the app kept assuming had been answered:
 * *what does this thing look like*. The studio asked readers to add components
 * to a system they could not see and the quiz asked which component saturates
 * without showing them the system either -- both are drawing on a mental
 * picture the reader has to hold themselves.
 *
 * It renders any `{active, edges}` pair, so it draws a real version of a scene
 * and equally a SYNTHETIC one: the architecture a reader just built out of
 * their own choices, which is what makes the studio's before/after possible.
 *
 * `status` colours individual nodes -- added, missing, extra -- so the same
 * component serves as both the diagram and the mark scheme.
 */
export default function SceneDiagram({
  scene, active, edges, status = {}, title, caption, compact = false,
}) {
  const version = useMemo(() => {
    const on = new Set(active)
    return { v: 0, active: [...active], edges: (edges ?? []).filter(e => on.has(e.from) && on.has(e.to)) }
  }, [active, edges])

  const { positions, width, height } = useMemo(() => layout(version), [version])
  const drawn = useMemo(() => activeEdges(version), [version])

  if (!active.length) {
    return (
      <div className="sd-empty">
        <p className="hint">Nothing selected — an empty architecture is a valid answer, and
        occasionally the right one.</p>
      </div>
    )
  }

  return (
    <figure className={compact ? 'sd sd-compact' : 'sd'}>
      {title && <figcaption className="sd-title">{title}</figcaption>}
      <div className="sd-scroll">
        <svg
          className="canvas"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={title ?? `${scene.title} architecture`}
        >
          <ArrowDefs />

          {drawn.map((e, i) => {
            const a = positions[e.from]
            const b = positions[e.to]
            if (!a || !b) return null
            // An edge into a node the reader should not have added is drawn
            // faint, so an over-built component does not look load-bearing.
            const faint = status[e.from] === 'extra' || status[e.to] === 'extra'
            const cls = ['edge', `edge-${e.kind}`, faint && 'edge-faint'].filter(Boolean).join(' ')
            return (
              <g key={`${e.from}-${e.to}-${i}`}>
                <path
                  d={edgePath(a, b)}
                  className={cls}
                  markerEnd={e.kind === 'async' ? 'url(#arrow-async)' : 'url(#arrow)'}
                />
                {e.label && !compact && <EdgeLabel a={a} b={b} label={e.label} />}
              </g>
            )
          })}

          {version.active.map(id => {
            const n = scene.nodes[id]
            const p = positions[id]
            if (!n || !p) return null
            const st = status[id]
            const cls = ['node', `node-${n.kind}`, st && `sd-${st}`].filter(Boolean).join(' ')
            const TAG = {
              added: 'ADDED', missing: 'MISSING', extra: 'NOT YET',
              answer: 'THE ANSWER', down: 'DOWN',
            }
            return (
              <g key={id} className={cls}>
                <Shape kind={n.kind} x={p.x} y={p.y} className="node-shape" />
                <text
                  className="node-label"
                  x={p.cx}
                  y={n.note && !compact ? p.cy - 3 : p.cy + 5}
                  textAnchor="middle"
                >
                  {n.label}
                </text>
                {n.note && !compact && (
                  <text className="node-note" x={p.cx} y={p.cy + 14} textAnchor="middle">{n.note}</text>
                )}
                {TAG[st] && (
                  <text className={`node-tag sd-tag-${st}`} x={p.cx} y={p.y - 8} textAnchor="middle">
                    {TAG[st]}
                  </text>
                )}
              </g>
            )
          })}
        </svg>
      </div>
      {caption && <figcaption className="sd-caption">{caption}</figcaption>}
    </figure>
  )
}
