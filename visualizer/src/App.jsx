import { useEffect, useMemo, useRef, useState } from 'react'
import Canvas from './components/Canvas.jsx'
import { SCENES } from './scenes/index.js'
import { activeEdges, flowAvailable, flowGeometry, layout, pointAt } from './lib/layout.js'

const SPEED_PX_PER_S = 260

export default function App() {
  const [sceneId, setSceneId] = useState(SCENES[0].id)
  const [vIndex, setVIndex] = useState(0)
  const [flowId, setFlowId] = useState(null)
  const [playing, setPlaying] = useState(false)
  const [down, setDown] = useState(() => new Set())
  const [dist, setDist] = useState(0)

  const scene = useMemo(() => SCENES.find(s => s.id === sceneId) ?? SCENES[0], [sceneId])
  const version = scene.versions[Math.min(vIndex, scene.versions.length - 1)]

  const { positions, width, height } = useMemo(() => layout(version), [version])
  const edges = useMemo(() => activeEdges(version), [version])

  const flows = useMemo(
    () => scene.flows.filter(f => flowAvailable(f, version)),
    [scene, version],
  )

  // Changing scene or version can invalidate the selection: a flow that needed
  // the cache is meaningless at V1. Fall back to the first available one rather
  // than silently animating nothing.
  useEffect(() => {
    if (!flows.length) { setFlowId(null); return }
    if (!flows.some(f => f.id === flowId)) setFlowId(flows[0].id)
  }, [flows, flowId])

  useEffect(() => { setDown(new Set()) }, [sceneId])

  const flow = flows.find(f => f.id === flowId) ?? null
  const geo = useMemo(
    () => (flow ? flowGeometry(flow.path, positions) : null),
    [flow, positions],
  )

  // Animation loop. Distance-based rather than time-per-hop, so a long hop
  // visibly takes longer than a short one — the picture should not imply that
  // crossing an ocean costs the same as a call within a rack.
  const raf = useRef(0)
  const last = useRef(0)
  useEffect(() => {
    if (!playing || !geo || geo.total === 0) return undefined
    last.current = performance.now()
    const tick = now => {
      const dt = (now - last.current) / 1000
      last.current = now
      setDist(d => {
        const next = d + dt * SPEED_PX_PER_S
        return next >= geo.total ? 0 : next
      })
      raf.current = requestAnimationFrame(tick)
    }
    raf.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf.current)
  }, [playing, geo])

  useEffect(() => { setDist(0) }, [flowId, vIndex, sceneId])

  const packet = geo && geo.total > 0 ? pointAt(geo, dist) : null
  const activeHopEdge = useMemo(() => {
    if (!flow || !packet) return null
    return { from: flow.path[packet.hop], to: flow.path[packet.hop + 1] }
  }, [flow, packet])

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

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="dot" aria-hidden="true" />
          <h1>System Design Lab</h1>
        </div>
        <label className="scene-pick">
          <span>System</span>
          <select value={sceneId} onChange={e => setSceneId(e.target.value)}>
            {SCENES.map(s => <option key={s.id} value={s.id}>{s.title}</option>)}
          </select>
        </label>
      </header>

      <p className="summary">{scene.summary}</p>

      <section className="stage">
        <div className="stage-head">
          <div>
            <span className="vtag">V{version.v}</span>
            <strong>{version.label}</strong>
          </div>
          <div className="metrics">
            <span><em>p50</em> {version.metrics.p50_ms} ms</span>
            <span><em>p99</em> {version.metrics.p99_ms} ms</span>
            <span><em>load</em> {version.traffic.label}</span>
          </div>
        </div>

        {outage && (
          <div className="banner outage">
            Total outage — no request completes. A component whose loss stops the system is never
            &ldquo;safe to lose&rdquo;, whatever the diagram says.
          </div>
        )}

        <Canvas
          scene={scene}
          version={version}
          positions={positions}
          width={width}
          height={height}
          edges={edges}
          packet={playing || dist > 0 ? packet : null}
          activeHopEdge={activeHopEdge}
          downNodes={down}
          bottleneck={bottleneck}
        />
      </section>

      <section className="why">
        <h2>Why this version exists</h2>
        <p className="trigger">{version.trigger}</p>
        {version.note && <p className="note">{version.note}</p>}
      </section>

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

      <footer>
        <p>
          Shapes follow the notation contract — dashed means safe to lose, a cylinder means losing it
          costs data. Every architecture here is authored once as a scene file and drives both this
          app and the diagrams committed in the repository.
        </p>
      </footer>
    </div>
  )
}
