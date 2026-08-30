import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import Canvas from './components/Canvas.jsx'
const Patterns = lazy(() => import('./components/Patterns.jsx'))
const Interview = lazy(() => import('./components/Interview.jsx'))
const Predict = lazy(() => import('./components/Predict.jsx'))
import StarButton from './components/StarButton.jsx'
import ThemeToggle from './components/ThemeToggle.jsx'
import { SCENES } from './scenes/index.js'
import { activeEdges, flowAvailable, layout } from './lib/layout.js'
import { buildTimeline, sampleTimeline } from './lib/timeline.js'

// How many simulated milliseconds pass per real second. A database query
// genuinely takes ~30ms, which is too fast to watch, so time is stretched.
const SPEEDS = [
  { label: '0.1×', factor: 12 },
  { label: '0.25×', factor: 30 },
  { label: '0.5×', factor: 60 },
  { label: '1×', factor: 120 },
  { label: '4×', factor: 480 },
]

export default function App() {
  const [sceneId, setSceneId] = useState(SCENES[0].id)
  const [vIndex, setVIndex] = useState(0)
  const [flowId, setFlowId] = useState(null)
  const [playing, setPlaying] = useState(false)
  const [speedIdx, setSpeedIdx] = useState(3)
  const [view, setView] = useState('architecture')
  const [down, setDown] = useState(() => new Set())
  const [simMs, setSimMs] = useState(0)

  const scene = useMemo(() => SCENES.find(s => s.id === sceneId) ?? SCENES[0], [sceneId])
  const version = scene.versions[Math.min(vIndex, scene.versions.length - 1)]

  const { positions, width, height } = useMemo(() => layout(version), [version])
  const edges = useMemo(() => activeEdges(version), [version])

  const flows = useMemo(
    () => scene.flows.filter(f => flowAvailable(f, version)),
    [scene, version],
  )

  useEffect(() => {
    if (!flows.length) { setFlowId(null); return }
    if (!flows.some(f => f.id === flowId)) setFlowId(flows[0].id)
  }, [flows, flowId])

  useEffect(() => { setDown(new Set()) }, [sceneId])

  const flow = flows.find(f => f.id === flowId) ?? null

  const timeline = useMemo(
    () => (flow ? buildTimeline(scene, flow, down) : null),
    [scene, flow, down],
  )

  // Advance simulated time, not pixels. The packet dwells inside components for
  // as long as that component costs, so a database visit visibly takes ~30x a
  // cache lookup instead of both being a dot moving at the same speed.
  const raf = useRef(0)
  const last = useRef(0)
  useEffect(() => {
    if (!playing || !timeline || timeline.totalMs === 0) return undefined
    last.current = performance.now()
    const tick = now => {
      const dt = (now - last.current) / 1000
      last.current = now
      setSimMs(t => {
        const next = t + dt * SPEEDS[speedIdx].factor
        // A blocked request does not loop -- it stays failed until you fix it.
        if (next >= timeline.totalMs) {
          return timeline.blockedAt !== null ? timeline.totalMs : 0
        }
        return next
      })
      raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [playing, timeline, speedIdx])

  useEffect(() => { setSimMs(0) }, [flowId, vIndex, sceneId, down])

  const sample = timeline ? sampleTimeline(timeline, positions, simMs) : null
  const showPacket = !!sample && (playing || simMs > 0)

  const failures = scene.failures.filter(
    f => version.active.includes(f.node) && (!f.minVersion || version.v >= f.minVersion),
  )
  const triggered = failures.filter(f => down.has(f.node))
  const bottleneck = triggered.find(f => f.bottleneck)?.bottleneck ?? version.bottleneck
  const outage = triggered.some(f => !f.survivable)

  const toggle = id => setDown(prev => {
    const next = new Set(prev)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  // Advance to the start of the next segment. Stepping hop-by-hop is the only
  // way to actually inspect a 1ms cache lookup, however slow the playback is.
  const step = () => {
    if (!timeline) return
    setPlaying(false)
    const next = timeline.steps.find(s => s.startMs > simMs + 0.01)
    setSimMs(next ? next.startMs : 0)
  }

  const replay = ({ version: v, flowId: fid, down: node }) => {
    const idx = scene.versions.findIndex(x => x.v === v)
    if (idx >= 0) setVIndex(idx)
    setFlowId(fid)
    setDown(new Set([node]))
    setSimMs(0)
    setPlaying(true)
    setView('architecture')
  }

  const blocked = timeline?.blockedAt !== null && timeline?.blockedNode
  const reachedBlock = blocked && simMs >= timeline.totalMs - 1

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="dot" aria-hidden="true" />
          <h1>System Design Lab</h1>
        </div>
        <nav className="viewnav">
          <button
            className={view === 'architecture' ? 'tick on' : 'tick'}
            onClick={() => setView('architecture')}
          >Architectures</button>
          <button
            className={view === 'predict' ? 'tick on' : 'tick'}
            onClick={() => setView('predict')}
          >Predict</button>
          <button
            className={view === 'patterns' ? 'tick on' : 'tick'}
            onClick={() => setView('patterns')}
          >Patterns</button>
          <button
            className={view === 'interview' ? 'tick on' : 'tick'}
            onClick={() => setView('interview')}
          >Interview</button>
        </nav>
        <div className="topright">
          {(view === 'architecture' || view === 'predict') && (
            <label className="scene-pick">
              <span>System</span>
              <select value={sceneId} onChange={e => setSceneId(e.target.value)}>
                {SCENES.map(s => <option key={s.id} value={s.id}>{s.title}</option>)}
              </select>
            </label>
          )}
          <ThemeToggle />
          <StarButton />
        </div>
      </header>

      {view === 'patterns' && (
        <Suspense fallback={<p className="hint" style={{ marginTop: 24 }}>Loading…</p>}>
          <Patterns />
        </Suspense>
      )}

      {view === 'interview' && (
        <Suspense fallback={<p className="hint" style={{ marginTop: 24 }}>Loading…</p>}>
          <Interview />
        </Suspense>
      )}

      {view === 'predict' && (
        <Suspense fallback={<p className="hint" style={{ marginTop: 24 }}>Loading…</p>}>
          <Predict scene={scene} onReplay={replay} />
        </Suspense>
      )}

      {view === 'architecture' && <>
      <p className="summary"><strong>{scene.title}.</strong> {scene.summary}</p>

      <section className="stage">
        <div className="stage-head">
          <div className="vwhy">
            <span className="vtag">V{version.v}</span>
            <strong>{version.label}</strong>
            <p className="trigger">{version.trigger}</p>
          </div>
          <div className="readout">
            <div className={`lat ${sample?.failed ? 'failed' : ''}`}>
              <em>elapsed</em>
              <strong>{sample ? Math.round(sample.elapsedMs) : 0}<span>ms</span></strong>
            </div>
            <div className="metrics">
              <span><em>p50</em> {version.metrics.p50_ms} ms</span>
              <span><em>p99</em> {version.metrics.p99_ms} ms</span>
              <span><em>load</em> {version.traffic.label}</span>
            </div>
          </div>
        </div>

        {outage && (
          <div className="banner outage">
            Total outage — no request completes. A component whose loss stops the system is never
            &ldquo;safe to lose&rdquo;, whatever the diagram says.
          </div>
        )}
        {reachedBlock && !outage && (
          <div className="banner outage">
            Request failed at <strong>{scene.nodes[timeline.blockedNode]?.label}</strong> — it is
            down, so nothing downstream of it is reached.
          </div>
        )}

        <div className="canvas-scroll">
        <Canvas
          scene={scene}
          version={version}
          positions={positions}
          width={width}
          height={height}
          edges={edges}
          packet={showPacket ? sample : null}
          activeNode={showPacket ? sample.activeNode : null}
          activeHopEdge={showPacket ? sample.edge : null}
          downNodes={down}
          bottleneck={bottleneck}
        />
        </div>

        <p className="simnote">
          Timings are illustrative orders of magnitude, stretched so they are watchable — the point
          is the <em>ratio</em> between a cache lookup and a database round trip, not the numbers.
        </p>
      </section>

      {version.note && <p className="note">{version.note}</p>}

      <section className="controls">
        <div className="ctl">
          <h3>Evolution</h3>
          <input
            type="range"
            min={0}
            max={scene.versions.length - 1}
            value={vIndex}
            onChange={e => setVIndex(Number(e.target.value))}
            aria-label="Architecture version"
          />
          <div className="ticks">
            {scene.versions.map((v, i) => (
              <button
                key={v.v}
                className={i === vIndex ? 'tick on' : 'tick'}
                onClick={() => setVIndex(i)}
                title={v.label}
              >
                V{v.v}
              </button>
            ))}
          </div>
          <p className="hint">Drag to grow the system. Every step has a reason, shown above.</p>
        </div>

        <div className="ctl">
          <h3>Request flow</h3>
          <div className="row">
            <button className="play" onClick={() => setPlaying(p => !p)} disabled={!flow}>
              {playing ? '❚❚  Pause' : '▶  Play'}
            </button>
            <select value={flowId ?? ''} onChange={e => setFlowId(e.target.value)} disabled={!flows.length}>
              {flows.map(f => <option key={f.id} value={f.id}>{f.label}</option>)}
            </select>
          </div>
          <div className="speeds">
            {SPEEDS.map((s, i) => (
              <button
                key={s.label}
                className={i === speedIdx ? 'tick on' : 'tick'}
                onClick={() => setSpeedIdx(i)}
              >
                {s.label}
              </button>
            ))}
            <button className="tick" onClick={step} disabled={!timeline}>Step ›</button>
            {timeline && (
              <span className="total">total {Math.round(timeline.totalMs)} ms</span>
            )}
          </div>
          {timeline && (
            <input
              type="range"
              min={0}
              max={Math.max(1, Math.round(timeline.totalMs))}
              value={Math.round(simMs)}
              onChange={e => { setPlaying(false); setSimMs(Number(e.target.value)) }}
              aria-label="Scrub through the request"
              className="scrub"
            />
          )}
          {flow && <p className="hint">{flow.outcome}</p>}
          {!flows.length && <p className="hint">No flow defined at this version.</p>}
        </div>

        <div className="ctl">
          <h3>Switch a component off</h3>
          <div className="toggles">
            {failures.length === 0 && <p className="hint">Nothing toggleable at this version.</p>}
            {failures.map(f => (
              <label key={f.id} className={down.has(f.node) ? 'tog on' : 'tog'}>
                <input type="checkbox" checked={down.has(f.node)} onChange={() => toggle(f.node)} />
                <span>{scene.nodes[f.node]?.label ?? f.node}</span>
              </label>
            ))}
          </div>
          {triggered.map(f => (
            <p key={f.id} className={f.survivable ? 'effect' : 'effect fatal'}>
              <strong>{f.survivable ? 'Degraded' : 'Outage'}</strong> — {f.effect}
            </p>
          ))}
        </div>
      </section>
      </>}

      <footer>
        {view === 'architecture' && (
          <p>
            Shapes follow the notation contract — <strong>dashed means safe to lose</strong>, a
            cylinder means losing it costs data. Timings are illustrative orders of magnitude.
          </p>
        )}
        {view === 'predict' && (
          <p>
            Every question and answer is derived from the scene file — the same data that draws the
            diagram, so the quiz cannot disagree with what you are about to watch.
          </p>
        )}
        {view === 'interview' && (
          <p>
            The follow-ups are the point — anyone can recite a first answer. Generated from the same
            data as the repository&rsquo;s question bank, so the two cannot drift.
          </p>
        )}
        {view === 'patterns' && (
          <p>
            Generated from the same tables that produce the repository&rsquo;s pattern catalogue, so
            a pattern cannot say one thing on the page and another here.
          </p>
        )}
      </footer>
    </div>
  )
}
