---
topic: Notification System — parameter decisions
category: Design exercise
difficulty: Advanced
---

# Notification System — parameter decisions

4 decisions taken while building [Notification System](../15-real-world-problems/notification-system/). Not *which component* — that is the other exercise. These are the values you set once the component is there, which is the half that ends up in the postmortem.

**Commit to an answer before opening the box.** A parameter question you read the answer to teaches nothing; the correction only lands if there was a prediction for it to contradict.

Of these 4: **0 are one-way doors**, 1 is costly to reverse, 3 are config. Sort your design argument accordingly.

---

## 1. Queue partition key

> **Costly to reverse** — Reversing this means changing code that already depends on it, or repairing data written under the old assumption.

**At V3** (20M users · three channels): Push and SMS arrived. They are not variations of email: SMS costs real money per message and is regulated, push tokens expire silently, and email is the only one where "accepted" means nothing at all.

**Three channels, 20M users. What do you partition the work queue on?**

- Channel — one partition each for email, push and SMS
- user_id
- Random — spread work as evenly as possible

<details>
<summary>Commit to one, then open this</summary>

**Channel — one partition each for email, push and SMS** — **No.** Three partitions means a parallelism ceiling of three, forever, no matter how many workers you run. Worse, the channels have wildly different volumes: the email partition is hours behind while the SMS partition sits idle, and no amount of scaling helps because the key decides the distribution.

**user_id** — **Correct.** Thousands of partitions, evenly loaded, and everything for one user lands in order on one partition — which is what makes the V6 rate limit and the V7 digest possible at all. Both need to reason about a single user's recent history.

**Random — spread work as evenly as possible** — **No.** Perfect balance and no per-user ordering, so two notifications for the same user race. It also makes per-user rate limiting a distributed coordination problem instead of a local one.

**If you need to change your mind:** Repartitioning a live queue means draining it or running old and new topologies side by side until the old one empties, while ordering guarantees are in flux.

</details>

---

## 2. Retry policy

> **Reversible** — A config change. Get it wrong, notice, fix it the same day.

**At V4** (50M users · the provider fails): The SMS provider returned 500s for twenty minutes. The workers retried immediately in a tight loop and turned a provider outage into a self-inflicted one.

**The SMS provider returns 500s for twenty minutes. How do workers retry?**

- Retry immediately, in a loop, until it succeeds
- Exponential backoff with jitter, ~6 attempts, then a dead-letter queue
- Fixed 1-second delay between attempts
- Retry forever with backoff, never give up

<details>
<summary>Commit to one, then open this</summary>

**Retry immediately, in a loop, until it succeeds** — **No.** This is the V4 incident. A provider returning errors is usually a provider under stress, and a tight retry loop is a denial of service aimed at the thing you need to recover. You also burn your own workers spinning on a call that cannot succeed.

**Exponential backoff with jitter, ~6 attempts, then a dead-letter queue** — **Correct.** Backoff gives the provider room to recover; jitter stops every worker retrying in the same instant and re-creating the spike; the attempt cap stops one poison message consuming a worker forever; and the DLQ keeps the failure inspectable instead of silent. Each clause is there because of a different failure.

**Fixed 1-second delay between attempts** — **No.** Better than no delay and still wrong, because every worker that failed at the same moment retries at the same moment. Without jitter you have built a synchronised wave that hits the recovering provider once a second.

**Retry forever with backoff, never give up** — **No.** A permanently invalid phone number is not going to start working. Backoff without a cap means the message stays in the system indefinitely, and eventually there are enough of them to occupy every worker.

**If you need to change your mind:** Worker configuration. Deploy and it takes effect on the next message.

</details>

---

## 3. Deduplication window

> **Reversible** — A config change. Get it wrong, notice, fix it the same day.

**At V5** (80M users · deduplication): A deploy replayed six hours of the event log. Every user received every notification a second time, at 03:00, and 40,000 of them turned notifications off permanently.

**A deploy replayed six hours of the event log. How long do you remember an event ID?**

- 5 minutes
- 24 hours, keyed on (user, event ID)
- Remember every event ID forever

<details>
<summary>Commit to one, then open this</summary>

**5 minutes** — **No.** Size the window against the incident you are defending against, not against normal operation. The replay covered six hours; a five-minute memory catches none of it and every user is woken at 03:00 anyway.

**24 hours, keyed on (user, event ID)** — **Correct.** Comfortably longer than any realistic replay or backfill window, and bounded so the store does not grow forever. Keying on the pair rather than the event alone means a genuine broadcast still reaches every user exactly once.

**Remember every event ID forever** — **No.** Unbounded growth in the hot path of every notification, to defend against a replay older than any you will ever perform. It also permanently suppresses legitimately recurring notifications that reuse an ID.

**If you need to change your mind:** A TTL on the dedupe store. Widening it costs memory and nothing else.

</details>

---

## 4. Rate limit scope

> **Reversible** — A config change. Get it wrong, notice, fix it the same day.

**At V6** (100M users · consent and budget): One busy comment thread sent a single user 140 push notifications in an hour. The system was nowhere near its own limits — the limit that matters is per user, not per system.

**One busy thread sent a single user 140 pushes in an hour. What do you limit?**

- Globally, across the whole system
- Per user, per channel
- Per event type

<details>
<summary>Commit to one, then open this</summary>

**Globally, across the whole system** — **No.** The system was nowhere near its global capacity during the incident, so a global limit would not have triggered. Meanwhile it punishes everyone during a legitimate spike. The limit must be scoped to the thing that was actually harmed: one person.

**Per user, per channel** — **Correct.** Matches where the damage occurs. Per-channel matters because the tolerances differ by an order of magnitude — twenty pushes an hour is obnoxious, twenty emails is a mail-client filter rule, and twenty SMS is a real bill and a regulatory problem.

**Per event type** — **No.** Comment notifications as a category were not misbehaving. One user was in one unusually active thread, and a per-type limit throttles that event type for every user on the platform to fix it.

**If you need to change your mind:** Configuration. The reason to think about it is that the wrong scope looks like it is working — the graph goes down — while the user experience does not change at all.

</details>

---

## Related

- [Notification System — the full design](../15-real-world-problems/notification-system/)
- [All parameter decisions](README.md)
- [Trade-off framework](../TRADEOFF-FRAMEWORK.md)
