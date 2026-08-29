import { useEffect, useState } from 'react'

/**
 * "Star on GitHub" with a live count.
 *
 * An honest note on what this can and cannot do: there is no URL that stars a
 * repository. GitHub requires the click to happen on their side, by a signed-in
 * user, because otherwise any page could farm stars from anyone who visited it.
 * So this button does the two things that ARE possible -- show the real current
 * count, and put the reader one click from the button that works.
 *
 * The count comes from the public API, which needs no token but is rate limited
 * to 60 requests per hour per IP. It is cached for an hour so a reader clicking
 * around the app does not spend that budget, and every failure path falls back
 * to rendering the button with no number rather than breaking.
 */

const REPO = 'SAGARCHRY0777/system-design-lab'
const CACHE_KEY = 'sdl-stars'
const TTL_MS = 60 * 60 * 1000

function readCache() {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const { n, at } = JSON.parse(raw)
    return Date.now() - at < TTL_MS ? n : null
  } catch {
    return null // private window, blocked storage -- not worth handling further
  }
}

function writeCache(n) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ n, at: Date.now() }))
  } catch {
    // A reader who cannot cache still gets the button.
  }
}

export default function StarButton() {
  const [stars, setStars] = useState(readCache)

  useEffect(() => {
    if (stars !== null) return undefined
    let alive = true
    fetch(`https://api.github.com/repos/${REPO}`)
      .then(r => (r.ok ? r.json() : null))
      .then(d => {
        if (!alive || !d || typeof d.stargazers_count !== 'number') return
        setStars(d.stargazers_count)
        writeCache(d.stargazers_count)
      })
      .catch(() => { /* rate limited or offline: render without a count */ })
    return () => { alive = false }
  }, [stars])

  return (
    <a
      className="starbtn"
      href={`https://github.com/${REPO}`}
      target="_blank"
      rel="noopener noreferrer"
      title="Star this repository on GitHub"
    >
      <svg viewBox="0 0 16 16" aria-hidden="true">
        <path d="M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25z" />
      </svg>
      <span>Star</span>
      {stars !== null && <span className="starcount">{stars.toLocaleString()}</span>}
    </a>
  )
}
