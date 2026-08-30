import { useState } from 'react'
import CASES from '../../../17-case-studies/cases.json'
import Mermaid from './Mermaid.jsx'

/**
 * Real systems, with their sources.
 *
 * The two fields given the most weight are `surprise` and `doesNotApply`, and
 * the second one is the reason this tab is not just a list of famous
 * architectures. A case study read without it becomes a licence to copy
 * Dynamo into a single-datacentre service doing forty requests a second, which
 * is a straightforward mistake and a common one.
 *
 * So the page is ordered against the grain of how these are usually written:
 * the surprise and the "when this is wrong for you" sit above the architecture,
 * not in a footnote after it.
 */
export default function CaseStudies() {
  const [selected, setSelected] = useState(CASES.cases[0].id)
  const c = CASES.cases.find(x => x.id === selected) ?? CASES.cases[0]

  return (
    <div className="patterns cs">
      <div className="pat-side">
        <p className="hint" style={{ margin: '0 0 4px' }}>
          {CASES.cases.length} systems, each with a primary source.
        </p>
        <ul className="pat-list">
          {CASES.cases.map(x => (
            <li key={x.id}>
              <button
                className={x.id === selected ? 'pat-item on' : 'pat-item'}
                onClick={() => setSelected(x.id)}
              >
                <strong>{x.system}</strong>
                <em>{x.title} · {x.year}</em>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="pat-detail">
        <span className="iv-lv lv-basic">{c.year}</span>
        <h2>{c.system} — {c.title}</h2>
        <p className="cs-scale">{c.scale}</p>

        <div className="iv-asking">
          <span>The surprise</span>
          <p>{c.surprise}</p>
        </div>

        {/* Above the architecture on purpose: the limit of a case study is
            more useful than its design, and it is what gets skipped. */}
        <div className="cs-warn">
          <span className="iv-h">When this does NOT apply to you</span>
          <p>{c.doesNotApply}</p>
        </div>

        <div className="cs-block">
          <span className="iv-h">The problem</span>
          <p>{c.problem}</p>
        </div>

        {c.constraints?.length > 0 && (
          <div className="cs-block">
            <span className="iv-h">What they could not change</span>
            <ul className="cs-list">{c.constraints.map((x, i) => <li key={i}>{x}</li>)}</ul>
          </div>
        )}

        <div className="cs-block">
          <span className="iv-h">What they built</span>
          <p>{c.approach}</p>
        </div>

        {c.diagram && (
          <div className="pat-diagram">
            <Mermaid chart={c.diagram} id={`cs-${c.id}`} />
          </div>
        )}

        {c.keyDecisions?.length > 0 && (
          <div className="cs-block">
            <span className="iv-h">Key decisions — and what each cost</span>
            <div className="cs-decisions">
              {c.keyDecisions.map((d, i) => (
                <div className="cs-dec" key={i}>
                  <strong>{d.decision}</strong>
                  <p><em>Why</em> {d.why}</p>
                  <p className="cs-cost"><em>Cost</em> {d.cost}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="cs-block">
          <span className="iv-h">When it applies to you</span>
          <p>{c.applies}</p>
        </div>

        <p className="cs-source">
          <span className="iv-h">Source</span>
          <a href={c.sourceUrl} target="_blank" rel="noopener noreferrer">{c.source}</a>
        </p>

        {c.seeAlso?.length > 0 && (
          <p className="hint">
            Related:{' '}
            {c.seeAlso.map((s, i) => (
              <span key={s}>
                {i > 0 && ' · '}
                <a
                  href={`https://github.com/SAGARCHRY0777/system-design-lab/tree/main/${s}`}
                  target="_blank"
                  rel="noopener noreferrer"
                >{s}</a>
              </span>
            ))}
          </p>
        )}
      </div>
    </div>
  )
}
