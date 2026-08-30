/**
 * The design studio: produce an architecture rather than recognise one.
 *
 * Every other question in this repository is recognition -- pick the right
 * answer, explain why this breaks. That is not the same skill as being handed
 * requirements and a blank page, and the gap between them is the gap between
 * passing the diagnostic and doing the job.
 *
 * So a brief here is a real design step from the chain: here is the system you
 * have today, here is the traffic it now faces, here is the symptom. What do
 * you add?
 *
 * The reference answer is the next version of the scene, which means the
 * grading data already exists and cannot drift from the diagrams -- the same
 * property the quiz has.
 *
 * Scoring penalises OVER-BUILDING as heavily as under-building. That is
 * deliberate and it is the repository's whole thesis: a component added before
 * its problem exists is not foresight, and every catalogue of patterns
 * implicitly teaches the opposite by making them all look desirable.
 */

/** Components a reader should never be asked to "add" -- they are always there. */
const IMPLICIT = new Set(['client'])

/**
 * Build the briefs for a scene: one per transition between versions.
 *
 * @returns {Array<{id,scene,fromV,toV,have,options,answer,trigger,note,traffic,metrics}>}
 */
export function buildBriefs(scene) {
  const briefs = []

  for (let i = 1; i < scene.versions.length; i++) {
    const prev = scene.versions[i - 1]
    const next = scene.versions[i]

    const have = prev.active.filter(id => !IMPLICIT.has(id))
    const should = next.active.filter(id => !IMPLICIT.has(id))
    const added = should.filter(id => !have.includes(id))
    const removed = have.filter(id => !should.includes(id))

    // A step that adds nothing is a topology change rather than a design
    // decision -- V8 of the URL shortener is a regional failure, not something
    // a reader is meant to "choose". Skip it.
    if (!added.length) continue

    // The palette: everything this scene ever uses, minus what you already have.
    // Distractors are therefore real components from a real architecture, not
    // invented ones -- and several of them are correct LATER, which is the
    // point. Right component, wrong time is the most common design error.
    const options = Object.keys(scene.nodes)
      .filter(id => !IMPLICIT.has(id) && !have.includes(id))

    briefs.push({
      id: `${scene.id}-v${next.v}`,
      scene: scene.title,
      fromV: prev.v,
      toV: next.v,
      have,
      options,
      answer: added,
      removed,
      trigger: next.trigger,
      note: next.note,
      traffic: next.traffic,
      metrics: next.metrics,
      prevMetrics: prev.metrics,
    })
  }

  return briefs
}

/**
 * Grade a submission.
 *
 * `correct` / `missed` / `overbuilt` rather than a score out of ten, because
 * the two ways of being wrong are different mistakes with different lessons and
 * collapsing them into one number loses that.
 */
export function grade(brief, picked) {
  const chosen = new Set(picked)
  const answer = new Set(brief.answer)

  const correct = brief.answer.filter(id => chosen.has(id))
  const missed = brief.answer.filter(id => !chosen.has(id))
  const overbuilt = picked.filter(id => !answer.has(id))

  const perfect = missed.length === 0 && overbuilt.length === 0

  let verdict
  if (perfect) verdict = 'exact'
  else if (missed.length === 0) verdict = 'overbuilt'
  else if (overbuilt.length === 0) verdict = 'underbuilt'
  else verdict = 'mixed'

  return { correct, missed, overbuilt, perfect, verdict }
}

/**
 * Why a component was wrong HERE, which is more useful than that it was wrong.
 *
 * A component that appears later in the same scene is not a bad idea -- it is
 * a good idea too early, and saying so is the lesson.
 */
export function whyWrong(scene, brief, id) {
  const laterVersion = scene.versions.find(
    v => v.v > brief.toV && v.active.includes(id),
  )
  if (laterVersion) {
    return {
      kind: 'too-early',
      text: `Not yet — this arrives at V${laterVersion.v} (${laterVersion.label}), `
        + `and the reason is: ${laterVersion.trigger}`,
    }
  }
  return {
    kind: 'never',
    text: 'This scene never needs it. Adding a component with no problem to solve is '
      + 'complexity you pay for forever and benefit from never.',
  }
}
