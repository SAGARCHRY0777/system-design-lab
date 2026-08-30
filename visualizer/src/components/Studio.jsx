import { useEffect, useMemo, useState } from 'react'
import { SCENES } from '../scenes/index.js'
import { buildBriefs, grade, whyWrong } from '../lib/studio.js'

/**
 * The design studio.
 *
 * Everything else in this app is recognition. This is production: you are given
 * the system you have, the traffic it now faces and the symptom, and you decide
 * what to add. The symptom is the requirement, not the answer -- inferring the
 * fix from it is the whole skill.
 *
 * Over-building is graded as harshly as under-building, and the feedback for a
 * wrong component says WHEN it would have been right. A catalogue of patterns
 * implicitly teaches that every pattern is desirable; this is the correction.
 */
export default function Studio() {
  const [sceneId, setSceneId] = useState(SCENES[0].id)
  const scene = useMemo(() => SCENES.find(s => s.id === sceneId) ?? SCENES[0], [sceneId])
  const briefs = useMemo(() => buildBriefs(scene), [scene])

  const [i, setI] = useState(0)
  const [picked, setPicked] = useState([])
  const [result, setResult] = useState(null)

  useEffect(() => { setI(0); setPicked([]); setResult(null) }, [sceneId])
  useEffect(() => { setPicked([]); setResult(null) }, [i])

  const b = briefs[Math.min(i, briefs.length - 1)]
  if (!b) return <div className="studio"><p className="hint">No briefs for this system.</p></div>

  const label = id => scene.nodes[id]?.label ?? id
  const toggle = id => setPicked(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id])

  const VERDICT = {
    exact: ['Exactly right.', 'You added what was needed and nothing else.'],
    overbuilt: ['Right, but too much.', 'Everything needed is there — along with things whose problem does not exist yet.'],
    underbuilt: ['Not enough.', 'What you added is correct; something the symptom demanded is missing.'],
    mixed: ['Not quite.', 'Something needed is missing, and something unneeded was added.'],
  }

  return (
    <div className="studio">
      <div className="st-head">
        <label className="scene-pick">
          <span>System</span>
          <select value={sceneId} onChange={e => setSceneId(e.target.value)}>
            {SCENES.map(s => <option key={s.id} value={s.id}>{s.title}</option>)}
          </select>
        </label>
        <span className="pq-count">brief {i + 1} / {briefs.length}</span>
      </div>

      <div className="st-brief">
        <span className="iv-h">The brief</span>
        <p className="st-have">
          <strong>You have today (V{b.fromV}):</strong>{' '}
          {b.have.map(label).join(' · ')}
        </p>
        <p className="st-traffic">
          <strong>Traffic is now:</strong> {b.traffic.label}
        </p>
        <p className="st-symptom">
          <strong>The symptom:</strong> {b.trigger}
        </p>
        <p className="hint">
          Current p99 is {b.prevMetrics.p99_ms} ms. What do you add? Adding nothing unnecessary
          counts for as much as adding the right thing.
        </p>
      </div>

      <div className="st-palette">
        <span className="iv-h">Available components</span>
        <div className="st-opts">
          {b.options.map(id => {
            const on = picked.includes(id)
            const state = result
              ? b.answer.includes(id)
                ? (on ? 'right' : 'missedopt')
                : (on ? 'wrong' : '')
              : (on ? 'picked' : '')
            return (
              <button
                key={id}
                className={`st-opt ${state}`}
                onClick={() => !result && toggle(id)}
                disabled={!!result}
              >
                <span className="st-mark" aria-hidden="true">
                  {result && b.answer.includes(id) ? '✓' : result && on ? '✗' : on ? '●' : '○'}
                </span>
                <span>{label(id)}</span>
                {scene.nodes[id]?.note && <em>{scene.nodes[id].note}</em>}
              </button>
            )
          })}
        </div>
      </div>

      {!result && (
        <div className="pq-actions">
          <button className="play" onClick={() => setResult(grade(b, picked))}>
            Submit design
          </button>
          <span className="hint">
            {picked.length === 0
              ? 'Submitting nothing is a valid answer — sometimes it is the right one.'
              : `${picked.length} component${picked.length > 1 ? 's' : ''} selected`}
          </span>
        </div>
      )}

      {result && (
        <div className={`st-result ${result.perfect ? 'good' : 'bad'}`}>
          <strong>{VERDICT[result.verdict][0]}</strong>
          <p>{VERDICT[result.verdict][1]}</p>

          {result.missed.length > 0 && (
            <div className="st-fb">
              <span className="iv-h">Missing</span>
              <ul>{result.missed.map(id => <li key={id}><strong>{label(id)}</strong></li>)}</ul>
            </div>
          )}

          {result.overbuilt.length > 0 && (
            <div className="st-fb over">
              <span className="iv-h">Not yet needed</span>
              <ul>
                {result.overbuilt.map(id => {
                  const w = whyWrong(scene, b, id)
                  return <li key={id}><strong>{label(id)}</strong> — {w.text}</li>
                })}
              </ul>
            </div>
          )}

          {b.note && (
            <div className="st-fb">
              <span className="iv-h">Why the reference design did this</span>
              <p>{b.note}</p>
            </div>
          )}

          <p className="hint">
            p99 goes {b.prevMetrics.p99_ms} ms → <strong>{b.metrics.p99_ms} ms</strong> at V{b.toV}.
          </p>

          <div className="pq-actions">
            <button className="tick" onClick={() => { setPicked([]); setResult(null) }}>
              Try again
            </button>
            <button className="play" onClick={() => setI(n => (n + 1) % briefs.length)}>
              Next brief ›
            </button>
          </div>
        </div>
      )}

      <p className="simnote">
        Graded against the next version of the scene file — the same data that draws the diagrams, so
        the reference design and the picture cannot disagree. <strong>Over-building costs you the
        same as under-building</strong>, because a component added before its problem exists is
        complexity you pay for forever.
      </p>
    </div>
  )
}
