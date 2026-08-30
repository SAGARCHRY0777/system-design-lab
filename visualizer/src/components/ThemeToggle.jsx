import { useEffect, useRef, useState } from 'react'
import { applyMode, readMode, THEMES } from '../lib/theme.js'

const ICON = {
  system: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="2" y="4" width="20" height="14" rx="2" /><path d="M8 21h8M12 18v3" />
    </svg>
  ),
  sun: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  ),
  moon: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  ),
}

const iconFor = id =>
  id === 'system' ? ICON.system
    : (id === 'light' || id === 'paper') ? ICON.sun
      : ICON.moon

/**
 * A menu rather than a cycle button.
 *
 * With three states a click-to-cycle control was fine. With six it is a puzzle
 * -- you would tap five times to get back to where you started, and you cannot
 * see what the options are without trying them. Six named swatches are honest
 * about what is available.
 */
export default function ThemeToggle() {
  const [mode, setMode] = useState('system')
  const [open, setOpen] = useState(false)
  const box = useRef(null)

  // Read on mount rather than in useState: this may first render against static
  // HTML where localStorage is not available.
  useEffect(() => {
    const m = readMode()
    setMode(m)
    applyMode(m)
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const away = e => { if (box.current && !box.current.contains(e.target)) setOpen(false) }
    const esc = e => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  const pick = id => {
    setMode(id)
    applyMode(id)
    setOpen(false)
  }

  const current = THEMES.find(t => t.id === mode) ?? THEMES[0]

  return (
    <div className="themer" ref={box}>
      <button
        className="themebtn"
        onClick={() => setOpen(o => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={`Theme: ${current.label}`}
      >
        {iconFor(mode)}
        <span>{current.label}</span>
      </button>

      {open && (
        <div className="themer-menu" role="menu">
          {THEMES.map(t => (
            <button
              key={t.id}
              role="menuitemradio"
              aria-checked={t.id === mode}
              className={t.id === mode ? 'themer-item on' : 'themer-item'}
              onClick={() => pick(t.id)}
            >
              <span className={`swatch sw-${t.id}`} aria-hidden="true" />
              <span className="themer-label">{t.label}</span>
              <span className="themer-hint">{t.hint}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
