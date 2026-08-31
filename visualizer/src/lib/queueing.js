/**
 * The capacity bench: why latency explodes before you run out of capacity.
 *
 * Every other part of this app teaches architecture as a shape. This one
 * teaches the single most counter-intuitive number in the whole subject, and it
 * is not a shape at all:
 *
 *   A server at 50% utilisation adds 1x its service time in waiting.
 *   At 90% it adds 9x. At 95%, 19x. At 99%, 99x.
 *
 * Nothing breaks at 80%. No component is at fault. The queue is simply the
 * mechanism by which a system that is "only" 80% busy delivers a p99 five times
 * worse than its p50, and every capacity plan that reasons in averages walks
 * into it. Being told this is forgettable; dragging the slider and watching the
 * curve go vertical is not.
 *
 * Two things run side by side here, and keeping them separate is the point:
 *
 *   SIMULATION   discrete-event, Poisson arrivals, exponential service. Nothing
 *                is drawn from a formula -- jobs arrive, wait, and are served.
 *   THEORY       the closed form for the same system. Drawn as a reference line.
 *
 * If the simulation is honest the two converge, and `check-queueing.mjs`
 * asserts exactly that. A demo whose numbers come from the formula it claims to
 * be demonstrating proves nothing, which is why they are computed apart.
 */

/* ------------------------------------------------------------------ theory */

/**
 * Erlang C -- the probability an arriving job finds every server busy and has
 * to queue. This is the classic call-centre staffing formula and it is the
 * right one here: c servers drawing from ONE shared queue.
 *
 * Computed with a recurrence rather than factorials directly, because a^c/c!
 * overflows to Infinity/NaN for perfectly ordinary inputs (c=40 is enough) and
 * a capacity tool that silently returns NaN is worse than one that refuses.
 */
export function erlangC(c, a) {
  if (c <= 0) return 1
  const rho = a / c
  if (rho >= 1) return 1                    // saturated: everyone queues

  // term_k = a^k / k!, built up one multiply at a time.
  let term = 1
  let sum = 1                                // k = 0
  for (let k = 1; k < c; k++) {
    term *= a / k
    sum += term
  }
  const last = (term * a / c) / (1 - rho)   // the a^c/(c!(1-rho)) tail
  return last / (sum + last)
}

/**
 * Closed-form behaviour of an M/M/c queue.
 *
 * @param {number} lambda   arrivals per second
 * @param {number} serviceMs mean service time of ONE job, milliseconds
 * @param {number} c        number of servers sharing one queue
 */
export function theory(lambda, serviceMs, c) {
  const mu = 1000 / serviceMs               // jobs per second, one server
  const a = lambda / mu                     // offered load, erlangs
  const rho = a / c                         // utilisation per server

  if (rho >= 1) {
    return { rho, mu, saturated: true, waitMs: Infinity, sojournMs: Infinity, p99Ms: Infinity }
  }

  const pWait = erlangC(c, a)
  const waitMs = (pWait / (c * mu - lambda)) * 1000   // mean time queued
  const sojournMs = waitMs + serviceMs                // queued + being served

  // For a single server the sojourn time is exactly Exp(mu - lambda), so the
  // 99th percentile has a clean closed form. For c > 1 there is no equally
  // tidy expression, so nothing is claimed -- the bench shows the measured
  // value alone rather than inventing a reference for it.
  const p99Ms = c === 1 ? (Math.log(100) / (mu - lambda)) * 1000 : null

  return { rho, mu, saturated: false, waitMs, sojournMs, p99Ms }
}

/* -------------------------------------------------------------- simulation */

/** Deterministic PRNG (mulberry32) so a run can be reproduced and asserted. */
export function rng(seed = 1) {
  let s = seed >>> 0
  return () => {
    s = (s + 0x6D2B79F5) >>> 0
    let t = Math.imul(s ^ (s >>> 15), 1 | s)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** An exponential draw with the given mean. */
function expo(rand, mean) {
  // 1 - rand() so a returned 0 cannot produce Infinity.
  return -Math.log(1 - rand()) * mean
}

/**
 * A discrete-event queue simulator.
 *
 * `mode` is the second lesson and the more surprising one:
 *
 *   'shared'  c servers, ONE queue. A free server can take anyone's work.
 *   'split'   c independent queues, one server each, jobs assigned on arrival.
 *
 * Both have identical total capacity and identical utilisation. The split
 * version is markedly worse, because a job can be stuck behind a long one while
 * another server sits idle -- work it is not allowed to take. That gap is the
 * whole argument for a shared work queue, and it is the same reason a hash
 * shard with a hot key hurts more than its average load suggests.
 */
export class Bench {
  constructor({ servers = 1, serviceMs = 100, seed = 1, mode = 'shared', keep = 600 } = {}) {
    this.mode = mode
    this.serviceMs = serviceMs
    this.keep = keep
    this.rand = rng(seed)
    this.t = 0
    this.completed = 0
    this.sumLatency = 0            // every completion, for a true running mean
    this.latencies = []            // ring buffer of RECENT sojourn times
    this.next = 0                  // round-robin cursor for 'split'
    this.servers = Array.from({ length: servers }, () => ({ remaining: 0, arrivedAt: 0, busy: false }))
    this.queues = Array.from({ length: mode === 'split' ? servers : 1 }, () => [])
  }

  get depth() {
    return this.queues.reduce((n, q) => n + q.length, 0)
  }

  get busy() {
    return this.servers.filter(s => s.busy).length
  }

  /** Advance the simulation by `dt` milliseconds at arrival rate `lambda` /sec. */
  step(dt, lambda) {
    this.t += dt

    // --- arrivals: Poisson over the interval, by Knuth's method -------------
    const mean = lambda * (dt / 1000)
    const L = Math.exp(-mean)
    let k = 0
    let p = 1
    do { k++; p *= this.rand() } while (p > L)
    for (let i = 0; i < k - 1; i++) {
      const q = this.mode === 'split' ? this.next++ % this.queues.length : 0
      this.queues[q].push(this.t)
    }

    // --- service ------------------------------------------------------------
    for (let i = 0; i < this.servers.length; i++) {
      const s = this.servers[i]

      if (s.busy) {
        s.remaining -= dt
        if (s.remaining <= 0) {
          // Sojourn time: arrival to completion, queueing included. That is what
          // a caller experiences, and it is what the theory line predicts.
          const sojourn = this.t - s.arrivedAt
          this.completed++
          this.sumLatency += sojourn
          this.latencies.push(sojourn)
          if (this.latencies.length > this.keep) this.latencies.shift()
          s.busy = false
        }
      }

      if (!s.busy) {
        const q = this.queues[this.mode === 'split' ? i : 0]
        const arrivedAt = q.shift()
        if (arrivedAt !== undefined) {
          s.busy = true
          s.arrivedAt = arrivedAt
          s.remaining = expo(this.rand, this.serviceMs)
        }
      }
    }
  }

  /** Measured percentile of time-in-system, in ms. */
  percentile(p) {
    if (!this.latencies.length) return 0
    const sorted = [...this.latencies].sort((a, b) => a - b)
    const i = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))
    return sorted[i]
  }

  /** Mean sojourn time over every completion, not just the ring buffer. */
  get meanLatency() {
    return this.completed ? this.sumLatency / this.completed : 0
  }

  stats() {
    return {
      depth: this.depth,
      busy: this.busy,
      completed: this.completed,
      mean: this.meanLatency,
      p50: this.percentile(50),
      p99: this.percentile(99),
      samples: this.latencies.length,
    }
  }
}

/**
 * What to tell the reader at this utilisation.
 *
 * The thresholds are not arbitrary: the queueing multiplier 1/(1-rho) is 2x at
 * 50%, 5x at 80% and 20x at 95%, and those are the points where the advice
 * genuinely changes.
 */
export function verdict(rho) {
  if (rho >= 1) {
    return {
      level: 'over',
      title: 'Past capacity — the queue never drains',
      text: 'Arrivals exceed what the servers can clear, so the backlog grows without bound '
        + 'and latency rises for as long as this lasts. No timeout tuning fixes this; there '
        + 'is simply more work arriving than leaving. You add capacity or you shed load.',
    }
  }
  if (rho >= 0.9) {
    return {
      level: 'danger',
      title: `${Math.round(rho * 100)}% utilised — ${(1 / (1 - rho)).toFixed(0)}x the service time`,
      text: 'The curve is vertical here. A 5% traffic increase now costs more latency than the '
        + 'previous 50% did, so ordinary daily variance produces pages. This is the region '
        + 'where a system looks fine on a dashboard of averages and is already failing its p99.',
    }
  }
  if (rho >= 0.7) {
    return {
      level: 'warn',
      title: `${Math.round(rho * 100)}% utilised — the knee`,
      text: 'Still healthy on average, and already sensitive: waiting time is now growing '
        + 'faster than arrivals are. This is the usual place to add capacity, because the '
        + 'next increment of traffic is the expensive one.',
    }
  }
  return {
    level: 'ok',
    title: `${Math.round(rho * 100)}% utilised — headroom`,
    text: 'Queueing is a small share of response time; most requests find a free server '
      + 'immediately. Running here costs money in idle capacity, and that is what you are '
      + 'buying: absorbing a burst without the p99 moving.',
  }
}
