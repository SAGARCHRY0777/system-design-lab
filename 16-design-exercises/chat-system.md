---
topic: Chat System — parameter decisions
category: Design exercise
difficulty: Advanced
---

# Chat System — parameter decisions

4 decisions taken while building [Chat System](../15-real-world-problems/chat-system/). Not *which component* — that is the other exercise. These are the values you set once the component is there, which is the half that ends up in the postmortem.

**Commit to an answer before opening the box.** A parameter question you read the answer to teaches nothing; the correction only lands if there was a prediction for it to contradict.

Of these 4: **1 is a one-way door**, 1 is costly to reverse, 2 are config. Sort your design argument accordingly.

---

## 1. Connection registry entry lifetime

> **Reversible** — A config change. Get it wrong, notice, fix it the same day.

**At V3** (200K online · two gateways): A second gateway was added and half the messages vanished. The sender's gateway had no idea which machine held the recipient's socket, so it delivered to nobody.

<img src="../19-diagrams/generated/chat-system-v3.svg" alt="Chat System at version 3: 200K online · two gateways" width="740">

**The registry maps user to gateway. How does an entry go away?**

- Deleted when the gateway sees a clean disconnect
- A ~30 second TTL, refreshed by heartbeat
- A 5 minute TTL, refreshed by heartbeat

<details>
<summary>Commit to one, then open this</summary>

**Deleted when the gateway sees a clean disconnect** — **No.** Gateways do not always get to say goodbye. A process killed by the OOM killer, a severed network link or a hard crash leaves its entries behind forever, and every message for those users is routed to a machine that no longer exists. Cleanup that only runs on the happy path is not cleanup.

**A ~30 second TTL, refreshed by heartbeat** — **Correct.** Liveness becomes something continuously proven rather than assumed. A dead gateway's entries drain within one TTL with nobody having to notice it died — which matters at V8, where a gateway holding 25,000 sockets disappears.

**A 5 minute TTL, refreshed by heartbeat** — **No.** Right mechanism, wrong constant. After a crash you black-hole messages for up to five minutes — an eternity in a chat product, and long enough that users conclude the app is broken.

**If you need to change your mind:** A TTL value and a heartbeat interval, both configuration. The reason to think about it carefully anyway is that the failure is invisible from the inside: a stale registry entry produces no error, no retry and no alert. Messages are routed to a machine that is not there, and the only signal is a user saying nobody replied.

</details>

---

## 2. Delivery guarantee

> **Costly to reverse** — Reversing this means changing code that already depends on it, or repairing data written under the old assumption.

**At V5** (600K online · offline delivery): Most recipients are not connected. A message published to a bus with nobody listening is a message deleted, and that is what was happening to every message sent to a sleeping phone.

<img src="../19-diagrams/generated/chat-system-v5.svg" alt="Chat System at version 5: 600K online · offline delivery" width="740">

**The recipient is offline and the push provider might time out. What guarantee?**

- At-most-once — try to deliver, do not retry
- At-least-once, deduplicated on the client by message ID
- Exactly-once delivery to the device

<details>
<summary>Commit to one, then open this</summary>

**At-most-once — try to deliver, do not retry** — **No.** A dropped message in a chat product is the single failure users will not forgive, because they cannot tell it from being ignored by the person they were talking to.

**At-least-once, deduplicated on the client by message ID** — **Correct.** Retries are safe because the client discards an ID it has already rendered. You accept a duplicate on the wire in exchange for never losing a message, and you pay for it in one place.

**Exactly-once delivery to the device** — **No.** Unachievable to a mobile client that can lose power between receiving bytes and rendering them. Every real system claiming it is doing at-least-once plus dedupe — choosing this option means not building the dedupe you nevertheless need.

**If you need to change your mind:** Tightening the guarantee later means adding a dedupe path to every client and every consumer, and shipping it to mobile apps you do not control the update cycle of.

</details>

---

## 3. Message ordering key

> **One-way door** — You do not get to change your mind. Reversing it is a migration measured in months, or it is simply not possible.

**At V6** (800K online · order and receipts): Two messages sent 30 ms apart arrived in the opposite order on one device and the right order on another. Nobody could tell whether a message had been read, or by whom.

<img src="../19-diagrams/generated/chat-system-v6.svg" alt="Chat System at version 6: 800K online · order and receipts" width="740">

**Two messages 30 ms apart arrived in different orders on different devices. What orders them?**

- Server wall-clock timestamp
- A per-conversation monotonic sequence number
- Client timestamp — the sender knows when they sent it
- UUIDv4 message IDs, sorted by ID

<details>
<summary>Commit to one, then open this</summary>

**Server wall-clock timestamp** — **No.** This is the V6 bug. The two messages were stamped by two different gateways whose clocks disagree by more than 30 ms, which is entirely normal. NTP bounds skew, it does not eliminate it, and no amount of clock discipline makes wall time a total order across machines.

**A per-conversation monotonic sequence number** — **Correct.** Order is assigned by one authority per conversation, so it is total and unambiguous by construction rather than by luck. The scope matters: per-conversation keeps the assigning authority small, where a global sequence would be a system-wide bottleneck.

**Client timestamp — the sender knows when they sent it** — **No.** Client clocks are worse than server clocks and are also under the user's control. Anyone can set their phone forward and pin their messages to the top of everyone's conversation.

**UUIDv4 message IDs, sorted by ID** — **No.** Random IDs carry no order at all. This sorts messages into a stable, consistent and completely meaningless sequence.

**If you need to change your mind:** Every message already stored carries the old key. Changing it means every client's sort logic must handle both schemes, forever, because old messages never get rewritten.

</details>

---

## 4. Presence propagation

> **Reversible** — A config change. Get it wrong, notice, fix it the same day.

**At V7** (1M online · presence): Presence was the cheapest-looking item on the roadmap. With 1M connections and 200 contacts each, one person going online is 200 notifications — and people go online about 40 times a day.

<img src="../19-diagrams/generated/chat-system-v7.svg" alt="Chat System at version 7: 1M online · presence" width="740">

**1M users, 200 contacts each. How does an online/offline change reach contacts?**

- Push every change to all 200 contacts immediately
- Subscribe only to the contacts in the conversation currently open
- Batch changes and broadcast a digest every 60 seconds

<details>
<summary>Commit to one, then open this</summary>

**Push every change to all 200 contacts immediately** — **No.** Do the arithmetic before building it. A user toggling state every 30 seconds across 1M users at 200 contacts each is roughly 1.6M events per second — over a hundred times the entire message path of the product. The cheapest-looking feature on the roadmap was the most expensive thing in the system.

**Subscribe only to the contacts in the conversation currently open** — **Correct.** Collapses the fan-out to what a user can actually see, which is a handful of people rather than 200. The realisation is that presence for someone you are not looking at has no value, so it should not be computed.

**Batch changes and broadcast a digest every 60 seconds** — **Defensible.** Cuts the event rate by orders of magnitude and is simple to reason about. The cost is that presence is now up to a minute stale, which makes 'is this person there right now' — the entire point of the feature — unreliable.

**If you need to change your mind:** Presence is soft state that rebuilds itself continuously. You can change the propagation model on a Tuesday afternoon.

</details>

---

## Related

- [Chat System — the full design](../15-real-world-problems/chat-system/)
- [All parameter decisions](README.md)
- [Trade-off framework](../TRADEOFF-FRAMEWORK.md)
