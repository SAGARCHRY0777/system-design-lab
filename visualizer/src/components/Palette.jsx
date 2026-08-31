import { useEffect, useMemo, useRef, useState } from 'react'

/**
 * The command palette.
 *
 * There are six systems, forty-eight versions, sixty request flows and
 * thirty-five failure modes in here, and until now the only way to reach any of
 * them was three dropdowns and a slider. That is fine the first time and hostile
 * the twentieth, which is the usage pattern this app is actually built for.
 *
 * So: one key, type what you want, land on it. "eu region down" goes to the URL
 * shortener at V8 with the flow already selected. "thundering" finds the cache
 * failure that causes it.
 *
 * Scoring is deliberately simple and explainable rather than clever. An exact
 * prefix beats a word-boundary match, which beats a substring, which beats
 * subsequence -- so typing the first letters of a title always finds that title,
 * and nothing outranks it for reasons the reader cannot see.
 */

/** Score `q` against `text`. Higher is better; 0 means no match. */
function score(text, q) {
  const t = text.toLowerCase()
  if (!q) return 1
  if (t === q) return 1000
  if (t.startsWith(q)) return 800 - t.length
  // Word-boundary hit: "reg fail" should find "Regional failure".
  const words = t.split(/[^a-z0-9]+/).filter(Boolean)
  if (words.some(w => w.startsWith(q))) return 600 - t.length
  const at = t.indexOf(q)
  if (at >= 0) return 400 - at - t.length * 0.1
  // Subsequence, so "urlsh" still finds "URL Shortener".
  let i = 0
  for (const ch of t) if (ch === q[i]) i++
  return i === q.length ? 100 - t.length * 0.1 : 0
}

/** Every query term must hit something; the total is the sum of the best hits. */
function rank(item, query) {
  const terms = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!terms.length) return 1
  const fields = [item.title, item.subtitle ?? '', item.group]
  let total = 0
  for (const term of terms) {
    const best = Math.max(...fields.map(f => score(f, term)))
    if (best <= 0) return 0
    total += best
  }
  return total
}

export default function Palette({ commands, open, setOpen, onOpen }) {
  const [q, setQ] = useState('')
  const [sel, setSel] = useState(0)
  const inputRef = useRef(null)
  const listRef = useRef(null)

  useEffect(() => {
    const onKey = e => {
      const mod = e.metaKey || e.ctrlKey
      if (mod && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen(o => !o)
        return
      }
      // "/" is the other convention readers expect, but not while they are
      // typing into something -- including this palette's own input.
      const tag = e.target?.tagName
      const typing = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
        || e.target?.isContentEditable
      if (e.key === '/' && !typing) {
        e.preventDefault()
        setOpen(true)
      }
      if (e.key === 'Escape') setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setOpen])

  useEffect(() => {
    if (!open) { setQ(''); setSel(0); return }
    onOpen?.()
    // Focus after paint, or the browser may hand focus back to whatever had it.
    const id = requestAnimationFrame(() => inputRef.current?.focus())
    return () => cancelAnimationFrame(id)
  }, [open, onOpen])

  const results = useMemo(() => {
    const scored = commands
      .map(c => ({ c, s: rank(c, q) }))
      .filter(x => x.s > 0)
      .sort((a, b) => b.s - a.s)
      .slice(0, 40)
      .map(x => x.c)
    return scored
  }, [commands, q])

  useEffect(() => { setSel(0) }, [q])

  // Keep the highlighted row in view when arrowing past the fold.
  useEffect(() => {
    const el = listRef.current?.querySelector('[data-sel="true"]')
    el?.scrollIntoView({ block: 'nearest' })
  }, [sel, results])

  if (!open) return null

  const run = item => { setOpen(false); item.run() }

  const onKeyDown = e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setSel(i => Math.min(i + 1, results.length - 1)) }
    if (e.key === 'ArrowUp') { e.preventDefault(); setSel(i => Math.max(i - 1, 0)) }
    if (e.key === 'Enter' && results[sel]) { e.preventDefault(); run(results[sel]) }
  }

  // Group headers, without reordering: the list is already in score order, so a
  // group label is printed the first time its group appears.
  const seen = new Set()

  return (
    <div className="pal-scrim" onMouseDown={e => { if (e.target === e.currentTarget) setOpen(false) }}>
      <div className="pal" role="dialog" aria-modal="true" aria-label="Command palette">
        <div className="pal-input">
          <span aria-hidden="true">⌕</span>
          <input
            ref={inputRef}
            value={q}
            onChange={e => setQ(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Jump to a system, version, request flow, failure or decision…"
            aria-label="Search"
            autoComplete="off"
            spellCheck="false"
          />
          <kbd>esc</kbd>
        </div>

        <ul className="pal-list" ref={listRef}>
          {results.length === 0 && (
            <li className="pal-empty">
              Nothing matches <strong>{q}</strong>. Try a component, a symptom, or a version.
            </li>
          )}
          {results.map((item, i) => {
            const first = !seen.has(item.group)
            seen.add(item.group)
            return (
              <li key={item.id}>
                {first && <div className="pal-group">{item.group}</div>}
                <button
                  className={i === sel ? 'pal-item on' : 'pal-item'}
                  data-sel={i === sel}
                  onMouseMove={() => setSel(i)}
                  onClick={() => run(item)}
                >
                  <span className="pal-title">{item.title}</span>
                  {item.subtitle && <span className="pal-sub">{item.subtitle}</span>}
                </button>
              </li>
            )
          })}
        </ul>

        <div className="pal-foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> move</span>
          <span><kbd>↵</kbd> go</span>
          <span><kbd>⌘</kbd><kbd>K</kbd> toggle</span>
          <span className="pal-count">{results.length} of {commands.length}</span>
        </div>
      </div>
    </div>
  )
}
