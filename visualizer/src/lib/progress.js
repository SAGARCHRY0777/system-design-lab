/**
 * Remember what you got wrong.
 *
 * There are hundreds of questions here and, until now, nothing remembered a
 * single answer. That is the difference between a quiz and practice: you cannot
 * return to your weak areas if nothing knows what they are, and the questions
 * you got right are exactly the ones not worth repeating.
 *
 * Deliberately NOT a score. The user chose commit-then-reveal without points,
 * and that decision holds -- this records misses so they can be revisited, not
 * a total to optimise. There is no streak, no percentage and no leaderboard,
 * because those change what a reader is trying to do.
 *
 * Per browser, per device, never sent anywhere. localStorage can throw outright
 * in a private window or with site data blocked, so every access is guarded and
 * an unusable store simply means the feature is absent rather than broken.
 */

const KEY = 'sdl-progress'
const MAX = 500   // a bound, so a long session cannot grow this without limit

function read() {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { missed: {}, seen: {} }
    const v = JSON.parse(raw)
    return {
      missed: v?.missed && typeof v.missed === 'object' ? v.missed : {},
      seen: v?.seen && typeof v.seen === 'object' ? v.seen : {},
    }
  } catch {
    return { missed: {}, seen: {} }
  }
}

function write(state) {
  try {
    // Trim oldest-first if the store has grown past the bound.
    const ids = Object.keys(state.seen)
    if (ids.length > MAX) {
      const drop = ids.slice(0, ids.length - MAX)
      for (const id of drop) { delete state.seen[id]; delete state.missed[id] }
    }
    localStorage.setItem(KEY, JSON.stringify(state))
  } catch {
    // A reader who cannot persist still gets every question.
  }
}

/**
 * Record an attempt.
 *
 * @param {string} area  'predict' | 'studio' | 'interview'
 * @param {string} id    stable question or brief id
 * @param {boolean} ok   whether they got it right
 */
export function record(area, id, ok) {
  const key = `${area}:${id}`
  const s = read()
  s.seen[key] = (s.seen[key] ?? 0) + 1
  if (ok) delete s.missed[key]        // getting it right retires it
  else s.missed[key] = (s.missed[key] ?? 0) + 1
  write(s)
}

/** Ids missed at least once and not since corrected, for one area. */
export function missedIn(area) {
  const s = read()
  const prefix = `${area}:`
  return Object.keys(s.missed)
    .filter(k => k.startsWith(prefix))
    .map(k => k.slice(prefix.length))
}

/** Counts for the header: how much has been attempted, how much is outstanding. */
export function summary() {
  const s = read()
  const seen = Object.keys(s.seen).length
  const missed = Object.keys(s.missed).length
  return { seen, missed }
}

export function reset() {
  try {
    localStorage.removeItem(KEY)
  } catch {
    /* nothing to clear that we can reach */
  }
}
