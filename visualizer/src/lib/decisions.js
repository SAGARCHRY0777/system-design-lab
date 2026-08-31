/**
 * Parameter decisions: the second half of designing something.
 *
 * The studio asks "what do you add". That is the visible half of design, and it
 * is the half that gets rehearsed, because it is what a whiteboard diagram
 * shows. The other half is what you SET it to -- the shard key, the TTL, the
 * replication mode, the timeout -- and that is the half that ends up in the
 * postmortem. Nobody writes "we should not have used a cache". They write "the
 * TTL was wrong" and "we sharded on the wrong column".
 *
 * The organising idea is `reversibility`, not correctness. Getting a TTL wrong
 * costs an afternoon; getting a shard key wrong costs a quarter. An engineer who
 * knows which is which can defer the cheap decisions and spend their argument on
 * the expensive ones, and that judgement is the actual deliverable here.
 *
 * Three verdicts rather than two, because real parameter choices are not binary.
 * A `defensible` option is one a competent engineer would pick for reasons worth
 * hearing -- marking it simply "wrong" would teach that design has one right
 * answer, which is the belief this whole repository exists to dismantle.
 */

/**
 * How reversible a decision is, rendered as a badge.
 *
 * The wording is deliberately about cost and time rather than difficulty: "a
 * config change" and "a migration" mean something to an engineer in a way that
 * "hard" does not.
 */
export const REVERSIBILITY = {
  'cheap': {
    label: 'Reversible',
    blurb: 'A config change. Get it wrong, notice, fix it the same day.',
    weight: 0,
  },
  'costly': {
    label: 'Costly to reverse',
    blurb: 'Reversing this means changing code that already depends on it, '
      + 'or repairing data that was written under the old assumption.',
    weight: 1,
  },
  'one-way': {
    label: 'One-way door',
    blurb: 'You do not get to change your mind. Reversing it is a migration '
      + 'measured in months, or it is simply not possible.',
    weight: 2,
  },
}

/**
 * Order a scene's decisions: by version, then hardest-to-reverse first.
 *
 * Within one version the one-way door is presented before the config flag, so a
 * reader meets the ranking in the order that teaches it.
 */
export function buildDecisions(decisions) {
  // Unknown reversibility must not throw. check_scenes.py rejects one in CI, so
  // this should be unreachable -- but an unguarded lookup here took down the
  // whole studio tab rather than degrading, and it only fired when two
  // decisions shared a version, because that is the only time the tie-break
  // clause evaluates. A latent crash that hides behind a `||` is worse than a
  // loud one.
  const weight = d => REVERSIBILITY[d.reversibility]?.weight ?? -1
  return [...(decisions ?? [])].sort(
    (a, b) => a.v - b.v || weight(b) - weight(a),
  )
}

/**
 * Assign every decision to exactly one brief.
 *
 * Decisions belong to VERSIONS; briefs cover TRANSITIONS between versions. The
 * two do not line up, and the gaps are not edge cases -- they are most of the
 * scene:
 *
 *   - The URL shortener's code-length decision is V1, and no brief has V1 as a
 *     destination because V1 is where the scene starts.
 *   - Social feed V5 and V6 add no new components, so `buildBriefs` skips them
 *     entirely -- but V6 is where the fan-out threshold is chosen.
 *   - Payment V8 is a design review that adds nothing, and it is where the
 *     capture timeout is decided.
 *
 * Matching on version ranges stranded three of twenty-four decisions: authored,
 * shape-validated, and displayed to nobody. So the rule is positional rather
 * than arithmetic -- each decision goes to the earliest brief that has already
 * reached its version, and anything past the last brief goes to the last brief.
 * Every decision lands somewhere, exactly once, by construction.
 *
 * @returns {Array<Array<object>>} parallel to `briefs`
 */
export function assignDecisions(decisions, briefs) {
  const out = briefs.map(() => [])
  if (!briefs.length) return out

  for (const d of buildDecisions(decisions)) {
    let idx = briefs.findIndex(b => b.toV >= d.v)
    if (idx === -1) idx = briefs.length - 1
    out[idx].push(d)
  }
  return out
}

/**
 * Grade one choice.
 *
 * Returns the reader's own option so the UI can explain the specific thing they
 * picked, and the correct one so it can say what to have done instead. A
 * `defensible` pick is not scored as success -- it is scored as a real answer
 * that costs something, and the explanation says what.
 */
export function gradeDecision(decision, value) {
  const picked = decision.options.find(o => o.value === value) ?? null
  const answer = decision.options.find(o => o.verdict === 'correct') ?? null
  return {
    picked,
    answer,
    verdict: picked?.verdict ?? null,
    // Only `correct` counts as correct for retention purposes. Defensible
    // answers are worth revisiting precisely because they are nearly right.
    correct: picked?.verdict === 'correct',
  }
}

/** Headline and sub-line for a graded decision. */
export function verdictText(verdict) {
  switch (verdict) {
    case 'correct':
      return ['Right.', 'And for the reason that matters, not by elimination.']
    case 'defensible':
      return ['Defensible — but not what this system needed.',
        'A competent engineer could argue for this. Here is what it would have cost you.']
    case 'wrong':
      return ['No.', 'This is the choice that produces the incident.']
    default:
      return ['', '']
  }
}
