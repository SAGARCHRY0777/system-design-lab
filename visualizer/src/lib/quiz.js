/**
 * Derive questions from a scene.
 *
 * No new data and no new schema field. A scene already carries
 * versions[].trigger, versions[].bottleneck, versions[].metrics,
 * failures[].effect and flows[].outcome -- those ARE question/answer pairs.
 * The app simply never asked them.
 *
 * Every answer key comes from the scene itself, and the `flow` generator
 * defers to buildTimeline(), which is the same function the animation uses.
 * That matters: if the quiz computed its own answer it could disagree with what
 * the reader is about to watch happen.
 *
 * Deterministic. Question order is derived from the scene, never shuffled
 * randomly, so a reader can return to the same question and a test can assert
 * against it.
 */

import { buildTimeline } from './timeline.js'

/** Rotate a list so `keep` is at `idx` -- deterministic option placement. */
function placeAt(options, correct, idx) {
  const others = options.filter(o => o !== correct)
  const out = [...others]
  out.splice(Math.min(idx, out.length), 0, correct)
  return out
}

function label(scene, id) {
  return scene.nodes[id]?.label ?? id
}

/** "Which component saturates first?" -- answer is versions[].bottleneck. */
function bottleneckQuestions(scene) {
  return scene.versions
    .filter(v => v.bottleneck)
    .map((v, i) => {
      const correct = label(scene, v.bottleneck)
      // Distractors come from the active set first -- a component that is
      // actually present is a far better wrong answer than one that is not.
      // But a small version may not hold three of them, which produced a
      // two-option question and a coin flip. Top up from the rest of the scene
      // before giving up.
      const active = v.active
        .filter(id => id !== v.bottleneck && scene.nodes[id]?.kind !== 'client')
      const spare = Object.keys(scene.nodes)
        .filter(id => id !== v.bottleneck && !active.includes(id)
          && scene.nodes[id]?.kind !== 'client')
      const pool = [...active, ...spare].map(id => label(scene, id))
      return {
        id: `bottleneck-${v.v}`,
        kind: 'Bottleneck',
        version: v.v,
        prompt: `At V${v.v} — ${v.label} — which component saturates first?`,
        options: placeAt([...pool.slice(0, 3), correct], correct, i % 4),
        correct,
        because: v.note ?? v.trigger,
      }
    })
    // A question with fewer than three options is a coin flip wearing a
    // question mark. Drop it rather than ask it.
    .filter(q => q.options.length >= 3)
}

/**
 * "If X dies, what happens?" -- answer is failures[].survivable.
 * Three options rather than two, so a coin flip does not look like knowledge.
 */
const OUTCOMES = [
  'Degraded — the system keeps serving',
  'Total outage — nothing completes',
  'No effect at all',
]

function failureQuestions(scene) {
  return scene.failures.map((f, i) => {
    const correct = f.survivable ? OUTCOMES[0] : OUTCOMES[1]
    return {
      id: `failure-${f.id}`,
      kind: 'Failure',
      version: f.minVersion ?? 1,
      prompt: `${label(scene, f.node)} goes down. What happens?`,
      options: placeAt(OUTCOMES, correct, i % 3),
      correct,
      because: f.effect,
    }
  })
}

/** "What forced V(n)?" -- answer is versions[].trigger, distractors are the others. */
function evolutionQuestions(scene) {
  const triggers = scene.versions.map(v => v.trigger)
  return scene.versions.slice(1).map((v, i) => {
    const others = triggers.filter(t => t !== v.trigger).slice(0, 3)
    return {
      id: `evolution-${v.v}`,
      kind: 'Evolution',
      version: v.v,
      prompt: `The architecture moved to V${v.v} (${v.label}). What forced the change?`,
      options: placeAt([...others, v.trigger], v.trigger, i % 4),
      correct: v.trigger,
      because: v.note ?? `That is the trigger recorded for V${v.v}.`,
    }
  })
}

/**
 * "With X down, where does the request stop?"
 *
 * The answer key is buildTimeline().blockedNode -- the same computation that
 * drives the animation, so the quiz cannot disagree with what the reader then
 * watches happen.
 */
function flowQuestions(scene) {
  const out = []
  for (const v of scene.versions) {
    const active = new Set(v.active)
    const flow = scene.flows.find(
      f => (f.minVersion ?? 1) <= v.v && v.v <= (f.maxVersion ?? 1e9)
        && f.path.every(n => active.has(n)) && f.path.length > 3,
    )
    if (!flow) continue

    const candidates = scene.failures.filter(
      f => active.has(f.node) && flow.path.includes(f.node)
        && (f.minVersion ?? 1) <= v.v,
    )
    if (!candidates.length) continue

    const fail = candidates[0]
    const tl = buildTimeline(scene, flow, new Set([fail.node]))
    if (!tl.blockedNode) continue

    const correct = label(scene, tl.blockedNode)
    const pool = [...new Set(flow.path)]
      .filter(n => n !== tl.blockedNode)
      .map(n => label(scene, n))

    out.push({
      id: `flow-${v.v}-${fail.node}`,
      kind: 'Request flow',
      version: v.v,
      prompt: `V${v.v}: ${label(scene, fail.node)} is down. Running "${flow.label}" — `
        + 'where does the request stop?',
      options: placeAt([...pool.slice(0, 3), correct], correct, out.length % 4),
      correct,
      because: fail.effect,
      // Lets the UI offer "watch it happen" with the right state pre-set.
      replay: { version: v.v, flowId: flow.id, down: fail.node },
    })
  }
  return out
}

/** All questions for a scene, ordered easiest-first by version. */
export function buildQuiz(scene) {
  const all = [
    ...evolutionQuestions(scene),
    ...failureQuestions(scene),
    ...flowQuestions(scene),
    ...bottleneckQuestions(scene),
  ]
  return all.sort((a, b) => a.version - b.version || a.id.localeCompare(b.id))
}
