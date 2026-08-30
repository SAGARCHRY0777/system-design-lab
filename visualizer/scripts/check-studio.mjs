/**
 * Verify every design brief and its grading.
 *
 * The studio tells a reader their architecture was wrong. If the reference
 * answer or the grading is itself wrong, it does that confidently and teaches
 * something false -- the same hazard as a bad quiz answer key, and equally
 * invisible to a linter.
 *
 * The properties that matter: the correct answer must grade perfect, an extra
 * component must be caught as over-building, an empty submission must be caught
 * as under-building, and every option a reader can click must have an
 * explanation for why it was wrong here.
 *
 *     npm run check:studio
 */

import { readFile } from 'node:fs/promises'
import { buildBriefs, grade, whyWrong } from '../src/lib/studio.js'

const SCENES = ['url-shortener', 'social-feed', 'ticket-booking']

let fail = 0
const bad = m => { console.log('  FAIL ' + m); fail++ }
let total = 0

for (const id of SCENES) {
  const scene = JSON.parse(
    await readFile(new URL(`../../19-diagrams/scenes/${id}.json`, import.meta.url), 'utf8'),
  )
  const briefs = buildBriefs(scene)
  total += briefs.length
  console.log(`${id}: ${briefs.length} design briefs`)

  for (const b of briefs) {
    if (!b.answer.length) bad(`${b.id}: nothing to add — should have been skipped`)
    if (!b.options.length) bad(`${b.id}: no options offered`)
    if (!b.trigger || b.trigger.length < 15) bad(`${b.id}: no usable symptom to design against`)

    // Every correct component must actually be clickable.
    for (const a of b.answer) {
      if (!b.options.includes(a)) bad(`${b.id}: answer "${a}" is not in the palette`)
    }

    // The reference answer must grade perfect, or the studio is unwinnable.
    if (!grade(b, b.answer).perfect) bad(`${b.id}: the reference answer does not grade perfect`)

    // Both failure directions must be detected, and distinguished.
    if (grade(b, []).verdict !== 'underbuilt') bad(`${b.id}: empty submission not flagged underbuilt`)
    const extra = b.options.find(o => !b.answer.includes(o))
    if (extra) {
      if (grade(b, [...b.answer, extra]).verdict !== 'overbuilt') {
        bad(`${b.id}: over-building not detected`)
      }
      const w = whyWrong(scene, b, extra)
      if (!w.text || w.text.length < 20) bad(`${b.id}: no explanation for wrongly adding "${extra}"`)
    }
  }
}

console.log(fail ? `\n${fail} problem(s)` : `\n${total} briefs, all grading correctly`)
process.exit(fail ? 1 : 0)
