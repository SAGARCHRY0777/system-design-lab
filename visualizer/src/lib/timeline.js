/**
 * Turn a flow path into a timeline of simulated work.
 *
 * The first version of this animated a dot along a polyline at constant speed.
 * It looked wrong because it WAS wrong: a real request does not spend its life
 * in transit at uniform velocity. It spends most of its time sitting inside
 * components doing work, and the components differ by orders of magnitude --
 * a cache lookup and a database query are not the same event drawn twice.
 *
 * So a flow becomes an alternating sequence:
 *
 *     travel(edge)  dwell(node)  travel(edge)  dwell(node)  ...
 *
 * with each segment given a duration in SIMULATED milliseconds. The packet then
 * visibly pauses inside the database and barely touches the cache, and the
 * running latency total makes the difference countable rather than decorative.
 *
 * The numbers below are ILLUSTRATIVE ORDERS OF MAGNITUDE, not measurements.
 * Their job is to make the ratios legible -- a database round trip costing ~30x
 * a cache hit is the point. A scene may override any of them.
 */

/** Simulated processing cost inside a component, in milliseconds. */
export const NODE_MS = {
  client: 0,
  edge: 1,
  lb: 1,
  gateway: 2,
  service: 4,
  cache: 1,
  store: 30,
  queue: 2,
  worker: 25,
  external: 60,
}

/** Simulated network cost of one hop, in milliseconds. */
const HOP_MS = 1
/** Client hops cross the public internet rather than a datacentre fabric. */
const CLIENT_HOP_MS = 22

function hopCost(scene, fromId, toId) {
  const a = scene.nodes[fromId]
  const b = scene.nodes[toId]
  if (a?.kind === 'client' || b?.kind === 'client') return CLIENT_HOP_MS
  // An edge PoP is near the user; reaching origin from it is a long hop.
  if (a?.kind === 'edge' || b?.kind === 'edge') return 12
  return HOP_MS
}

function nodeCost(scene, id) {
  const n = scene.nodes[id]
  if (!n) return 0
  return n.ms ?? NODE_MS[n.kind] ?? 2
}

/**
 * Build the timeline.
 *
 * @returns {{steps:Array, totalMs:number, blockedAt:number|null, blockedNode:string|null}}
 *   steps  – {type:'travel'|'dwell', ms, startMs, from?, to?, node?}
 *   blockedAt – index of the step where a downed component stops the request
 */
export function buildTimeline(scene, flow, downNodes) {
  const steps = []
  let t = 0
  let blockedAt = null
  let blockedNode = null

  const push = s => {
    steps.push({ ...s, startMs: t })
    t += s.ms
  }

  const path = flow.path
  for (let i = 0; i < path.length; i++) {
    const id = path[i]

    // A request cannot pass through something that is down. It reaches the
    // component, fails there, and goes no further -- which is the entire point
    // of being able to switch a component off.
    if (downNodes.has(id)) {
      blockedAt = steps.length
      blockedNode = id
      push({ type: 'dwell', ms: 220, node: id, failed: true })
      break
    }

    push({ type: 'dwell', ms: nodeCost(scene, id), node: id })

    if (i + 1 < path.length) {
      const next = path[i + 1]
      if (downNodes.has(next)) {
        // Still travel to it -- the packet should visibly arrive and then fail,
        // rather than vanishing mid-edge.
        push({ type: 'travel', ms: hopCost(scene, id, next), from: id, to: next })
        blockedAt = steps.length
        blockedNode = next
        push({ type: 'dwell', ms: 220, node: next, failed: true })
        break
      }
      push({ type: 'travel', ms: hopCost(scene, id, next), from: id, to: next })
    }
  }

  return { steps, totalMs: t, blockedAt, blockedNode }
}

/**
 * Where is the packet at simulated time `ms`, and what is it doing?
 *
 * @returns {{x,y,activeNode,edge,elapsedMs,failed}|null}
 */
export function sampleTimeline(timeline, positions, ms) {
  const { steps } = timeline
  if (!steps.length) return null

  const clamped = Math.max(0, Math.min(ms, timeline.totalMs))
  let step = steps[steps.length - 1]
  for (const s of steps) {
    if (clamped < s.startMs + s.ms) { step = s; break }
  }

  if (step.type === 'dwell') {
    const p = positions[step.node]
    if (!p) return null
    return {
      x: p.cx, y: p.cy,
      activeNode: step.node,
      edge: null,
      elapsedMs: clamped,
      failed: !!step.failed,
    }
  }

  const a = positions[step.from]
  const b = positions[step.to]
  if (!a || !b) return null
  const f = step.ms === 0 ? 1 : (clamped - step.startMs) / step.ms
  return {
    x: a.cx + (b.cx - a.cx) * f,
    y: a.cy + (b.cy - a.cy) * f,
    activeNode: null,
    edge: { from: step.from, to: step.to },
    elapsedMs: clamped,
    failed: false,
  }
}
