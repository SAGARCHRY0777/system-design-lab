/**
 * Parse every mermaid block in the repository with the real mermaid engine.
 *
 * `scripts/check_mermaid.py` is a heuristic: it counts brackets and looks for
 * known-bad shapes. That catches typos and it cannot catch a diagram that is
 * well-formed text and invalid mermaid -- an unsupported node shape, a
 * `direction` in a diagram type that has no such keyword, a `%` that silently
 * starts a comment and eats the rest of the line.
 *
 * There are 300+ blocks here and they render on GitHub, where a broken one
 * shows the reader a red error box instead of the picture the page is arguing
 * with. So this runs the actual parser.
 *
 * mermaid needs a DOM, hence jsdom. An earlier attempt to run it bare in node
 * failed every block with "DOMPurify.addHook is not a function" -- identically,
 * before parsing anything -- which looks exactly like a real failure and is not
 * one. A check that fails everything proves as little as one that passes
 * everything.
 *
 *     npm run check:mermaid
 */

import { readFileSync } from 'node:fs'
import { execSync } from 'node:child_process'
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  pretendToBeVisual: true,
})
globalThis.window = dom.window
globalThis.document = dom.window.document
// Node 21+ defines a getter-only `navigator`, so plain assignment throws.
Object.defineProperty(globalThis, 'navigator', {
  value: dom.window.navigator, configurable: true, writable: true,
})
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.SVGElement = dom.window.SVGElement
globalThis.Element = dom.window.Element
globalThis.Node = dom.window.Node
globalThis.DOMParser = dom.window.DOMParser
globalThis.XMLSerializer = dom.window.XMLSerializer
globalThis.getComputedStyle = dom.window.getComputedStyle
globalThis.requestAnimationFrame = cb => setTimeout(cb, 0)

const mermaid = (await import('mermaid')).default
mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' })

const files = execSync('git ls-files "*.md"', { cwd: '..', encoding: 'utf8' })
  .split('\n').filter(Boolean)

let blocks = 0
let fail = 0
const failures = []

for (const rel of files) {
  // Normalise line endings FIRST. Half these files are CRLF on this machine,
  // and a /```mermaid\n/ regex matches none of them -- the first run of this
  // script silently checked 294 of 302 blocks and reported success. A checker
  // that skips what it cannot see is worse than no checker, so the count is
  // asserted against check_mermaid.py below.
  const txt = readFileSync(new URL(`../../${rel}`, import.meta.url), 'utf8')
    .replace(/\r\n/g, '\n')
  const found = [...txt.matchAll(/```mermaid\n([\s\S]*?)```/g)].map(m => m[1])
  for (const [i, body] of found.entries()) {
    blocks++
    try {
      await mermaid.parse(body)
    } catch (e) {
      fail++
      const msg = String(e?.message ?? e).split('\n').find(Boolean) ?? '?'
      failures.push(`${rel} block ${i + 1}: ${msg.slice(0, 160)}`)
    }
  }
}

// A run where nothing parsed is an environment failure wearing a content
// failure's clothes. Say so rather than printing 300 plausible errors.
if (fail === blocks && blocks > 0) {
  console.log(`every one of ${blocks} blocks failed identically -- this is the `
    + 'harness, not the diagrams. First error:')
  console.log(`  ${failures[0]}`)
  process.exit(1)
}

for (const f of failures) console.log(`  FAIL ${f}`)

// Cross-check the block count against the Python checker. If the two disagree
// this script is skipping blocks, and skipped blocks report as success.
let expected = null
try {
  const out = execSync('python scripts/check_mermaid.py', { cwd: '..', encoding: 'utf8' })
  expected = Number(out.match(/(\d+) mermaid block/)?.[1] ?? NaN)
} catch { /* that checker reports its own failures; only the count is wanted */ }

if (Number.isFinite(expected) && expected !== blocks) {
  console.log(`\ncounted ${blocks} blocks but check_mermaid.py sees ${expected} -- `
    + 'this script is skipping some, and skipped blocks look like passing ones')
  process.exit(1)
}

console.log(fail
  ? `\n${fail} of ${blocks} mermaid block(s) do not parse`
  : `${blocks} mermaid blocks across ${files.length} files: all parse `
    + `(count agrees with check_mermaid.py)`)
process.exit(fail ? 1 : 0)
