---
topic: Social Feed — parameter decisions
category: Design exercise
difficulty: Advanced
---

# Social Feed — parameter decisions

4 decisions taken while building [Social Feed](../17-case-studies/). Not *which component* — that is the other exercise. These are the values you set once the component is there, which is the half that ends up in the postmortem.

**Commit to an answer before opening the box.** A parameter question you read the answer to teaches nothing; the correction only lands if there was a prediction for it to contradict.

Of these 4: **1 is a one-way door**, 1 is costly to reverse, 2 are config. Sort your design argument accordingly.

---

## 1. What a feed row stores

> **One-way door** — You do not get to change your mind. Reversing it is a migration measured in months, or it is simply not possible.

**At V3** (5M users): A user following 2,000 accounts needed a 2,000-way merge on every refresh. Read-time assembly does not scale with follow count.

**You are materialising feeds. What goes in each row?**

- The full post: text, author name, avatar URL, counts
- Post ID and timestamp only
- Post ID plus a denormalised copy of the author's display name

<details>
<summary>Commit to one, then open this</summary>

**The full post: text, author name, avatar URL, counts** — **No.** Denormalising looks faster because the read needs no join. Then someone edits a post or changes their display name, and you must find and rewrite every copy across millions of feeds. You have made a write-amplification problem out of a read optimisation.

**Post ID and timestamp only** — **Correct.** A feed row becomes ~16 bytes, so storing 800 of them per user is trivial, and edits and deletes are a single write to the post itself. The extra hydration lookup is a batch get from cache — the cheapest part of the request.

**Post ID plus a denormalised copy of the author's display name** — **Defensible.** A real and common compromise: it kills the most frequent hydration lookup. You are betting that display names change rarely enough that a lazy backfill is acceptable — usually true, and worth stating out loud as a bet rather than discovering later.

**If you need to change your mind:** Changing this means rewriting every materialised feed for every user — billions of rows — while continuing to serve reads from them.

</details>

---

## 2. Materialised feed length

> **Reversible** — A config change. Get it wrong, notice, fix it the same day.

**At V3** (5M users): A user following 2,000 accounts needed a 2,000-way merge on every refresh. Read-time assembly does not scale with follow count.

**How many entries do you keep in a user's precomputed feed?**

- Unbounded — keep everything ever fanned out
- About 800 entries
- 20 entries — exactly one screen

<details>
<summary>Commit to one, then open this</summary>

**Unbounded — keep everything ever fanned out** — **No.** Storage grows without limit for content nobody will ever scroll to. A user following 2,000 accounts accumulates millions of rows to serve a screen that shows twenty.

**About 800 entries** — **Correct.** Deep enough that essentially no real session scrolls past it, shallow enough to stay cheap. Past the end you fall back to read-time assembly, which is fine because almost nobody gets there.

**20 entries — exactly one screen** — **No.** Every user who scrolls twice falls through to the expensive read-time path, which is the thing the materialised feed exists to avoid. You kept the write cost and gave away the read benefit.

**If you need to change your mind:** A trim job and a config value. Raising or lowering it is a background task, not a migration.

</details>

---

## 3. Fan-out queue delivery guarantee

> **Costly to reverse** — Reversing this means changing code that already depends on it, or repairing data written under the old assumption.

**At V4** (20M users): Fan-out on write made posting slow: the author waited while the system wrote to thousands of feeds.

**A fan-out worker crashes halfway through a job. What did you configure?**

- At-least-once, with an idempotent feed insert
- At-most-once — acknowledge on receipt
- Exactly-once delivery

<details>
<summary>Commit to one, then open this</summary>

**At-least-once, with an idempotent feed insert** — **Correct.** The crash replays the job and the duplicate insert is a no-op because the row key is (user_id, post_id). Redelivery is something you design for once, in the consumer, and then never think about.

**At-most-once — acknowledge on receipt** — **No.** The crashed job is gone. Some followers never receive that post in their feed, there is no error anywhere, and no user reports it because nobody knows what they did not see. Silent data loss is the worst failure mode because it never gets fixed.

**Exactly-once delivery** — **No.** Not something a queue can give you across a process boundary. Systems advertising it are doing at-least-once plus deduplication, which is what you should build explicitly — believing the label means skipping the idempotency you still need.

**If you need to change your mind:** Moving from at-most-once to at-least-once forces every consumer to become idempotent. That is a change to the write path of every worker, not a queue setting.

</details>

---

## 4. Hybrid fan-out threshold

> **Reversible** — A config change. Get it wrong, notice, fix it the same day.

**At V6** (Hybrid fan-out): Neither strategy works alone: write fan-out dies on celebrities, read fan-out dies on high follow counts.

**Above what follower count do you stop fanning out on write?**

- 100 followers
- Around 10,000 followers
- 1,000,000 followers

<details>
<summary>Commit to one, then open this</summary>

**100 followers** — **No.** Almost every account is now read-time, so nearly every timeline request does a large fan-in merge. You have effectively reverted to V2 while keeping all the machinery of V4.

**Around 10,000 followers** — **Correct.** Puts well over 99% of accounts on the write path, where fan-out is cheap and reads are free, and confines read-time merging to the few thousand accounts where write fan-out would be catastrophic. The threshold sits where the two costs actually cross.

**1,000,000 followers** — **No.** An account with 900K followers still triggers 900K feed writes from one request. The queue backs up for everyone, including the ordinary users whose posts are stuck behind it.

**If you need to change your mind:** A number in a config file, applied to future posts. You can tune it weekly against real latency data, and you should.

</details>

---

## Related

- [Social Feed — the full design](../17-case-studies/)
- [All parameter decisions](README.md)
- [Trade-off framework](../TRADEOFF-FRAMEWORK.md)
