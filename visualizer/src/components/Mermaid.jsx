import { useEffect, useRef, useState } from 'react'

/**
 * Render a Mermaid diagram.
 *
 * Mermaid is ~500KB, which is more than the rest of this app put together, so
 * it is loaded with a dynamic import: Vite splits it into its own chunk and the
 * browser only fetches it when someone actually opens a view that draws one.
 * The initial load pays nothing.
 *
 * The theme is resolved from the page's own CSS custom properties rather than
 * from a Mermaid theme name, so a diagram follows whichever of the six palettes
 * the reader chose. It re-renders when the theme changes, because Mermaid bakes
 * colours into the SVG at render time and will not pick up a later change.
 */

let mermaidPromise = null

function loadMermaid() {
  // One import for the whole app, shared by every diagram on the page.
  mermaidPromise ??= import('mermaid').then(m => m.default)
  return mermaidPromise
}

function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

/** Watch for a theme change, since Mermaid cannot react to CSS on its own. */
function useThemeTick() {
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const bump = () => setTick(t => t + 1)
    const mo = new MutationObserver(bump)
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    mq.addEventListener('change', bump)
    return () => { mo.disconnect(); mq.removeEventListener('change', bump) }
  }, [])
  return tick
}

export default function Mermaid({ chart, id }) {
  const host = useRef(null)
  const [error, setError] = useState(null)
  const tick = useThemeTick()

  useEffect(() => {
    let alive = true
    if (!chart) return undefined

    loadMermaid().then(mermaid => {
      if (!alive) return
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        fontFamily: 'inherit',
        themeVariables: {
          background:        cssVar('--panel', '#fff'),
          primaryColor:      cssVar('--sunken', '#eee'),
          primaryTextColor:  cssVar('--ink', '#111'),
          primaryBorderColor: cssVar('--line2', '#999'),
          lineColor:         cssVar('--line2', '#999'),
          secondaryColor:    cssVar('--sunken', '#eee'),
          tertiaryColor:     cssVar('--panel', '#fff'),
          fontSize: '14px',
        },
      })
      // A unique id per render: Mermaid caches by id and would otherwise reuse
      // the previous theme's SVG.
      return mermaid.render(`m-${id}-${tick}`, chart)
    })
      .then(res => {
        if (!alive || !res || !host.current) return
        host.current.innerHTML = res.svg
        setError(null)
      })
      .catch(e => {
        if (!alive) return
        // A diagram that will not parse should not take the page with it.
        setError(String(e?.message ?? e).split('\n')[0])
      })

    return () => { alive = false }
  }, [chart, id, tick])

  if (error) {
    return (
      <pre className="mmd-fallback" aria-label="Diagram source">
        {chart}
      </pre>
    )
  }
  return <div className="mmd" ref={host} />
}
