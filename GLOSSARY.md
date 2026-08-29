---
topic: Glossary
category: Reference
difficulty: Beginner
---

# Glossary

The hub of the cross-link graph. A term is defined here in one or two sentences and linked to its
full treatment — a concept is explained **once** and referenced everywhere else.

Where a link points at a directory, that topic is not yet written; the definition below still holds.

---

### Availability
The fraction of time a system responds successfully. Quoted in nines: 99.9% is ~8.8 h of downtime a
year, 99.99% is ~53 min. Each additional nine costs roughly an order of magnitude more.
→ [00-foundations/availability/](00-foundations/availability/)

### Backpressure
A signal from an overloaded consumer telling producers to slow down. Without it a queue absorbs load
until it runs out of memory, which converts a slowdown into an outage.
→ [06-messaging/queues/](06-messaging/queues/)

### Batching
Grouping many operations into one round trip. Raises **throughput**, raises **latency** for the first
item in the batch. The clearest example of two goals in direct opposition.
### Bottleneck
The single component that saturates first. Every scaling step is: find it, fix it, find the next one.
Fixing anything else changes nothing. → [SYSTEM-DESIGN-THINKING.md](SYSTEM-DESIGN-THINKING.md)

### Bearer token
A credential where possession is sufficient — anyone holding it can use it. Which is why transport
security and short lifetimes matter more than token format.
→ [12-security/jwt/](12-security/jwt/)

### IDOR / BOLA
Checking authorization on the *endpoint* but not on the *object*, so changing an id in the URL
returns someone else's data. The most common real API vulnerability.
→ [12-security/api-security/](12-security/api-security/)

### Cache
A faster, smaller copy of data kept nearer the reader. Buys latency, sells **staleness**. Worth having
only when access is **skewed** — a cache over uniformly random reads hits almost never.
→ [04-caching/fundamentals/](04-caching/fundamentals/)

### Cache invalidation
Deciding when a cached copy is no longer true. Genuinely one of the hardest problems in the field,
because the cache has no way to know the source changed unless something tells it.
→ [04-caching/fundamentals/](04-caching/fundamentals/)

### CAP theorem
Under a network **partition** you must choose availability or consistency. It says nothing about
normal operation — which is why [PACELC](#pacelc) exists. Widely misquoted as "pick two of three".
→ [00-foundations/cap-theorem/](00-foundations/cap-theorem/)

### CDN
Caches placed physically near users. The only fix for the speed of light, which no amount of hardware
addresses.
### Circuit breaker
Stops calling a failing dependency for a cooling-off period. Without one, retries pile onto a
struggling service and finish it off.
→ [00-foundations/reliability/](00-foundations/reliability/)

### Consensus
Getting a group of nodes to agree on one value despite failures. Raft and Paxos. Expensive; use a
system that already implements it rather than writing your own. `[E]`

### Consistency
Whether all readers see the same data at the same time. **Strong**: every read sees the latest write.
**Eventual**: reads converge, given time. Neither is better — they are priced differently.
→ [00-foundations/consistency/](00-foundations/consistency/)

### Durability
Once the system says "saved", the data survives crashes. Distinct from availability: a system can be
down but durable, or up and losing writes.
→ [00-foundations/reliability/](00-foundations/reliability/)

### Eventual consistency
Replicas converge if writes stop. "Eventually" without a stated bound is not a design — say
*how* eventual, and who notices.
→ [00-foundations/consistency/](00-foundations/consistency/)

### Fan-out
One event producing many writes or messages. Writing a post to 10M followers' feeds is fan-out on
write; assembling the feed at read time is fan-out on read. The choice defines a social feed's
architecture.
### Hot key
One key receiving a disproportionate share of traffic. Defeats sharding, because hashing spreads
*keys* evenly, not *load*.
→ [05-databases/sharding/](05-databases/sharding/)

### Idempotency
Doing the operation twice has the same effect as once. **Mandatory wherever you retry** — and you
always end up retrying.
→ [07-api-design/idempotency/](07-api-design/idempotency/)

### Cursor pagination
Paging by an opaque pointer to the last row seen, rather than by offset. Exists because **offset
pagination silently skips and duplicates rows** when the data changes mid-traversal.
→ [07-api-design/pagination/](07-api-design/pagination/)

### Distributed monolith
Services that must be deployed together, with network failure between them. The worst of both
architectures, and the usual result of splitting a monolith along the wrong seams.
→ [02-architecture/monolith-vs-microservices/](02-architecture/monolith-vs-microservices/)

### Latency
Time for one operation. Always quote **p99**, not the average: the average hides the experience of
your least happy users, and at scale a 1% tail is a lot of people.
→ [00-foundations/latency/](00-foundations/latency/)

### Load balancer
Spreads requests across servers. Also buys zero-downtime deploys, which is usually the benefit that
actually forces the change. Make it redundant, or it becomes the single point of failure it was meant
to remove.
→ [03-load-balancing/fundamentals/](03-load-balancing/fundamentals/)

### Partition (data)
Splitting a dataset into pieces. See [sharding](#sharding) for splitting it across *machines*.
→ [05-databases/fundamentals/](05-databases/fundamentals/)

### Partition (network)
A break that stops nodes communicating while both remain alive. The **P** in CAP, and the reason the
theorem matters.
→ [00-foundations/cap-theorem/](00-foundations/cap-theorem/)

### PACELC
The completion of CAP: if **P**artitioned, choose **A** or **C**; **E**lse, choose **L**atency or
**C**onsistency. The second half describes normal operation, which is where systems spend all their
time.
→ [00-foundations/cap-theorem/](00-foundations/cap-theorem/)

### Quorum
A majority agreeing before an operation counts. With `R + W > N`, reads and writes overlap on at
least one node, so a read cannot miss the latest write. `[A]`

### Rate limiting
Capping how much a client may consume. Protects you from one caller, whether hostile or merely
buggy.
→ [18-implementations/rate-limiter/](18-implementations/rate-limiter/)

### Read replica
A copy serving reads only. Scales reads, introduces **replication lag** — so a user can write and
then not see their own write.
→ [05-databases/replication/](05-databases/replication/)

### Replication
Keeping copies of data on multiple machines, for availability and read scale.
→ [05-databases/replication/](05-databases/replication/)

### Retry storm
Every client retrying a struggling service simultaneously, guaranteeing it stays down. Prevented by
backoff, **jitter**, and a circuit breaker.
→ [00-foundations/reliability/](00-foundations/reliability/)

### Sharding
Splitting data across machines by a key. Buys write scale and unbounded storage. Sells cross-shard
joins, and the shard key is close to permanent — choose it slowly.
→ [05-databases/sharding/](05-databases/sharding/)

### Split brain
A partition leaves two halves each believing it is in charge, both accepting writes. Resolving the
divergence afterwards is often impossible. `[A]`

### Tail latency
The slow end of the distribution — p99, p99.9. At scale it dominates user experience, because a
request touching 100 services hits *someone's* p99 almost every time.
→ [00-foundations/latency/](00-foundations/latency/)

### Throughput
Operations per second. Not the inverse of latency — batching improves throughput while making latency
worse.
→ [00-foundations/throughput/](00-foundations/throughput/)

### Thundering herd
A cached key expires and every waiting request hits the database at once. The most common way a cache
outage becomes a full outage.
→ [04-caching/fundamentals/](04-caching/fundamentals/)

### Timeout
A cap on how long you wait. **Slow is worse than down**: a dead dependency fails fast and you route
around it; a slow one holds every thread that touches it.
→ [00-foundations/reliability/](00-foundations/reliability/)

---

## Related

- [System Design Thinking](SYSTEM-DESIGN-THINKING.md) · [Trade-off Framework](TRADEOFF-FRAMEWORK.md)
- [Estimation Guide](ESTIMATION-GUIDE.md) · [Design Checklist](DESIGN-CHECKLIST.md)
- [Concept dependency graph](19-diagrams/concept-dependency-graph.mmd) — the order to learn these in
