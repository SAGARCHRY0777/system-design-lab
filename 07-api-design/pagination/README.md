---
topic: Pagination
category: API Design
difficulty: Intermediate
concepts: [traversal, consistency, indexing, cursors]
related: [rest-grpc-graphql, versioning, database, latency]
---

# Pagination

`[INTERMEDIATE]` · **Offset pagination silently skips and duplicates rows** whenever the underlying list changes mid-traversal. It is the default in every ORM, it passes every test you will write, and it is wrong in production.

---

## 1. One-line definition

Returning a large result set as a sequence of bounded responses, together with enough state for the
caller to ask for the next one.

## 2. Explain like I'm new

There are ten thousand results and you can only send twenty at a time. So you send twenty, and the
caller comes back for the next twenty. The only question is **how you remember where they were**, and
there are exactly two answers.

You can remember a **position**: "you had the first twenty, so now give them rows 21 to 40." Simple,
obvious, and the one everybody writes first.

Or you can remember a **place**: "you stopped just after the row with this timestamp and this ID, so
give them the next twenty after that."

Those sound equivalent. They are not, and the difference is the entire page. If someone adds a row to
the top of the list between the two requests, everything shifts down by one — so "rows 21 to 40" now
covers what used to be rows 20 to 39, and the caller sees row 20 for a second time. If someone
deletes a row instead, everything shifts up, and the caller **never sees** one row at all. It is not
reported as an error. Nothing logs anything. The caller simply gets a list with a gap in it.

## 3. Real-world analogy

Reading a long noticeboard by counting: "I read the first twenty notices; tomorrow I start at number
twenty-one."

**Where it breaks:** a noticeboard analogy suggests you would *notice*. In a real reading you would
see the same notice twice and think "hold on, I have read that". An API caller has no such
recognition — it receives a list, appends it, and moves on. **The corruption is invisible to both
ends**: the server did exactly what it was asked, the client got a valid response, and the resulting
data is wrong with nothing anywhere to indicate it. That silence is why this page exists.

## 4. Technical explanation

### The demonstration

A feed, ordered newest first, page size 3. Two traversals, one with an insert and one with a delete
happening between page 1 and page 2.

```
CASE 1 — a row is inserted at the head between requests   (duplicate)

  before page 1            after the insert, at page 2
  ───────────────          ────────────────────────────
  0  I  ← page 1           0  J   (new)
  1  H  ← page 1           1  I
  2  G  ← page 1           2  H
  3  F                     3  G   ← OFFSET 3 lands here  ← page 2
  4  E                     4  F                          ← page 2
  5  D                     5  E                          ← page 2

  client received:  I H G   then   G F E
                                   ↑ G delivered twice


CASE 2 — a row above the window is deleted                (skip)

  before page 1            after deleting I, at page 2
  ───────────────          ───────────────────────────
  0  J  ← page 1           0  J
  1  I  ← page 1           1  H
  2  H  ← page 1           2  G
  3  G                     3  F   ← OFFSET 3 lands here  ← page 2
  4  F                     4  E                          ← page 2
  5  E                     5  D                          ← page 2

  client received:  J I H   then   F E D
                                   ↑ G never delivered, ever
```

That is the whole bug. `OFFSET n` means "discard the first n rows of the result **as it exists right
now**", and the result as it exists right now is not the result the caller was traversing. An offset
is a position in a list that is allowed to move underneath it.

**The bug is invisible in testing because test data does not move.** Your fixtures are inserted
before the test and unchanged during it, so offsets are stable and every page is correct. There is no
assertion you can write against a static dataset that catches this. It appears only under
concurrency, in production, on exactly the endpoints where it matters most — feeds, activity logs,
inboxes, anything ordered by recency, where insertion at the head is not an edge case but **the
normal operating mode**. The busier the list, the more rows are lost.

And it is worse for delete than for insert. A duplicate is at least *visible* to a client that
de-duplicates by ID. A skipped row is gone: the caller finishes the traversal believing it has seen
everything, and there is no signal — not a count mismatch, not an error, nothing — to say otherwise.
If that traversal was a data export, a reconciliation job, or a sync to another system, you now have
silent data loss with a clean success log.

### The second problem: offset does not scale

Independently of correctness, `OFFSET` is **O(offset)**, not O(limit). The database cannot jump to
row 100,000; it must produce and discard the preceding 100,000 rows, every time.

| Request | Rows the engine must produce | Rows returned |
|---|---|---|
| `LIMIT 20 OFFSET 0` | 20 | 20 |
| `LIMIT 20 OFFSET 1 000` | 1 020 | 20 |
| `LIMIT 20 OFFSET 100 000` | 100 020 | 20 |
| `LIMIT 20 OFFSET 1 000 000` | 1 000 020 | 20 |

The cost per page **grows as the user goes deeper**, which is the opposite of what any user expects
and the opposite of what you want — the further in they are, the more invested they are. A crawler
walking to page 50,000 does not need to be malicious to take your database down; it merely needs to
be thorough. Keyset pagination is a constant-cost index seek per page regardless of depth.

### Cursor (keyset) pagination

Remember the *place*, not the position. Instead of "skip 20", say "give me rows ordered after this
exact point":

```sql
-- page 1
SELECT ... FROM feed
 WHERE user_id = ?
 ORDER BY created_at DESC, id DESC
 LIMIT 20;

-- page 2 — anchored on the last row of page 1
SELECT ... FROM feed
 WHERE user_id = ?
   AND (created_at, id) < (:last_created_at, :last_id)
 ORDER BY created_at DESC, id DESC
 LIMIT 20;
```

Three properties follow, and they are the reasons to do this:

- **Inserts at the head do not affect it.** New rows sort above the anchor and are simply not part of
  this traversal — which is the correct behaviour for "continue where I was". The client polls the
  head separately if it wants new items.
- **Deletions do not shift anything.** The comparison is on *values*, not on row positions. This also
  means the anchor row itself may be deleted and the traversal still works perfectly — which is
  precisely why the cursor must encode the sort values rather than a reference to a row.
- **Cost is constant per page.** With an index on `(user_id, created_at DESC, id DESC)` it is a seek
  plus a scan of 20 rows, whether it is page 2 or page 20,000.

The tie-break column is not optional. `ORDER BY created_at DESC` alone is not a total order: two rows
with identical timestamps have no defined relative position, so one of them can appear on both pages
or on neither. **Always append a unique column to the sort and to the comparison** — the composite
`(created_at, id)` comparison above is doing real work, and writing it as two separate `AND`
conditions with `>=` and `>` is where people introduce off-by-one duplicates. Use row-value
comparison where your database supports it.

## 5. Engineering at scale

**The index must match the sort, exactly, including direction.** Keyset pagination's constant cost is
entirely a property of the index; without a matching composite index, the "efficient" query becomes a
sort of the whole partition and you have kept all of offset's cost while losing page numbers. Check
the plan, not the query text. See [databases](../../05-databases/fundamentals/#10-indexing) — the
leftmost-prefix rule decides whether your cursor index is used at all.

**Make cursors opaque, and put the query shape inside them.** Base64 a small structure containing the
sort values, the sort direction, and a fingerprint of the filters. Two reasons, both learned the hard
way:

1. If the cursor is a readable `created_at` value, callers will construct their own, and then the
   cursor format becomes a public contract you can never change — [Hyrum's Law](../versioning/)
   again.
2. If the cursor does not carry the query shape, a caller can pass a cursor from one filter into a
   request with a different filter or sort. The result is not an error; it is a traversal that
   quietly returns nonsense. Compare the fingerprint and reject the mismatch with a 400.

**Cap the page size at the API, always.** `limit` is caller-controlled input to a resource decision.
A default of 20, a hard maximum of 100, and a rejection rather than a silent clamp above it — a
silent clamp means the caller's loop terminates early and believes it read everything. This is the
same class of bug as the skip.

**`SELECT COUNT(*)` is the second-most-common pagination outage.** A total count over a filtered set
is a full scan of the matching rows; it is frequently more expensive than the page itself, and it
gets slower as the table grows while the page cost stays flat. The options, in order of preference:
do not return a count at all (most UIs do not need one, they need "is there more"); return an
approximate count from statistics; return a capped count (`"1000+"`) computed with `LIMIT 1001`; or
compute the exact count asynchronously and cache it. A `hasMore` boolean — obtained by fetching
`limit + 1` rows and discarding the extra — costs nothing and answers the question the UI actually
asks.

**Deep pagination is usually a symptom.** A caller on page 4,000 does not want page 4,000; they want
either a search, a filter, or a bulk export. All three are better served by something other than
pagination — a query, a narrower filter, or a file in an object store with a signed URL. A hard depth
cap on offset endpoints ("results beyond 10,000 require a narrower filter") is a legitimate and
common answer.

**In a [sharded](../../05-databases/sharding/) or fan-out system, pagination gets harder in a
specific way**: a global ordering across shards means each shard must return its top-N, and a
coordinator merges them. Offset across shards is close to unworkable — `OFFSET 1000` means fetching
1,000 rows from *every* shard — while keyset merges cleanly because each shard can be asked for "the
next 20 after this sort value". This is one of the clearest cases where the naive approach does not
merely get slower, it stops being feasible.

## 6. The problem it solves

Returning a result set that does not fit in one response, or that the caller does not want all of —
bounding response size, memory, and latency, and giving the client a way to stream through a large
list incrementally.

## 7. The problem it does NOT solve

**Cursor pagination fixes shifting positions. It does not fix changing sort values.** If you paginate
by a mutable column — `updated_at`, a relevance score, a vote count — a row can move across the
cursor boundary while you traverse, and it will be seen twice or never, exactly as with offset. The
cursor is correct with respect to the ordering; the ordering itself moved. **Paginate on an immutable
key wherever you can** (`created_at`, `id`, a sequence number). If the sort must be mutable, you need
a genuine snapshot: a point-in-time consistent read, or a filter that freezes the set
(`WHERE created_at <= :request_started_at`) so at least the *membership* is stable.

It also does not give you:

- **A consistent view of the whole list.** Pagination is many separate reads. Nothing spans them
  unless you deliberately add something — see [consistency](../../00-foundations/consistency/).
- **Page numbers, or jumping to page 7.** Keyset is inherently sequential. If the product genuinely
  requires numbered pages, you need offset, or a hybrid, and you should know why.
- **A free total count.** Neither scheme makes counting cheap; cursors merely stop pretending it is.
- **Protection from an expensive query.** A cursor over a query with no usable index is still a full
  scan, just a repeated one.

---

## 9. How it works

| | **Offset** | **Cursor / keyset** |
|---|---|---|
| Request | `?limit=20&offset=40` | `?limit=20&after=eyJ0IjoiMjAy…` |
| Query | `LIMIT 20 OFFSET 40` | `WHERE (sort, id) < (:v, :id) LIMIT 20` |
| State lives | In the client's page number | In the cursor, which encodes the last row's sort values |
| Cost per page | **O(offset)** — grows with depth | O(log n) seek + limit — **constant** |
| Insert at head mid-traversal | **Duplicates a row** | Unaffected |
| Delete above the window | **Skips a row, silently** | Unaffected |
| Jump to page 7 | Yes | No |
| Total count | Available, and expensive | Not naturally available |
| Stable under mutable sort key | No | **No** — neither scheme survives this |
| Works across shards | Barely | Cleanly |
| Right for | Static or small result sets, admin tables, numbered UIs | **Feeds, logs, exports, APIs, anything that changes** |

The default, stated plainly: **use cursor pagination for any list that can change, which is most
lists.** Use offset only when the result set is effectively static for the duration of the traversal,
or small enough that a full scan is free, or when numbered pages are a genuine product requirement
you have consciously priced.

### Snapshot pagination — the third option

Where the traversal must be *complete and consistent* — an export, a reconciliation, a migration —
neither scheme is sufficient on its own, because both are defined only against the current state.
Freeze the membership instead:

```sql
WHERE created_at <= :request_started_at        -- membership frozen at traversal start
  AND (created_at, id) < (:cursor_t, :cursor_id)
ORDER BY created_at DESC, id DESC
LIMIT 20
```

Rows created after the traversal began are excluded from it entirely, and the traversal is
reproducible. This is the append-only case and it is common. For a mutable set you need the
database's own mechanism — a repeatable-read transaction held open (rarely acceptable: it blocks
vacuum and holds resources; see
[databases](../../05-databases/fundamentals/#19-failure-scenarios)), an explicit snapshot or
`AS OF SYSTEM TIME` read where the engine supports it, or a change-log-based sync rather than a
paginated read at all.

## 13. When to use it

**Use cursor pagination when:** the list can change during traversal (feeds, logs, inboxes, activity
streams); the result set is large; callers may go deep; the data is sharded; correctness of the
traversal matters — for exports, syncs and reconciliation it is not optional.

**Use offset pagination when:** the result set is genuinely static during traversal (a finished
report, an immutable archive); the total is small (a few hundred rows, where correctness risk and
scan cost are both negligible); or the UI requires numbered pages and the product has accepted the
duplicate/skip behaviour as a known cost.

**Add a snapshot filter when:** the traversal must be complete — anything whose output is compared
against another system.

## 14. When NOT to

- **Do not paginate a bulk export.** A caller pulling ten million rows through an API twenty at a
  time is doing 500,000 requests, will hit every rate limit you have, and will get an inconsistent
  result anyway. Give them a file in object storage and a signed URL.
- **Do not offer offset pagination on a public feed.** You are shipping the skip/duplicate bug to
  callers who will not understand why their data is wrong.
- **Do not paginate on a mutable sort key** without a snapshot — cursors do not save you.
- **Do not return a total count by default.** Make it opt-in, because most callers do not need it and
  all of them will pay for it.
- **Do not let the caller set an unbounded `limit`.** One request for a million rows is a
  self-inflicted outage.
- **Do not paginate at all when the answer fits in one response.** A list of a user's 5 addresses
  needs no cursor, no `hasMore`, and no page metadata.

## 17. Trade-offs

| Choose | Get | Pay |
|---|---|---|
| Offset | Page numbers, jump-to-page, total count, trivial to implement | **Silent skips and duplicates**; cost grows with depth |
| Cursor / keyset | Correct traversal; constant cost per page; shards cleanly | No page numbers; no natural total; needs a matching composite index |
| Opaque cursor | Free to change the format later; callers cannot forge one | Callers cannot construct a request by hand; harder to debug |
| Transparent cursor | Debuggable; a caller can resume from a known value | The format is now a public contract forever |
| Snapshot filter | Reproducible, complete traversal | Excludes new rows — correct for exports, wrong for feeds |
| Returning a total count | The UI can show "1 of 500" | A full scan on every page request |
| `hasMore` via `limit + 1` | Answers the real question for near-zero cost | You cannot show a total, only "there is more" |
| Small page size | Fast responses, bounded memory | More round trips — the mobile latency problem again |

## 18. Why not?

| Alternative | Why not here | When it WOULD win |
|---|---|---|
| **No pagination — return everything** | Unbounded response, unbounded memory, unbounded latency | **A genuinely bounded set.** Five addresses do not need a cursor |
| Offset | Skips and duplicates; deep pages scan the table | Static result sets, small tables, or a product that demands page numbers |
| Cursor | No page numbers or totals; more implementation care | **The default for anything that changes** |
| Time-window pagination (`?since=&until=`) | Uneven page sizes; needs a tie-break for bursts | Time-series and log APIs, where the caller thinks in time anyway |
| Streaming the response (chunked / gRPC stream) | Long-lived connection; no resumption if it drops | Server-to-server bulk reads within one trusted boundary |
| Change feed / CDC | Not a list read; requires infrastructure | **Continuous sync** — the correct answer whenever "paginate everything, repeatedly" is the plan |
| File export + object store URL | Not interactive; there is a delay | Bulk data movement, which is what the caller with `offset=2000000` actually wants |

The last two rows matter more than they look. **A large fraction of pagination pain is a bulk-data
problem being solved with a list endpoint.** If the caller's real goal is "keep a copy of everything
in sync", pagination is the wrong tool no matter how good your cursors are — they want a change feed
or an export, and giving them one removes the problem instead of managing it.

## 19. Failure scenarios

| Failure | What happens | Mitigation |
|---|---|---|
| **Insert during offset traversal** | A row is returned twice; the client's list has a duplicate | Cursor pagination |
| **Delete during offset traversal** | A row is **never returned**; no error, no signal, silent data loss | Cursor pagination |
| **Non-unique sort key** | Rows with equal sort values appear on two pages or on none — even with cursors | Always tie-break on a unique column, in the sort *and* the comparison |
| **Mutable sort key** | Rows cross the cursor boundary; duplicates and skips return | Paginate on an immutable key, or snapshot the traversal |
| Deep offset | `OFFSET 1000000` scans a million rows per request; one crawler saturates the database | Depth cap; cursors; a narrower filter |
| `COUNT(*)` on every page | The count costs more than the data, and worsens with table growth | `hasMore`, capped count, or approximate count |
| Unbounded `limit` | One request tries to serialise the table into memory | Hard cap, and reject rather than clamp |
| Cursor reused with different filters | Traversal returns coherent-looking nonsense | Encode a filter/sort fingerprint in the cursor; reject mismatches |
| Cursor format leaked and depended on | You can never change the encoding | Opaque, versioned cursors from day one |
| Client ignores `hasMore` and loops on page count | Infinite loop, or an early stop | Return an explicit terminal signal — a null `next` cursor |
| Index does not match the sort | Keyset query sorts the whole partition; all the cost, none of the benefit | Read the query plan; composite index matching sort order and direction |
| Retry of a page after a timeout | With offset, the underlying data may have moved between attempts | Cursors make the retry naturally idempotent — see [idempotency](../idempotency/) |

**The first two rows are the reason this page exists**, and neither of them produces an error, a log
line, or a metric. Every other row in this table announces itself. These two do not.

---

## 25. Without it → With it → New problem → Next

```
Without it   →  responses are unbounded; one query serialises a million rows into
                memory and the request times out or takes the process with it
With it      →  bounded responses, bounded memory, predictable latency; callers can
                walk a large result set incrementally
New problem  →  the traversal is now many separate reads with no consistency between
                them — so with offsets the list shifts underneath the caller and rows
                are silently duplicated or skipped
Next         →  cursor pagination anchored on an immutable, uniquely-ordered key, a
                composite index that matches the sort, and a snapshot filter wherever
                the traversal must be complete
```

Pagination is the clearest small example of the whole method: a fix creates a subtler problem than
the one it solved — see [the chain](../../SYSTEM-DESIGN-THINKING.md#part-1--the-chain).

## 28. Common mistakes

| Mistake | Why it is wrong |
|---|---|
| Offset pagination on a changing list | Silently skips and duplicates rows; no error is ever raised |
| Believing the tests prove it works | Test fixtures do not move. This bug is unreachable with static data |
| Sorting without a unique tie-break | Not a total order; equal-valued rows land on two pages or none |
| Paginating on `updated_at` or a score | A mutable sort key breaks cursors too — rows cross the boundary |
| `>=` and `>` as two conditions instead of a row-value comparison | Off-by-one duplicates at every page boundary |
| Exposing raw cursor contents | Callers construct their own; the format becomes permanent |
| Cursor without a filter fingerprint | A cursor from another query returns plausible nonsense |
| `SELECT COUNT(*)` on every page | Frequently costs more than the page and degrades with growth |
| No maximum `limit` | Caller-controlled memory allocation |
| Silently clamping an oversized `limit` | The client's loop terminates early believing it is done |
| No depth cap on offset endpoints | One thorough crawler is a denial of service |
| Paginating a bulk export | 500,000 requests, every rate limit, and an inconsistent result |
| Keyset query with no matching index | All the complexity of cursors, all the cost of offset |

## 29. Monitoring

The signal nobody has and everybody needs: **the distribution of requested offset depth**. If offset
endpoints exist, chart p99 offset — a rising tail is a crawler or a sync job, and it is the leading
indicator of the query that will take the database down.

Also: latency **per page position**, not aggregated — offset latency grows with depth, so an average
across page 1 and page 10,000 tells you nothing. Rows scanned per row returned, which is the direct
measure of pagination efficiency and should be near 1 for keyset. Requested page sizes, including
rejected ones. Cursor rejection rate (a spike means a client is mishandling cursors, or the format
changed under someone). And, for any endpoint with a total count, count-query time as its own metric,
because it will diverge from page latency and it is the half that scales badly. See
[observability](../../11-observability/).

## 31. Exercises

1. A nightly job pages through `/orders?limit=100&offset=N` to sync your order table into a data
   warehouse. It reports success every night. Finance says roughly 0.3% of orders are missing, and
   the ones missing are not correlated with anything obvious. Explain it, and give the fix.

<details><summary>Answer</summary>

Orders are being created and deleted (or cancelled out of the filtered set) while the job traverses.
Each row that leaves the set *above* the job's current offset shifts everything up by one, and the
next page skips exactly one row. Each insert above the window causes a duplicate, which the warehouse
load probably de-duplicates by primary key — so **only the skips survive as visible symptoms**, which
is why the loss looks one-directional and uncorrelated. The 0.3% is roughly a function of how much
the table churns during the job's runtime, so it will grow with order volume.

The job reports success because nothing failed: every request returned 200, every page had 100 rows,
the loop terminated normally.

Fix in two parts. Switch to keyset pagination on an immutable key — `(created_at, id)` — so shifts
above the cursor are irrelevant. Then add a snapshot filter, `WHERE created_at <= :job_start`, so the
traversal has a defined, reproducible membership and rows created mid-run are picked up by tomorrow's
run rather than landing unpredictably. Longer term, ask whether this should be a paginated read at
all: a change feed or CDC stream is the right shape for "keep a copy in sync", and it removes the
class of bug rather than avoiding one instance of it.
</details>

2. You switch a feed endpoint from offset to cursor pagination. A week later, users report seeing the
   same post twice — but only occasionally, and only on very active feeds. What did you miss?

<details><summary>Answer</summary>

Almost certainly a non-unique sort key. If the cursor is `created_at` alone and several posts share a
timestamp — which is common on active feeds, and near-guaranteed if the column has second
granularity or the rows are written in a batch — then `created_at < :cursor` excludes *all* rows at
that timestamp (dropping some) while `created_at <= :cursor` includes *all* of them again (duplicating
some). There is no correct choice, because the ordering is not total.

Fix: tie-break on a unique column and compare the pair as a unit —
`(created_at, id) < (:cursor_t, :cursor_id)` — with `ORDER BY created_at DESC, id DESC` and an index
that matches. Note that expressing this as `created_at <= :t AND (created_at < :t OR id < :id)` is
equivalent but is where off-by-one bugs get written; prefer the row-value form if your database
supports it.

The second candidate, if the sort key is genuinely unique: the feed is sorted by something mutable —
a score, a rank, `updated_at` — in which case rows move across the boundary and cursors do not help.
That needs an immutable sort key or a snapshot.
</details>

3. Product wants "Page 1 2 3 … 47" with a total count, on a table of 80 million rows with
   user-supplied filters. What do you tell them, and what do you build?

<details><summary>Answer</summary>

Tell them the two requirements have different prices and one of them is very high. Numbered pages
require offset (or an equivalent rank computation), which means deep pages scan proportionally to
depth, and the exact total requires counting every matching row on every request — a full scan of
the filtered set, which with arbitrary user filters cannot be pre-computed. On 80 million rows those
are not micro-optimisations, they are the difference between a page load and an incident.

What to build, in order of preference: infinite scroll or a "Load more" button with cursors and a
`hasMore` flag, which covers what most users are actually doing; if a total is genuinely needed,
show an **approximate** count from table statistics or a capped one ("1,000+" via `LIMIT 1001`); if
numbered pages survive that conversation, cap the depth ("refine your filter to see beyond page
100"), which is what every large search engine does and which nobody complains about because nobody
goes there.

Worth surfacing the underlying question: who actually goes to page 47? Almost always the answer is
"a crawler, and one person who is really looking for search". Build search.
</details>

4. Why is this bug essentially impossible to catch with unit or integration tests, and what test
   would catch it?

<details><summary>Answer</summary>

Because the bug is a function of *mutation between two requests*, and test data does not mutate
between two requests. A standard test inserts fixtures, requests page 1, requests page 2, asserts on
the contents — and passes, correctly, because the dataset was frozen throughout. There is no
assertion over a static dataset that can fail. Even property-based tests over pagination usually
generate a fixed dataset and then paginate it, which is the same blind spot with more effort.

A test that catches it must interleave writes with the traversal: request page 1, then insert a row
that sorts *above* the window, then request page 2, and assert that the union of pages contains each
row exactly once. Run the same shape with a delete above the window and assert that no row from the
original set is missing. Under offset both assertions fail immediately; under keyset both hold. It is
about fifteen lines and it is the only test in your suite that will ever exercise this.

The broader lesson generalises well beyond pagination: **a test suite where nothing changes
concurrently cannot find concurrency bugs**, and most of the expensive bugs in a distributed system
are in that category — see [consistency](../../00-foundations/consistency/).
</details>

5. Your cursors currently encode `{"created_at": …, "id": …}` as base64 and callers have started
   decoding and constructing their own to resume syncs. Is that a problem? What would you change?

<details><summary>Answer</summary>

Yes, and it is already a contract. Base64 is an encoding, not a boundary — once callers depend on the
structure you cannot change the sort key, add a filter fingerprint, switch to a compound key, or
migrate the underlying store without breaking them. That is Hyrum's Law arriving on schedule; see
[versioning](../versioning/).

There is a second, sharper problem: a hand-constructed cursor can be paired with *different* filters
than the one it came from. Your endpoint will happily apply that cursor's comparison against another
tenant's or another sort's query and return a coherent-looking page from the wrong result set — no
error, plausible data. If any of those filters are authorisation-relevant, the consequences are worse
than "wrong page".

Changes: version the cursor payload (`{"v":2,…}`) so you can evolve it; include a fingerprint of the
filter and sort parameters and reject any request whose parameters do not match; sign or encrypt the
payload so it cannot be forged or hand-edited; and document explicitly that cursors are opaque and
must be echoed back verbatim. Existing callers must be migrated with the normal deprecation process —
you cannot simply change it now, which is exactly the cost of having shipped it transparently.
</details>

## 33. Related

- [Databases](../../05-databases/fundamentals/) — the index decides whether a cursor is fast or a lie
- [Sharding](../../05-databases/sharding/) — offset across shards is close to unworkable; keyset merges cleanly
- [Consistency](../../00-foundations/consistency/) — a traversal is many reads, and nothing spans them by default
- [Idempotency](../idempotency/) — a retried page must return the same page
- [Versioning](../versioning/) — a change of default ordering is a breaking change
- [REST vs gRPC vs GraphQL](../rest-grpc-graphql/) — the connection spec is a convention, not an implementation
- [Latency](../../00-foundations/latency/) — page size is a round-trip trade
- [Observability](../../11-observability/) — offset depth distribution is the metric nobody collects
- [Glossary](../../GLOSSARY.md) · [Combination matrix](../../14-component-combinations/MATRIX.md)
- [API design index](../README.md)
