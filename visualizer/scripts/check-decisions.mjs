/**
 * Verify every parameter decision and its grading.
 *
 * `check_scenes.py` already validates the SHAPE of a decision -- exactly one
 * correct option, a real explanation on each, a version that exists. This checks
 * the things only the app knows: that a reader can actually reach every decision
 * that was authored, and that grading returns what the UI assumes it returns.
 *
 * The reachability check exists because of a bug this very feature nearly
 * shipped with. Decisions belong to versions; briefs cover transitions between
 * versions. The URL shortener's code-length decision belongs to V1, and no brief
 * has V1 as its destination -- so the single most irreversible decision in the
 * scene was authored, validated by the Python checker, and displayed to nobody.
 * Shape validation cannot catch that. Only walking the actual UI path can.
 *
 *     npm run check:decisions
 */

import { readFile } from 'node:fs/promises'
import { buildBriefs } from '../src/lib/studio.js'
import {
  REVERSIBILITY, assignDecisions, buildDecisions, gradeDecision, verdictText,
} from '../src/lib/decisions.js'

const SCENES = ['url-shortener', 'social-feed', 'ticket-booking',
                'chat-system', 'notification-system', 'payment-system']

let fail = 0
const bad = m => { console.log('  FAIL ' + m); fail++ }
let total = 0
const byReversibility = { cheap: 0, costly: 0, 'one-way': 0 }

for (const id of SCENES) {
  const scene = JSON.parse(
    await readFile(new URL(`../../19-diagrams/scenes/${id}.json`, import.meta.url), 'utf8'),
  )
  const file = JSON.parse(
    await readFile(
      new URL(`../../19-diagrams/scenes/decisions/${id}.json`, import.meta.url), 'utf8',
    ),
  )
  if (file.scene !== id) bad(`${id}: decisions file declares scene "${file.scene}"`)

  const decisions = buildDecisions(file.decisions)
  const briefs = buildBriefs(scene)
  total += decisions.length

  // --- reachability: walk the exact path the Studio walks -----------------
  const reached = new Map()
  for (const forBrief of assignDecisions(file.decisions, briefs)) {
    for (const d of forBrief) reached.set(d.id, (reached.get(d.id) ?? 0) + 1)
  }

  for (const d of decisions) {
    if (!reached.has(d.id)) {
      bad(`${id}/${d.id}: authored at V${d.v} but no brief ever shows it`)
    } else if (reached.get(d.id) > 1) {
      bad(`${id}/${d.id}: shown by ${reached.get(d.id)} different briefs`)
    }
    byReversibility[d.reversibility]++
  }

  // --- grading ------------------------------------------------------------
  for (const d of decisions) {
    if (!REVERSIBILITY[d.reversibility]) {
      bad(`${id}/${d.id}: unknown reversibility ${d.reversibility}`)
      continue
    }

    const answer = d.options.find(o => o.verdict === 'correct')
    const g = gradeDecision(d, answer.value)
    if (!g.correct) bad(`${id}/${d.id}: the correct option does not grade correct`)
    if (g.answer?.value !== answer.value) bad(`${id}/${d.id}: grade returned the wrong answer key`)

    // Every option a reader can click must produce a usable screen: the UI
    // renders picked.because and answer.value unconditionally.
    for (const o of d.options) {
      const r = gradeDecision(d, o.value)
      if (!r.picked) bad(`${id}/${d.id}: option "${o.value}" does not grade at all`)
      if (!r.answer) bad(`${id}/${d.id}: no answer key when "${o.value}" is picked`)
      if (r.correct !== (o.verdict === 'correct')) {
        bad(`${id}/${d.id}: "${o.value}" grades as ${r.correct} for verdict ${o.verdict}`)
      }
      const [head, sub] = verdictText(o.verdict)
      if (!head || !sub) bad(`${id}/${d.id}: no verdict text for ${o.verdict}`)
    }

    // A defensible option that is never distinguished from a wrong one is just
    // a wrong one with extra words.
    if (gradeDecision(d, '__nonexistent__').picked !== null) {
      bad(`${id}/${d.id}: an unknown value graded as a real pick`)
    }

    if (d.reversal.length < 60) bad(`${id}/${d.id}: 'reversal' is a stub`)
  }

  const shape = decisions.map(d => `V${d.v}/${d.reversibility}`).join(' ')
  console.log(`${id}: ${decisions.length} decisions  ${shape}`)
}

console.log(
  `\n${byReversibility.cheap} reversible · ${byReversibility.costly} costly · `
  + `${byReversibility['one-way']} one-way`,
)

// A set of decisions that are all cheap teaches nothing about which arguments
// are worth having -- the whole point is the contrast between them.
if (byReversibility['one-way'] === 0) bad('no one-way decisions anywhere: the contrast is the lesson')

console.log(fail ? `\n${fail} problem(s)` : `${total} decisions, all reachable and grading correctly`)
process.exit(fail ? 1 : 0)
