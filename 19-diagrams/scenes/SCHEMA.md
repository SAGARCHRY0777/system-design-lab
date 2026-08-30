# Scene format

A **scene** describes one architecture across its whole life — every version it passes through as
traffic grows, every request path through it, and every way it breaks. It is authored once, as data,
and rendered two ways: to committed animated SVGs for the markdown, and to the interactive
visualizer. Neither renderer may contain architecture knowledge of its own.

Scenes carry **no pixel coordinates**. Layout is computed by topological rank, so adding a node never
means re-positioning the others by hand.

---

## Top level

```jsonc
{
  "id":      "url-shortener",        // filename stem, kebab-case, used in generated SVG names
  "title":   "URL Shortener",
  "summary": "One sentence on what the system does.",
  "nodes":    { ... },               // every node that appears in ANY version
  "versions": [ ... ],               // ordered; the V1→V8 scrubber
  "flows":    [ ... ],               // animated request paths
  "failures": [ ... ]                // what breaks when a node dies
}
```

## `nodes`

Declared once for the whole scene; each version then lists which are active. Keeps ids stable across
versions so the scrubber can animate a node appearing rather than redrawing everything.

```jsonc
"nodes": {
  "client": { "kind": "client",  "label": "Client" },
  "cache":  { "kind": "cache",   "label": "Cache", "note": "read-through, 60s TTL" }
}
```

`kind` must be one of `client · edge · lb · service · cache · store · queue · external` —
see the [notation contract](../README.md#1-node-kinds). `note` is optional and renders as a subtitle.

## `versions`

The heart of the format. Each entry is one step in the architecture's evolution, and **`trigger` is
the most important field in the whole schema** — it is the answer to "why did this change?", which is
the thing §38 exists to teach. A version without a trigger is a diagram; a version with one is a
lesson.

```jsonc
{
  "v": 4,
  "label": "200M req/day",
  "trigger": "p99 hit 800ms. 92% of reads were for the top 0.1% of keys.",
  "traffic": { "rps": 2314, "label": "200M/day" },
  "active": ["client", "lb", "app", "cache", "db"],
  "edges": [
    { "from": "client", "to": "lb",    "kind": "sync" },
    { "from": "app",    "to": "cache", "kind": "sync", "label": "read-through" },
    { "from": "app",    "to": "db",    "kind": "sync" }
  ],
  "metrics":    { "p50_ms": 8, "p99_ms": 45 },
  "bottleneck": "db",              // node id, or null — highlighted amber
  "note": "Optional paragraph shown beside the diagram."
}
```

`edges[].kind` is one of `sync · async · replication`. Sum the `sync` hops to reason about
user-visible latency; `async` hops do not add to it.

Metrics are **hypothetical unless the scene says otherwise** — they illustrate the shape of a
change, not a measurement of a real system. Where a number is real, cite it in `note`.

## `flows`

Named request paths the visualizer animates and the SVG renderer draws as a moving dot.

```jsonc
{
  "id": "cache-miss",
  "label": "Cache miss",
  "minVersion": 4,                 // only offered from V4 on, when the cache exists
  "path": ["client", "lb", "app", "cache", "db", "app", "client"],
  "outcome": "Miss costs a full DB round trip, then populates the cache."
}
```

The path may revisit nodes — that is how a response returning along the same hops is expressed.

## `failures`

Powers the component toggles: switch a node off and see what actually happens.

```jsonc
{
  "id": "cache-down",
  "node": "cache",
  "minVersion": 4,
  "effect": "Every read falls through to the database at once — a thundering herd.",
  "bottleneck": "db",
  "survivable": true               // false = user-visible outage
}
```

`survivable: true` on a `cache` node and `false` on a `store` node is usually the correct pairing,
and is exactly the dashed-vs-solid distinction from the notation contract.

---

## `decisions/<id>.json` — the parameters

A sibling file, not a field on the scene. Where the scene records *which components exist*, this
records **what they were set to**: the shard key, the TTL, the replication mode, the timeout. Those
are the choices that end up in a postmortem — nobody writes *"we should not have used a cache"*.

```jsonc
{
  "scene": "url-shortener",        // must match the scene's id
  "decisions": [
    {
      "id": "shard-key",
      "v": 6,                       // the version where this is decided
      "parameter": "Shard key",
      "question": "You are sharding. What do you shard on?",
      "reversibility": "one-way",   // cheap | costly | one-way
      "reversal": "Re-sharding on a different key means every row moves…",
      "options": [
        { "value": "hash(short_code)", "verdict": "correct",    "because": "…" },
        { "value": "user_id",          "verdict": "wrong",      "because": "…" },
        { "value": "region",           "verdict": "defensible", "because": "…" }
      ]
    }
  ]
}
```

**`reversibility` is the field that earns this file its place.** A TTL is a config change and a
shard key is a migration; an engineer who knows which is which can decide the cheap ones fast and
spend the argument on the expensive ones. Exactly one option is `correct`, and `defensible` exists
because real parameter choices are not binary — marking a reasonable-but-suboptimal answer simply
"wrong" would teach that design has one right answer.

### Why it is a separate file

Every scene is imported into the app's **main** bundle, because the default view renders one
immediately. The decision prose is 33 KB that only the lazily-loaded studio reads — while it lived
inside the scene it cost every visitor 10.7 KB gzipped on the critical path for bytes the first
screen never touches. Splitting the file moves it into the chunk that uses it.

---

## Validation

`python scripts/check_scenes.py` enforces:

- every `active` and `edges` id exists in `nodes`
- every `flows[].path` hop is active in every version at or above `minVersion`
- every `bottleneck` refers to an active node
- versions are ordered and `v` is unique
- every node in `nodes` is used by at least one version — no dead declarations
- each scene has a `decisions/` file naming it, with **exactly one** `correct` option per
  decision, a known `reversibility`, three or more options, and a real explanation on each —
  a stub tells a reader they were wrong without saying why, which is worse than not asking

`npm run check:decisions` additionally walks the studio's own path to prove every authored decision
is **reachable**. Decisions belong to versions and briefs cover the transitions between them, so a
decision can be authored, pass every shape check, and be shown to nobody — three of the first
twenty-four were.

`python scripts/render_diagrams.py --check` additionally fails when a committed SVG is stale
relative to its scene, so the markdown can never quietly disagree with the data.
