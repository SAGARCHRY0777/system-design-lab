/**
 * Verify every generated question against the scene it came from.
 *
 * A wrong answer key is the worst possible bug in a teaching tool: it
 * confidently corrects the reader with something false. Lint cannot catch that,
 * so it is asserted here -- in particular that a flow question's answer equals
 * what buildTimeline() will actually do, since that is the animation the reader
 * then watches. If those two ever disagree, one of them is lying.
 *
 *     npm run check:quiz
 */

import { readFile } from 'node:fs/promises'
import { buildQuiz } from '../src/lib/quiz.js'
import { buildTimeline } from '../src/lib/timeline.js'

const SCENES = ['url-shortener', 'social-feed', 'ticket-booking']

let fail = 0
const bad = m => { console.log('  FAIL ' + m); fail++ }

for (const id of SCENES) {
  const scene = JSON.parse(
    await readFile(new URL(`../../19-diagrams/scenes/${id}.json`, import.meta.url), 'utf8'),
  )
  const q = buildQuiz(scene)

  const byKind = {}
  for (const x of q) byKind[x.kind] = (byKind[x.kind] ?? 0) + 1
  console.log(`${id}: ${q.length} questions  ${JSON.stringify(byKind)}`)

  // The correct answer must be among the options.
  for (const x of q) if (!x.options.includes(x.correct)) bad(`${x.id}: answer not in options`)

  // A duplicated option makes two choices simultaneously right.
  for (const x of q) if (new Set(x.options).size !== x.options.length) bad(`${x.id}: duplicate options`)

  // Three options minimum, and a real explanation to correct with.
  for (const x of q) {
    if (x.options.length < 3) bad(`${x.id}: only ${x.options.length} options`)
    if (!x.because || x.because.length < 20) bad(`${x.id}: no usable explanation`)
  }

  // The key assertion: the quiz and the animation must agree.
  for (const x of q.filter(x => x.kind === 'Request flow')) {
    const flow = scene.flows.find(f => f.id === x.replay.flowId)
    const tl = buildTimeline(scene, flow, new Set([x.replay.down]))
    const expect = scene.nodes[tl.blockedNode]?.label
    if (expect !== x.correct) bad(`${x.id}: says "${x.correct}", timeline says "${expect}"`)
  }

  // If the answer always sits in the same slot it is guessable without knowing anything.
  const spread = new Set(q.map(x => x.options.indexOf(x.correct))).size
  if (spread < 3) bad(`${id}: answer sits in only ${spread} distinct slots`)
  else console.log(`  answer position spread: ${spread} slots`)

  // Deterministic, so a reader can return to the same question.
  const again = buildQuiz(scene)
  if (JSON.stringify(again) !== JSON.stringify(q)) bad(`${id}: not deterministic`)
}

console.log(fail ? `\n${fail} problem(s)` : '\nall answer keys verified against their scenes')
process.exit(fail ? 1 : 0)
