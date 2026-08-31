import { useEffect, useMemo, useRef, useState } from 'react'
import { Bench as Sim, theory, verdict } from '../lib/queueing.js'

/**
 * The capacity bench.
 *
 * Every other tab teaches architecture as a shape. This one teaches the number
 * that ruins capacity plans, and it is not a shape: response time does not rise
 * linearly with load, it rises as 1/(1-rho) and goes vertical while the servers
 * still look half idle on a dashboard.
 *
 * Being told that is forgettable. Dragging the arrival rate and watching the
 * marker climb the wall is not, which is the entire reason this is interactive
 * rather than a paragraph with a diagram.
 *
 * Nothing here is drawn from the formula it is demonstrating. Jobs arrive by a
 * Poisson process, queue, and are served with exponential service times; the
 * theory line is computed separately and drawn on top. `check-queueing.mjs`
 * asserts the two agree, so the curve is evidence rather than decoration.
 */

const DT = 4                 // simulated ms per step
const STEPS_PER_FRAME = 4    // ~16 sim-ms per animation frame

function cssVar(el, name, fallback) {
  const v = getComputedStyle(el).getPropertyValue(name).trim()
  return v || fallback
}

export default function Bench() {
  const [lambda, setLambda] = useState(7)      // arrivals / second
  const [serviceMs, setServiceMs] = useState(100)
  const [servers, setServers] = useState(1)
  const [mode, setMode] = useState('shared')
  const [running, setRunning] = useState(true)
  const [stats, setStats] = useState({ depth: 0, busy: 0, completed: 0, mean: 0, p50: 0, p99: 0 })

  const reduced = useMemo(
    () => typeof matchMedia === 'function'
      && matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  )

  const t = useMemo(() => theory(lambda, serviceMs, servers), [lambda, serviceMs, servers])
  const v = useMemo(() => verdict(t.rho), [t.rho])

  const sim = useRef(null)
  const hist = useRef([])
  const raf = useRef(0)
  const depthCanvas = useRef(null)
  const curveCanvas = useRef(null)

  // Any parameter change invalidates the run: measurements from the old
  // configuration would otherwise be averaged into the new one and the readout
  // would lag the slider by thousands of samples.
  useEffect(() => {
    sim.current = new Sim({ servers, serviceMs, mode, seed: 7 })
    hist.current = []
    setStats(sim.current.stats())

    // Under reduced motion there is no animation to watch, so the bench runs to
    // a steady state immediately and presents the finished result. The feature
    // still works; it just stops moving.
    if (reduced) {
      for (let i = 0; i < 30_000; i++) sim.current.step(DT, lambda)
      hist.current = Array.from({ length: 240 }, () => sim.current.depth)
      setStats(sim.current.stats())
    }
  }, [lambda, serviceMs, servers, mode, reduced])

  useEffect(() => {
    if (!running || reduced) return undefined
    const tick = () => {
      const s = sim.current
      for (let i = 0; i < STEPS_PER_FRAME; i++) s.step(DT, lambda)
      hist.current.push(s.depth)
      if (hist.current.length > 240) hist.current.shift()
      setStats(s.stats())
      raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [running, lambda, reduced])

  // --- queue depth over time ------------------------------------------------
  useEffect(() => {
    const c = depthCanvas.current
    if (!c) return
    const ctx = c.getContext('2d')
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    const w = c.clientWidth
    const h = c.clientHeight
    if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, h)

    const ink3 = cssVar(c, '--ink3', '#888')
    const accent = cssVar(c, '--accent', '#4ade80')
    const red = cssVar(c, '--red', '#f87171')
    const line = cssVar(c, '--line', '#333')

    const data = hist.current
    const peak = Math.max(8, ...data)

    ctx.strokeStyle = line
    ctx.lineWidth = 1
    for (let g = 1; g < 4; g++) {
      const y = (h / 4) * g
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke()
    }

    if (data.length > 1) {
      const step = w / 240
      ctx.beginPath()
      ctx.moveTo(0, h)
      data.forEach((d, i) => ctx.lineTo(i * step, h - (d / peak) * (h - 4)))
      ctx.lineTo((data.length - 1) * step, h)
      ctx.closePath()
      ctx.fillStyle = t.rho >= 0.9 ? `${red}22` : `${accent}22`
      ctx.fill()

      ctx.beginPath()
      data.forEach((d, i) => {
        const y = h - (d / peak) * (h - 4)
        if (i === 0) ctx.moveTo(0, y); else ctx.lineTo(i * step, y)
      })
      ctx.strokeStyle = t.rho >= 0.9 ? red : accent
      ctx.lineWidth = 1.5
      ctx.stroke()
    }

    ctx.fillStyle = ink3
    ctx.font = '10px ui-monospace, monospace'
    ctx.fillText(`peak depth ${Math.round(peak)}`, 6, 12)
  }, [stats, t.rho])

  // --- the wall: sojourn time against utilisation ---------------------------
  useEffect(() => {
    const c = curveCanvas.current
    if (!c) return
    const ctx = c.getContext('2d')
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    const w = c.clientWidth
    const h = c.clientHeight
    if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, w, h)

    const ink3 = cssVar(c, '--ink3', '#888')
    const accent = cssVar(c, '--accent', '#4ade80')
    const red = cssVar(c, '--red', '#f87171')
    const line = cssVar(c, '--line', '#333')
    const CAP = 12                       // y axis: multiples of service time

    ctx.strokeStyle = line
    ctx.lineWidth = 1
    for (const m of [2, 5, 10]) {
      const y = h - (m / CAP) * h
      ctx.beginPath(); ctx.moveTo(28, y); ctx.lineTo(w, y); ctx.stroke()
      ctx.fillStyle = ink3
      ctx.font = '10px ui-monospace, monospace'
      ctx.fillText(`${m}x`, 4, y + 3)
    }

    // 1/(1-rho): the whole lesson in one line.
    ctx.beginPath()
    for (let px = 28; px <= w; px++) {
      const rho = (px - 28) / (w - 28) * 0.98
      const mult = Math.min(CAP, 1 / (1 - rho))
      const y = h - (mult / CAP) * h
      if (px === 28) ctx.moveTo(px, y); else ctx.lineTo(px, y)
    }
    ctx.strokeStyle = ink3
    ctx.lineWidth = 1.5
    ctx.stroke()

    // Where this configuration sits on it.
    if (t.rho < 1) {
      const x = 28 + (t.rho / 0.98) * (w - 28)
      const mult = Math.min(CAP, t.sojournMs / serviceMs)
      const y = h - (mult / CAP) * h
      ctx.strokeStyle = t.rho >= 0.9 ? red : accent
      ctx.lineWidth = 1
      ctx.setLineDash([2, 3])
      ctx.beginPath(); ctx.moveTo(x, h); ctx.lineTo(x, y); ctx.stroke()
      ctx.setLineDash([])
      ctx.beginPath()
      ctx.arc(x, y, 4, 0, Math.PI * 2)
      ctx.fillStyle = t.rho >= 0.9 ? red : accent
      ctx.fill()
    }

    ctx.fillStyle = ink3
    ctx.font = '10px ui-monospace, monospace'
    ctx.fillText('0%', 28, h - 3)
    ctx.fillText('100%', w - 26, h - 3)
  }, [t.rho, t.sojournMs, serviceMs])

  const capacity = (1000 / serviceMs) * servers
  const fmt = ms => (ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`)

  return (
    <div className="bench">
      <div className="bn-head">
        <div>
          <span className="iv-h">Capacity bench</span>
          <h2 className="bn-title">Why p99 collapses before you run out of servers</h2>
        </div>
        {!reduced && (
          <button className="play" onClick={() => setRunning(r => !r)}>
            {running ? '❚❚  Pause' : '▶  Run'}
          </button>
        )}
      </div>

      <p className="bn-lede">
        A queue is not a buffer that smooths things out — it is the mechanism by which a system
        that is <em>only</em> 80% busy delivers a p99 five times its p50. Drag the arrival rate
        and watch where the wall is. It is not at 100%.
      </p>

      <div className="bn-grid">
        <div className="bn-controls">
          <label className="bn-ctl">
            <span>Arrival rate <strong>{lambda}/s</strong></span>
            <input
              type="range" min={1} max={40} step={1}
              value={lambda} onChange={e => setLambda(Number(e.target.value))}
            />
          </label>
          <label className="bn-ctl">
            <span>Service time <strong>{serviceMs} ms</strong></span>
            <input
              type="range" min={20} max={300} step={10}
              value={serviceMs} onChange={e => setServiceMs(Number(e.target.value))}
            />
          </label>
          <label className="bn-ctl">
            <span>Servers <strong>{servers}</strong></span>
            <input
              type="range" min={1} max={6} step={1}
              value={servers} onChange={e => setServers(Number(e.target.value))}
            />
          </label>

          <div className="bn-mode">
            <span className="iv-h">Queue shape</span>
            <div className="speeds">
              <button
                className={mode === 'shared' ? 'tick on' : 'tick'}
                onClick={() => setMode('shared')}
                title="One queue, any free server takes the next job"
              >One shared queue</button>
              <button
                className={mode === 'split' ? 'tick on' : 'tick'}
                onClick={() => setMode('split')}
                disabled={servers < 2}
                title="Each server has its own queue, jobs assigned on arrival"
              >{servers < 2 ? 'Split (needs 2+)' : 'One queue each'}</button>
            </div>
          </div>

          <dl className="bn-readout">
            <div><dt>Utilisation</dt><dd className={v.level}>{(t.rho * 100).toFixed(0)}%</dd></div>
            <div><dt>Capacity</dt><dd>{capacity.toFixed(1)}/s</dd></div>
            <div><dt>In queue</dt><dd>{stats.depth}</dd></div>
            <div><dt>Busy</dt><dd>{stats.busy}/{servers}</dd></div>
          </dl>
        </div>

        <div className="bn-charts">
          <div className="bn-chart">
            <span className="iv-h">Queue depth over time</span>
            <canvas ref={depthCanvas} className="bn-canvas depth" />
          </div>
          <div className="bn-chart">
            <span className="iv-h">Response time ÷ service time, against utilisation</span>
            <canvas ref={curveCanvas} className="bn-canvas curve" />
          </div>
        </div>
      </div>

      <div className={`bn-verdict ${v.level}`}>
        <strong>{v.title}</strong>
        <p>{v.text}</p>
      </div>

      <div className="bn-measured">
        <span className="iv-h">Measured, from {stats.completed.toLocaleString()} completed requests</span>
        <table className="bn-table">
          <thead>
            <tr><th /><th>Simulated</th><th>Theory</th></tr>
          </thead>
          <tbody>
            <tr>
              <th>mean</th>
              <td>{fmt(stats.mean)}</td>
              <td>{t.saturated ? '∞' : fmt(t.sojournMs)}</td>
            </tr>
            <tr>
              <th>p50</th>
              <td>{fmt(stats.p50)}</td>
              <td className="dim">—</td>
            </tr>
            <tr>
              <th>p99</th>
              <td className={t.rho >= 0.9 ? 'hot' : ''}>{fmt(stats.p99)}</td>
              <td>{t.p99Ms ? fmt(t.p99Ms) : <span className="dim">—</span>}</td>
            </tr>
          </tbody>
        </table>
        <p className="hint">
          {servers === 1
            ? 'Theory here is the exact M/M/1 result: mean 1/(μ−λ), and p99 = ln(100)/(μ−λ).'
            : `Theory here is Erlang C for ${servers} servers. There is no equally tidy closed `
              + 'form for the p99 of a multi-server queue, so none is claimed — that cell is '
              + 'the measurement alone.'}
        </p>
      </div>

      {mode === 'split' && servers > 1 && (
        <div className="bn-note">
          <span className="iv-h">The same servers, arranged badly</span>
          <p>
            Identical capacity and identical utilisation — every job is simply assigned a queue on
            arrival instead of taking the next free server. It is measurably worse, because a job
            can wait behind a long one while another server sits idle with work it is not allowed
            to take.
          </p>
          <p>
            That gap is the argument for a shared work queue, and it is the same reason a hash
            shard with one hot key hurts far more than its average load suggests. <strong>Splitting
            a queue costs you capacity you have already paid for.</strong>
          </p>
        </div>
      )}

      <p className="simnote">
        Poisson arrivals, exponential service, discrete-event — nothing on this page is drawn from
        the formula it demonstrates. The theory column is computed by separate code and
        <strong> npm run check:queueing</strong> asserts the two agree, including that splitting the
        queue really is worse. A simulation nobody checks draws a confident, smooth, wrong curve.
      </p>
    </div>
  )
}
