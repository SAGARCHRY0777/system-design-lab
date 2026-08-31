/**
 * Verify the capacity bench against closed-form queueing theory.
 *
 * The bench makes a strong claim -- that a system at 90% utilisation waits
 * roughly nine times its service time -- and a reader has no way to audit a
 * simulation by looking at it. If the simulator drifted, it would go on drawing
 * a confident, smooth, wrong curve, and the lesson would be false in exactly
 * the direction that feels plausible.
 *
 * So the simulation and the formula are computed by separate code paths and
 * checked against each other here. The simulator never consults `theory()`.
 *
 *     npm run check:queueing
 */

import { Bench, erlangC, theory, verdict } from '../src/lib/queueing.js'

let fail = 0
const bad = m => { console.log('  FAIL ' + m); fail++ }
const ok = m => console.log('  ok   ' + m)

/** Run to completion and return measured mean sojourn time. */
function run(lambda, serviceMs, servers, mode, ms = 900_000, seed = 7) {
  const b = new Bench({ servers, serviceMs, mode, seed, keep: 20_000 })
  const dt = 1
  for (let t = 0; t < ms; t += dt) b.step(dt, lambda)
  return b
}

const near = (a, b, tol) => Math.abs(a - b) / b <= tol

// --- Erlang C against values that are known analytically -------------------
// For a single server the probability of waiting is exactly the utilisation.
for (const a of [0.1, 0.5, 0.8, 0.95]) {
  const got = erlangC(1, a)
  if (!near(got, a, 1e-9)) bad(`erlangC(1, ${a}) = ${got}, expected ${a}`)
}
ok('erlangC(1, a) === a, the known M/M/1 result')

// It must not overflow. a^c/c! goes to Infinity around c=40 if computed
// directly, and NaN in a capacity tool is worse than an error.
for (const c of [10, 40, 120, 500]) {
  const got = erlangC(c, c * 0.85)
  if (!Number.isFinite(got) || got < 0 || got > 1) {
    bad(`erlangC(${c}, ...) = ${got} -- not a probability`)
  }
}
ok('erlangC stays a finite probability up to c=500 (no factorial overflow)')

// Saturation must be reported, not divided by zero into Infinity silently.
if (theory(10, 100, 1).saturated !== true) bad('rho = 1 not reported as saturated')
if (theory(20, 100, 1).saturated !== true) bad('rho > 1 not reported as saturated')
ok('saturation is reported rather than returning a number')

// --- the simulator must converge on the formula ----------------------------
// M/M/1 sojourn time is exactly 1/(mu - lambda).
console.log('\n  M/M/1 — simulated mean vs 1/(mu-lambda):')
for (const [lambda, serviceMs] of [[2, 100], [5, 100], [8, 100], [4, 50]]) {
  const t = theory(lambda, serviceMs, 1)
  const b = run(lambda, serviceMs, 1, 'shared')
  const got = b.meanLatency
  const pass = near(got, t.sojournMs, 0.08)
  console.log(`    lambda=${lambda}/s svc=${serviceMs}ms  rho=${t.rho.toFixed(2)}  `
    + `sim ${got.toFixed(1)}ms  theory ${t.sojournMs.toFixed(1)}ms  `
    + `${pass ? 'agree' : 'DIVERGE'}   (n=${b.completed})`)
  if (!pass) bad(`M/M/1 lambda=${lambda} svc=${serviceMs}: sim and theory disagree`)
}

// M/M/c via Erlang C -- the multi-server case the bench actually defaults to.
console.log('\n  M/M/c — simulated mean vs Erlang C:')
for (const [lambda, serviceMs, c] of [[15, 100, 2], [25, 100, 3], [34, 100, 4]]) {
  const t = theory(lambda, serviceMs, c)
  const b = run(lambda, serviceMs, c, 'shared')
  const got = b.meanLatency
  const pass = near(got, t.sojournMs, 0.10)
  console.log(`    lambda=${lambda}/s c=${c}  rho=${t.rho.toFixed(2)}  `
    + `sim ${got.toFixed(1)}ms  theory ${t.sojournMs.toFixed(1)}ms  `
    + `${pass ? 'agree' : 'DIVERGE'}   (n=${b.completed})`)
  if (!pass) bad(`M/M/${c} lambda=${lambda}: sim and theory disagree`)
}

// --- the second lesson: pooling ---------------------------------------------
// Identical capacity, identical utilisation, one shared queue versus c separate
// ones. If the simulator did NOT show shared winning, the mechanic would be
// wrong -- so this asserts the teaching claim, not just the arithmetic.
console.log('\n  Pooling — one shared queue vs the same servers split up:')
for (const [lambda, c] of [[15, 2], [25, 3], [34, 4]]) {
  const shared = run(lambda, 100, c, 'shared').meanLatency
  const split = run(lambda, 100, c, 'split').meanLatency
  const better = split / shared
  console.log(`    lambda=${lambda}/s c=${c}  shared ${shared.toFixed(1)}ms  `
    + `split ${split.toFixed(1)}ms  split is ${better.toFixed(2)}x worse`)
  if (!(split > shared)) {
    bad(`c=${c}: splitting the queue did not make it worse -- the demo claims it does`)
  }
}

// --- the headline claim -----------------------------------------------------
// "50% costs 1x, 90% costs 9x, 95% costs 19x" -- the multiplier is 1/(1-rho),
// and the page states these numbers, so they are asserted here.
console.log('\n  Queueing multiplier 1/(1-rho):')
for (const [rho, expected] of [[0.5, 2], [0.8, 5], [0.9, 10], [0.95, 20]]) {
  const t = theory(rho * 10, 100, 1)   // mu = 10/s, so lambda = rho*10
  const mult = t.sojournMs / 100
  const pass = near(mult, expected, 1e-6)
  console.log(`    rho=${rho}  sojourn is ${mult.toFixed(1)}x the service time`)
  if (!pass) bad(`rho=${rho}: multiplier ${mult}, the page says ${expected}`)
}

// --- the copy must match the maths ------------------------------------------
for (const [rho, level] of [[0.3, 'ok'], [0.75, 'warn'], [0.93, 'danger'], [1.2, 'over']]) {
  if (verdict(rho).level !== level) bad(`verdict(${rho}) is ${verdict(rho).level}, expected ${level}`)
}
if (!verdict(0.9).title.includes('10x')) {
  bad(`verdict(0.9) should state the 10x multiplier, says: ${verdict(0.9).title}`)
}
ok('the verdict copy matches the multiplier it describes')

console.log(fail
  ? `\n${fail} problem(s)`
  : '\nsimulation agrees with closed-form theory in every case')
process.exit(fail ? 1 : 0)
