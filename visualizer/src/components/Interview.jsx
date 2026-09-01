import { useEffect, useMemo, useState } from 'react'
import BANK from '../../../20-system-design-interview/questions.json'
import Mermaid from './Mermaid.jsx'

/**
 * The interview tab.
 *
 * Two decisions shape it.
 *
 * The answer is folded, like everything else here -- reading an answer you did
 * not attempt teaches nothing, and this whole repository exists because it used
 * to print both on the same line.
 *
 * Follow-ups reveal ONE AT A TIME, in order. That is not decoration: anyone can
 * recite a first answer, and the actual test of whether someone understands a
 * system is the third question down the chain. Showing all three at once turns
 * an escalation into a list and loses the thing being simulated.
 */

const REPO = 'https://github.com/SAGARCHRY0777/system-design-lab'
const LEVELS = ['basic', 'intermediate', 'advanced']

/** seeAlso is a repo-relative path and may be a file or a directory. */
function repoLink(path) {
  const kind = /\.[a-z]+$/i.test(path) ? 'blob' : 'tree'
  return `${REPO}/${kind}/main/${path}`
}

export default function Interview() {
  const [trackId, setTrackId] = useState(BANK.tracks[0].id)
  const [levels, setLevels] = useState(() => new Set(LEVELS))
  const [selected, setSelected] = useState(null)
  const [revealed, setRevealed] = useState(false)
  const [shown, setShown] = useState(0)   // how many follow-ups are visible

  const track = BANK.tracks.find(t => t.id === trackId) ?? BANK.tracks[0]

  const questions = useMemo(
    () => track.questions.filter(q => levels.has(q.level)),
    [track, levels],
  )

  // Changing track or filter can strip the current selection out of the list.
  useEffect(() => {
    if (!questions.length) { setSelected(null); return }
    if (!questions.some(q => q.id === selected)) setSelected(questions[0].id)
  }, [questions, selected])

  useEffect(() => { setRevealed(false); setShown(0) }, [selected])

  const q = questions.find(x => x.id === selected) ?? null

  const toggleLevel = lv => setLevels(prev => {
    const next = new Set(prev)
    if (next.has(lv)) next.delete(lv); else next.add(lv)
    // Removing the last filter would show nothing at all, which is never what
    // anyone meant by unticking a box.
    return next.size ? next : prev
  })

  const totals = BANK.tracks.reduce((n, t) => n + t.questions.length, 0)

  return (
    <div className="patterns iv">
      <div className="pat-side">
        <div className="iv-levels">
          {LEVELS.map(lv => (
            <button
              key={lv}
              className={levels.has(lv) ? 'tick on' : 'tick'}
              onClick={() => toggleLevel(lv)}
              title={`Show ${lv} questions`}
            >
              {lv[0].toUpperCase()}{lv.slice(1)}
            </button>
          ))}
        </div>

        <div className="pat-fams">
          {BANK.tracks.map(t => (
            <button
              key={t.id}
              className={t.id === trackId ? 'tick on' : 'tick'}
              onClick={() => setTrackId(t.id)}
            >
              {t.name} <span>{t.questions.length}</span>
            </button>
          ))}
        </div>

        <p className="hint" style={{ margin: '2px 0 0' }}>{track.blurb}</p>

        {/* The shape this track's questions keep circling back to. Generated
            from the same source as QUESTIONS.md, so the page and the app show
            the same picture. */}
        {track.diagram && (
          <div className="iv-diagram">
            <Mermaid chart={track.diagram} id={`track-${track.id}`} />
          </div>
        )}

        <ul className="pat-list">
          {questions.map(x => (
            <li key={x.id}>
              <button
                className={x.id === selected ? 'pat-item on' : 'pat-item'}
                onClick={() => setSelected(x.id)}
              >
                <strong>{x.q}</strong>
                <em className={`lv lv-${x.level}`}>{x.level}</em>
              </button>
            </li>
          ))}
          {!questions.length && <li className="hint">No questions at that level.</li>}
        </ul>
      </div>

      <div className="pat-detail">
        {!q && <p className="hint">Select a question.</p>}
        {q && (
          <>
            <span className={`iv-lv lv-${q.level}`}>{q.level}</span>
            <h2>{q.q}</h2>

            <div className="iv-asking">
              <span>What they are actually probing</span>
              <p>{q.asking}</p>
            </div>

            {!revealed && (
              <button className="play" onClick={() => setRevealed(true)}>
                Show a good answer
              </button>
            )}

            {revealed && (
              <>
                <div className="iv-answer">
                  <span className="iv-h">A good answer</span>
                  <p>{q.answer}</p>
                </div>

                {q.redFlags?.length > 0 && (
                  <div className="iv-flags">
                    <span className="iv-h">Red flags</span>
                    <ul>{q.redFlags.map((f, i) => <li key={i}>{f}</li>)}</ul>
                  </div>
                )}

                {q.followUps?.length > 0 && (
                  <div className="iv-followups">
                    <span className="iv-h">
                      Follow-ups — {shown} of {q.followUps.length}
                    </span>
                    <p className="hint" style={{ marginTop: 0 }}>
                      Anyone can recite a first answer. The chain is the test.
                    </p>

                    {q.followUps.slice(0, shown).map((f, i) => (
                      <div className="iv-fu" key={i}>
                        <strong>{f.q}</strong>
                        <p>{f.answer}</p>
                      </div>
                    ))}

                    {shown < q.followUps.length && (
                      <button className="tick" onClick={() => setShown(n => n + 1)}>
                        {shown === 0 ? 'And then they ask…' : 'And then…'}
                      </button>
                    )}
                  </div>
                )}

                {q.seeAlso && (
                  <p className="hint">
                    Read the topic:{' '}
                    <a href={repoLink(q.seeAlso)} target="_blank" rel="noopener noreferrer">
                      {q.seeAlso}
                    </a>
                  </p>
                )}
              </>
            )}
          </>
        )}
      </div>

      <p className="iv-count">
        {totals} questions across {BANK.tracks.length} tracks, generated from the same data as the
        repository&rsquo;s question bank.
      </p>
    </div>
  )
}
