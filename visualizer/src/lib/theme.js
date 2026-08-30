/**
 * Theme: five palettes plus system.
 *
 * `system` stamps nothing and lets prefers-color-scheme decide, because a page
 * that ignores the OS setting is annoying in exactly the situation the setting
 * exists for. Its dark branch resolves to SLATE rather than midnight -- a soft
 * dark is the better default, and the deepest one stays available to anyone who
 * actually wants it.
 *
 * localStorage can throw outright in a private window or with site data
 * blocked, so every access is guarded and an unreadable store means `system`.
 */

const KEY = 'sdl-theme'

export const THEMES = [
  { id: 'system',   label: 'System',   hint: 'Follow the operating system' },
  { id: 'light',    label: 'Light',    hint: 'Cool paper' },
  { id: 'paper',    label: 'Paper',    hint: 'Warm light' },
  { id: 'slate',    label: 'Slate',    hint: 'Soft dark' },
  { id: 'midnight', label: 'Midnight', hint: 'Deep dark' },
  { id: 'ember',    label: 'Ember',    hint: 'Warm dark' },
]

const IDS = THEMES.map(t => t.id)

export function readMode() {
  try {
    const v = localStorage.getItem(KEY)
    return IDS.includes(v) ? v : 'system'
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
