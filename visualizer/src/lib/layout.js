/**
 * Layout: scenes carry no pixel coordinates, so positions are derived here.
 *
 * Nodes are placed in columns by topological rank — the longest path from any
 * source node. That is what makes the drawing read left-to-right as request
 * flow, which is the notation contract in 19-diagrams/README.md.
 *
 * Replication edges are excluded from ranking on purpose: a replica is a
 * sibling of its primary, not a step further along the request path, and
 * ranking by it would push read replicas into their own column and imply a
 * hop that does not exist.
 */

export const NODE_W = 132
export const NODE_H = 60
const COL_GAP = 88
const ROW_GAP = 30
const PAD_X = 40
const PAD_Y = 40

/** Edges that actually exist in this version, both ends active. */
export function activeEdges(version) {
  const on = new Set(version.active)
  return version.edges.filter(e => on.has(e.from) && on.has(e.to))
}

/**
 * Longest-path rank per node. Iterated to a fixpoint with an iteration cap, so
 * a cyclic scene degrades to a stable layout instead of hanging.
 */
function ranks(version) {
  const rank = {}
  version.active.forEach(id => { rank[id] = 0 })
  const edges = activeEdges(version).filter(e => e.kind !== 'replication')

  for (let pass = 0; pass < version.active.length + 1; pass++) {
    let moved = false
    for (const e of edges) {
      if (rank[e.to] < rank[e.from] + 1) {
        rank[e.to] = rank[e.from] + 1
        moved = true
      }
    }
    if (!moved) break
  }
  return rank
}

/**
 * @returns {{positions: Record<string,{x,y,cx,cy}>, width: number, height: number}}
 */
export function layout(version) {
  const rank = ranks(version)

  const columns = new Map()
  for (const id of version.active) {
    const r = rank[id] ?? 0
    if (!columns.has(r)) columns.set(r, [])
    columns.get(r).push(id)
  }

  const cols = [...columns.keys()].sort((a, b) => a - b)
  const tallest = Math.max(...cols.map(c => columns.get(c).length), 1)
  const height = PAD_Y * 2 + tallest * NODE_H + (tallest - 1) * ROW_GAP
  const width = PAD_X * 2 + cols.length * NODE_W + (cols.length - 1) * COL_GAP

  const positions = {}
  cols.forEach((c, ci) => {
    const ids = columns.get(c)
    const colH = ids.length * NODE_H + (ids.length - 1) * ROW_GAP
    const top = (height - colH) / 2
    ids.forEach((id, ri) => {
      const x = PAD_X + ci * (NODE_W + COL_GAP)
      const y = top + ri * (NODE_H + ROW_GAP)
      positions[id] = { x, y, cx: x + NODE_W / 2, cy: y + NODE_H / 2 }
    })
  })

  return { positions, width, height }
}

/**
 * Turn a flow path (node ids, possibly revisiting) into a polyline plus its
 * cumulative length, so a packet can be animated along it at constant speed
 * rather than constant time-per-hop — a long hop should visibly take longer.
 */
export function flowGeometry(path, positions) {
  const pts = path.map(id => positions[id]).filter(Boolean).map(p => ({ x: p.cx, y: p.cy }))
  const segs = []
  let total = 0
  for (let i = 0; i + 1 < pts.length; i++) {
    const a = pts[i]
    const b = pts[i + 1]
    const len = Math.hypot(b.x - a.x, b.y - a.y)
    segs.push({ a, b, len, start: total })
    total += len
  }
  return { pts, segs, total }
}

/** Point at distance `d` along the polyline, plus which hop index we are on. */
export function pointAt(geo, d) {
  if (!geo.segs.length) return { x: 0, y: 0, hop: 0 }
  const clamped = Math.max(0, Math.min(d, geo.total))
  for (let i = 0; i < geo.segs.length; i++) {
    const s = geo.segs[i]
    if (clamped <= s.start + s.len || i === geo.segs.length - 1) {
      const t = s.len === 0 ? 0 : (clamped - s.start) / s.len
      return { x: s.a.x + (s.b.x - s.a.x) * t, y: s.a.y + (s.b.y - s.a.y) * t, hop: i }
    }
  }
  return { ...geo.pts[geo.pts.length - 1], hop: geo.segs.length - 1 }
}

/** A flow is offerable on this version if every hop is active and the version is in range. */
export function flowAvailable(flow, version) {
  if (flow.minVersion && version.v < flow.minVersion) return false
  if (flow.maxVersion && version.v > flow.maxVersion) return false
  const on = new Set(version.active)
  return flow.path.every(id => on.has(id))
}
