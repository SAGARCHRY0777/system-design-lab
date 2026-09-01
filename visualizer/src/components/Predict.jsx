import { useEffect, useMemo, useState } from 'react'
import { buildQuiz } from '../lib/quiz.js'
import { missedIn, record } from '../lib/progress.js'
import SceneDiagram from './SceneDiagram.jsx'

/**
 * Commit-then-reveal.
 *
 * The reveal is gated behind a choice on purpose. Learning happens when a
 * confident prediction is violated, and a reader who has not committed to an
 * answer cannot be surprised by the right one -- they just read it and agree.
 *
 * No score, no streak, no badges. The correction IS the teaching, and points
 * displace understanding with point-chasing.
 */
export default function Predict({ scene, onReplay }) {
  const all = useMemo(() => buildQuiz(scene), [scene])
  const [onlyMissed, setOnlyMissed] = useState(false)

  // Practising your misses is the whole reason anything is recorded. If nothing
  // has been missed yet the filter is offered but empty, so it falls back
  // rather than showing a blank pane.
  const questions = useMemo(() => {
    if (!onlyMissed) return all
    const missed = new Set(missedIn('predict'))
    const subset = all.filter(q => missed.has(q.id))
    return subset.length ? subset : all
  }, [all, onlyMissed])
  const [i, setI] = useState(0)
  const [picked, setPicked] = useState(null)
  const [revealed, setRevealed] = useState(false)

  useEffect(() => { setI(0); setPicked(null); setRevealed(false) }, [scene])

  const q = questions[i]
  if (!q) {
    return <div className="predict"><p className="hint">No questions for this system yet.</p></div>
  }

  const correct = revealed && picked === q.correct
  const qVersion = scene.versions.find(v => v.v === q.version)
  // Marks appear only after the reveal -- showing which box is the answer
  // beforehand would give the question away.
  const answerStatus = revealed ? (q.mark ?? {}) : {}
  const next = () => {
    setI(n => (n + 1) % questions.length)
    setPicked(null)
    setRevealed(false)
  }

  return (
    <div className="predict">
      <div className="pq-head">
        <span className="pq-kind">{q.kind}</span>
        <div className="pq-headright">
          <button
            className={onlyMissed ? 'tick on' : 'tick'}
            onClick={() => { setOnlyMissed(v => !v); setI(0); setPicked(null); setRevealed(false) }}
            title="Only the questions you have got wrong and not yet corrected"
          >
            Practise misses
          </button>
          <span className="pq-count">{i + 1} / {questions.length}</span>
        </div>
      </div>

      <h2 className="pq-prompt">{q.prompt}</h2>

      {/* The question names components; without the picture the reader has to
          hold the architecture in their head and the question tests memory
          instead of reasoning. After the reveal the answer is marked on the
          diagram, so the correction is spatial as well as verbal. */}
      {qVersion && (
        <SceneDiagram
          scene={scene}
          active={qVersion.active}
          edges={qVersion.edges}
          status={answerStatus}
          compact
          caption={`V${qVersion.v} — ${qVersion.label}`}
        />
      )}

      <ul className="pq-options">
        {q.options.map(opt => {
          const isPicked = picked === opt
          const isAnswer = opt === q.correct
          const cls = [
            'pq-opt',
            isPicked && !revealed && 'picked',
            revealed && isAnswer && 'right',
            revealed && isPicked && !isAnswer && 'wrong',
          ].filter(Boolean).join(' ')
          return (
            <li key={opt}>
              <button
                className={cls}
                onClick={() => !revealed && setPicked(opt)}
                disabled={revealed}
                aria-pressed={isPicked}
              >
                <span className="pq-mark" aria-hidden="true">
                  {revealed && isAnswer ? '✓' : revealed && isPicked ? '✗' : isPicked ? '●' : '○'}
                </span>
                <span>{opt}</span>
              </button>
            </li>
          )
        })}
      </ul>

      {!revealed && (
        <div className="pq-actions">
          <button
            className="play"
            onClick={() => { setRevealed(true); record('predict', q.id, picked === q.correct) }}
            disabled={!picked}
          >
            Reveal
          </button>
          {!picked && <span className="hint">Commit to an answer first.</span>}
        </div>
      )}

      {revealed && (
        <div className={correct ? 'pq-result right' : 'pq-result wrong'}>
          <strong>{correct ? 'Correct.' : 'Not quite.'}</strong>
          {!correct && <p className="pq-was">The answer is <em>{q.correct}</em>.</p>}
          <p>{q.because}</p>
          <div className="pq-actions">
            {q.replay && (
              <button className="tick" onClick={() => onReplay(q.replay)}>
                Watch it happen ›
              </button>
            )}
            <button className="play" onClick={next}>Next ›</button>
          </div>
        </div>
      )}

      <p className="simnote">
        Every question and every answer here is derived from the scene file — the same data that
        drives the diagram and the animation, so the quiz cannot disagree with what you are about
        to watch.
      </p>
    </div>
  )
}
