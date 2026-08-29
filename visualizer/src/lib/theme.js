/**
 * Theme: three states, not two.
 *
 *   'light' / 'dark'  -- an explicit choice, stamped on <html data-theme>
 *   'system'          -- stamp nothing and let prefers-color-scheme decide
 *
 * The default is 'system', because a page that ignores the OS setting is
 * annoying in exactly the situation the setting exists for.
 *
 * localStorage can throw outright in a private window or with site data
 * blocked, so every access is guarded and an unreadable store simply means
 * 'system'.
 */

const KEY = 'sdl-theme'
export const MODES = ['system', 'light', 'dark']

export function readMode() {
  try {
    const v = localStorage.getItem(KEY)
    return MODES.includes(v) ? v : 'system'
  } catch {
    return 'system'
  }
}

export function applyMode(mode) {
  const root = document.documentElement
  if (mode === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', mode)
  try {
    localStorage.setItem(KEY, mode)
  } catch {
    // A viewer who cannot persist the choice should still get the choice.
  }
}

export function nextMode(mode) {
  return MODES[(MODES.indexOf(mode) + 1) % MODES.length]
}
