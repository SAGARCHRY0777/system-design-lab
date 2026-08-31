import { useEffect, useMemo, useRef, useState } from 'react'
import { SCENES } from '../scenes/index.js'
import { decisionsForScene } from '../scenes/decisions.js'
import { buildBriefs, grade, whyWrong } from '../lib/studio.js'
import {
  REVERSIBILITY, assignDecisions, gradeDecision, verdictText,
} from '../lib/decisions.js'
import { missedIn, record } from '../lib/progress.js'

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
 *
 * A brief has two phases, and the second one is the one that matters more.
 * BUILD asks what to add. CONFIGURE asks what to set it to -- the shard key, the
 * TTL, the timeout. Choosing a component is the part that gets rehearsed because
 * it is what a diagram shows; choosing its parameters is the part that ends up
 * in the postmortem. Nobody writes "we should not have used a cache".
 */
export default function Studio() {
  const [sceneId, setSceneId] = useState(SCENES[0].id)
  const scene = useMemo(() => SCENES.find(s => s.id === sceneId) ?? SCENES[0], [sceneId])
  const briefs = useMemo(() => buildBriefs(scene), [scene])

  const [i, setI] = useState(0)
  const [picked, setPicked] = useState([])
  const [result, setResult] = useState(null)

  // Phase two: parameters.
  const [phase, setPhase] = useState('build')
  const [di, setDi] = useState(0)
  const [dPicked, setDPicked] = useState(null)
  const [dResult, setDResult] = useState(null)

  const reset = () => {
    setPicked([]); setResult(null)
    setPhase('build'); setDi(0); setDPicked(null); setDResult(null)
  }
  useEffect(() => { setI(0); reset() }, [sceneId])
  useEffect(reset, [i])

  const assigned = useMemo(
    () => assignDecisions(decisionsForScene(scene.id), briefs),
    [scene, briefs],
  )

  const b = briefs[Math.min(i, briefs.length - 1)]
  const decisions = assigned[Math.min(i, briefs.length - 1)] ?? []
  const d = decisions[di]

  // Every hook must sit ABOVE the early return below, or a scene with no briefs
  // changes how many hooks this component calls and React loses its place.
  //
  // Only the FIRST attempt at a decision is recorded. This phase has a "Try
  // again" button and Predict does not, so without this a reader could miss a
  // decision, retry it immediately, and erase their own miss -- record(_, true)
  // retires the entry. The retention list would then hold only the things you
  // had not yet bothered to retry, which is the opposite of what it is for.
  const attempted = useRef(new Set())
  useEffect(() => { attempted.current = new Set() }, [sceneId])

  const missedBefore = useMemo(
    () => (d ? missedIn('decision').includes(`${scene.id}:${d.id}`) : false),
    // `dResult` is the trigger: the tag must re-evaluate after a commit writes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [scene.id, d, dResult],
  )

  if (!b) return <div className="studio"><p className="hint">No briefs for this system.</p></div>

  const label = id => scene.nodes[id]?.label ?? id
  const toggle = id => setPicked(p => p.includes(id) ? p.filter(x => x !== id) : [...p, id])
  // Reset here as well as in the [i] effect. The effect only runs after paint,
  // so advancing would otherwise commit one frame holding the NEW brief's
  // decisions against the OLD phase and index -- a visible flash of a body with
  // nothing in it.
  const nextBrief = () => { reset(); setI(n => (n + 1) % briefs.length) }

  const rev = d ? REVERSIBILITY[d.reversibility] : null

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
          {phase === 'build'
            ? `Current p99 is ${b.prevMetrics.p99_ms} ms. What do you add? Adding nothing `
              + 'unnecessary counts for as much as adding the right thing.'
            : `You are at V${b.toV}. The components are decided — now set them.`}
        </p>
      </div>

      {phase === 'build' && (
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
      )}

      {phase === 'build' && !result && (
        <div className="pq-actions">
          <button
            className="play"
            onClick={() => {
              const g = grade(b, picked)
              setResult(g)
              record('studio', b.id, g.perfect)
            }}
          >
            Submit design
          </button>
          <span className="hint">
            {picked.length === 0
              ? 'Submitting nothing is a valid answer — sometimes it is the right one.'
              : `${picked.length} component${picked.length > 1 ? 's' : ''} selected`}
          </span>
        </div>
      )}

      {phase === 'build' && result && (
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
            {decisions.length > 0 ? (
              <button className="play" onClick={() => setPhase('configure')}>
                Now configure it ›
              </button>
            ) : (
              <button className="play" onClick={nextBrief}>Next brief ›</button>
            )}
          </div>
          {decisions.length > 0 && (
            <p className="hint">
              Choosing the component was the easy half. {decisions.length === 1
                ? 'There is one parameter'
                : `There are ${decisions.length} parameters`} to set, and at least one of
              them you will not get to change later.
            </p>
          )}
        </div>
      )}

      {phase === 'configure' && d && (
        <div className="st-decide">
          <div className="st-dhead">
            <span className="iv-h">Configure · {d.parameter}</span>
            <span className="pq-count">
              {missedBefore && <em className="st-again">missed before</em>}
              {di + 1} / {decisions.length}
            </span>
          </div>

          {/* The badge is the lesson. Everything else on this screen is the
              worked example that justifies it. */}
          <div className={`st-rev ${d.reversibility}`}>
            <strong>{rev.label}</strong>
            <span>{rev.blurb}</span>
          </div>

          <h2 className="pq-prompt">{d.question}</h2>

          <ul className="pq-options">
            {d.options.map(o => {
              const isPicked = dPicked === o.value
              const isAnswer = o.verdict === 'correct'
              const cls = [
                'pq-opt',
                isPicked && !dResult && 'picked',
                dResult && isAnswer && 'right',
                dResult && isPicked && !isAnswer && (o.verdict === 'defensible' ? 'maybe' : 'wrong'),
              ].filter(Boolean).join(' ')
              return (
                <li key={o.value}>
                  <button
                    className={cls}
                    onClick={() => !dResult && setDPicked(o.value)}
                    disabled={!!dResult}
                    aria-pressed={isPicked}
                  >
                    <span className="pq-mark" aria-hidden="true">
                      {dResult && isAnswer ? '✓'
                        : dResult && isPicked ? (o.verdict === 'defensible' ? '~' : '✗')
                          : isPicked ? '●' : '○'}
                    </span>
                    <span>{o.value}</span>
                  </button>
                </li>
              )
            })}
          </ul>

          {!dResult && (
            <div className="pq-actions">
              <button
                className="play"
                disabled={!dPicked}
                onClick={() => {
                  const g = gradeDecision(d, dPicked)
                  setDResult(g)
                  const key = `${scene.id}:${d.id}`
                  if (!attempted.current.has(key)) {
                    attempted.current.add(key)
                    record('decision', key, g.correct)
                  }
                }}
              >
                Commit
              </button>
              {!dPicked && <span className="hint">Commit to a value first.</span>}
            </div>
          )}

          {dResult && (
            <div className={`st-result ${dResult.correct ? 'good' : 'bad'}`}>
              <strong>{verdictText(dResult.verdict)[0]}</strong>
              <p>{verdictText(dResult.verdict)[1]}</p>

              <div className="st-fb">
                <span className="iv-h">
                  {dResult.correct ? 'Why' : `Why "${dResult.picked.value}" behaves that way`}
                </span>
                <p>{dResult.picked.because}</p>
              </div>

              {!dResult.correct && (
                <div className="st-fb">
                  <span className="iv-h">What this system needed</span>
                  <p><strong>{dResult.answer.value}</strong> — {dResult.answer.because}</p>
                </div>
              )}

              <div className="st-fb over">
                <span className="iv-h">If you need to change your mind</span>
                <p>{d.reversal}</p>
              </div>

              <div className="pq-actions">
                <button
                  className="tick"
                  onClick={() => { setDPicked(null); setDResult(null) }}
                >
                  Try again
                </button>
                {di + 1 < decisions.length ? (
                  <button
                    className="play"
                    onClick={() => { setDi(n => n + 1); setDPicked(null); setDResult(null) }}
                  >
                    Next parameter ›
                  </button>
                ) : (
                  <button className="play" onClick={nextBrief}>Next brief ›</button>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      <p className="simnote">
        {phase === 'build' ? (
          <>
            Graded against the next version of the scene file — the same data that draws the
            diagrams, so the reference design and the picture cannot disagree.{' '}
            <strong>Over-building costs you the same as under-building</strong>, because a component
            added before its problem exists is complexity you pay for forever.
          </>
        ) : (
          <>
            Some of these are a config change and some are a migration, and the badge tells you
            which before you choose. <strong>That distinction is the point.</strong> Reversible
            decisions should be made quickly and corrected with data; one-way decisions deserve the
            argument, and they are usually made earliest, when the system is smallest and it feels
            like they matter least.
          </>
        )}
      </p>
    </div>
  )
}
