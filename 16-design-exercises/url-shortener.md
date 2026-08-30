---
topic: URL Shortener — parameter decisions
category: Design exercise
difficulty: Advanced
---

# URL Shortener — parameter decisions

4 decisions taken while building [URL Shortener](../15-real-world-problems/url-shortener/). Not *which component* — that is the other exercise. These are the values you set once the component is there, which is the half that ends up in the postmortem.

**Commit to an answer before opening the box.** A parameter question you read the answer to teaches nothing; the correction only lands if there was a prediction for it to contradict.

Of these 4: **2 are one-way doors**, 1 is costly to reverse, 1 is config. Sort your design argument accordingly.

---

## 1. Short code length

> **One-way door** — You do not get to change your mind. Reversing it is a migration measured in months, or it is simply not possible.

**At V1** (10K req/day): Launch. One box, one database, no traffic worth planning for.

**Codes are base62. How many characters?**

- 4 characters (~14.8M codes)
- 7 characters (~3.5 trillion codes)
- A base62-encoded auto-increment integer
- A full UUID (36 characters)

<details>
<summary>Commit to one, then open this</summary>

**4 characters (~14.8M codes)** — **No.** 62^4 is 14,776,336. At the 1B requests/day this system reaches, even a 0.1% write ratio exhausts the whole keyspace in under two weeks. You then face the one migration you cannot perform.

**7 characters (~3.5 trillion codes)** — **Correct.** 62^7 is 3,521,614,606,208. At a million new links a day that is 9,600 years of keyspace, and it stays short enough to read aloud. Buying four orders of magnitude of headroom costs three characters.

**A base62-encoded auto-increment integer** — **Defensible.** It works and it guarantees uniqueness without a collision check, which is genuinely attractive. The cost is that codes are enumerable: anyone can walk your entire link database, and the difference between two codes tells a competitor your exact signup rate. Correct for internal tools, wrong for a public service.

**A full UUID (36 characters)** — **No.** Collision-proof and completely self-defeating: the output is longer than most of the URLs being shortened. The product is brevity.

**If you need to change your mind:** Every code you have ever issued is a public URL that someone has pasted into a document, a tweet or a QR code on a printed poster. You can start issuing longer codes tomorrow, but you can never shorten or reissue the ones already out there. This is the most irreversible decision on the page and it is made on day one, at 10K requests a day, when it feels like it does not matter.

</details>

---

## 2. Cache TTL

> **Reversible** — A config change. Get it wrong, notice, fix it the same day.

**At V4** (200M req/day): p99 reached 800ms under peak. 92% of reads were for the top 0.1% of codes.

**The cache is read-through. What TTL do you set on an entry?**

- No expiry — the mapping never changes
- 1 hour
- 30 seconds

<details>
<summary>Commit to one, then open this</summary>

**No expiry — the mapping never changes** — **No.** The tempting answer, because a code-to-URL mapping really is immutable. But entries are not only invalidated by edits: a link that turns out to host malware has to stop redirecting NOW, and an entry with no TTL keeps serving it from every cache node until someone evicts it by hand. Also nothing ever reclaims memory for the long tail nobody clicks.

**1 hour** — **Correct.** Long enough that the hot 0.1% of codes essentially never expire under continuous traffic, short enough that a takedown propagates on its own within an hour without an explicit purge. The TTL is doing double duty as a safety net.

**30 seconds** — **No.** Buys freshness that an immutable mapping does not need, and pays for it in hit rate: every hot key re-fetches 120 times an hour across every node. You added a cache to take load off the database and then configured it to keep asking.

**If you need to change your mind:** A config change that takes effect within one TTL period. If you get this wrong you will know within an hour and fix it within two. Spend your design argument somewhere else.

</details>

---

## 3. Shard key

> **One-way door** — You do not get to change your mind. Reversing it is a migration measured in months, or it is simply not possible.

**At V6** (1B req/day): Write throughput and dataset size both exceeded what one primary could hold.

**You are sharding. What do you shard on?**

- user_id of whoever created the link
- hash(short_code)
- created_at, in date ranges
- Geographic region of the creator

<details>
<summary>Commit to one, then open this</summary>

**user_id of whoever created the link** — **No.** Look at the read path: a redirect request contains a short code and nothing else. It does not know who created the link, so it cannot compute the shard — every read becomes a scatter-gather across all N shards. The shard key must be derivable from what the hot request actually carries.

**hash(short_code)** — **Correct.** The redirect path knows the code, so one hash sends it to exactly one shard. Hashing also spreads writes evenly by construction, which is the other half of the V6 problem.

**created_at, in date ranges** — **No.** Every new link is written to the newest shard, so 100% of write traffic lands on one machine and the other N-1 sit idle. You have bought the operational cost of a sharded cluster and none of the write throughput. Range keys on a monotonic column always do this.

**Geographic region of the creator** — **Defensible.** Genuinely right for a data-residency requirement — if EU links must live in the EU, this is how. But it does not solve the V6 problem: regions are wildly uneven in size, so load is uneven, and a redirect still does not know the region from the code alone.

**If you need to change your mind:** Re-sharding on a different key means every row moves. In practice that is dual writes to both clusters, a backfill of the entire dataset, a consistency check and a cutover with a rollback plan — months of engineering during which you ship nothing else.

</details>

---

## 4. Cross-region replication

> **Costly to reverse** — Reversing this means changing code that already depends on it, or repairing data written under the old assumption.

**At V7** (1B/day, multi-region): EU traffic still crossed the Atlantic on every cache miss.

**US and EU each hold a copy. How do writes propagate?**

- Synchronous — a write is not acknowledged until both regions have it
- Asynchronous — acknowledge locally, replicate in the background
- No replication — each region owns its own links

<details>
<summary>Commit to one, then open this</summary>

**Synchronous — a write is not acknowledged until both regions have it** — **No.** A round trip between US and EU is roughly 80-150 ms of pure speed-of-light latency that no hardware removes. Every link creation now pays it, and worse, an EU outage stops US writes entirely: you have coupled the availability of two regions in exchange for consistency that redirects do not need.

**Asynchronous — acknowledge locally, replicate in the background** — **Correct.** Writes stay fast and the regions stay independently available. The cost is real and bounded: for ~200 ms after creation, a code can 404 in the other region. For a redirect that is acceptable. The tolerance is a property of the use case, not the technology — the same trade in the payment system would be indefensible.

**No replication — each region owns its own links** — **No.** Then a link created in the US simply does not exist in the EU, and short links are shared across exactly those borders. This breaks the product rather than the latency budget.

**If you need to change your mind:** Switching modes is a config and topology change rather than a data migration, but it changes the guarantees the application above it is already relying on. Anything written assuming synchronous replication breaks quietly when you loosen it.

</details>

---

## Related

- [URL Shortener — the full design](../15-real-world-problems/url-shortener/)
- [All parameter decisions](README.md)
- [Trade-off framework](../TRADEOFF-FRAMEWORK.md)
