---
topic: Capacity Estimation
category: Method
difficulty: Beginner
---

# Estimation Guide

The goal is an **order of magnitude**, fast, in your head. Whether a system needs 800 or 1,200 rps
almost never changes the design. Whether it needs 100 or 100,000 changes everything.

False precision is the failure mode here. "About 10K rps, call it 30K at peak" is a better answer
than "11,574.07 rps", because the second one implies a confidence you do not have and cannot have.

---

## 1. Numbers worth memorising

Round, deliberately. These are for arithmetic in your head, not for a capacity plan.

| Quantity | Use |
|---|---|
| 1 day | ~86,400 s → **round to 100,000** |
| 1 month | ~2.5M s |
| 1 year | ~31.5M s |
| 1M/day | **~12 rps** |
| 100M/day | ~1,200 rps |
| 1B/day | ~12,000 rps |

So: **divide daily requests by 100,000 to get rps.** 500M/day → 5,000 rps. That is the whole trick.

### Latency, roughly

Ratios matter; exact figures drift with hardware and are not worth memorising precisely.

| Operation | Order of magnitude |
|---|---|
| L1 cache reference | ~1 ns |
| Main memory reference | ~100 ns |
| SSD random read | ~100 µs |
| Round trip within a datacentre | ~0.5 ms |
| Disk seek (spinning) | ~10 ms |
| Round trip across a continent | ~50 ms |
| Round trip across the world | ~150 ms |

**The one that shapes architecture: memory is ~1,000× faster than SSD, and a cross-continent round
trip is ~100,000× slower than memory.** This is why caching works and why no amount of hardware fixes
a user in Sydney talking to a server in Virginia. The only fix for distance is to be closer.

### Sizes

| Thing | Rough size |
|---|---|
| UUID | 16 B |
| Timestamp | 8 B |
| Short URL code (7 chars) | 7 B |
| Tweet-length text | ~300 B |
| Typical DB row with indexes | ~1 KB |
| Compressed web page | ~100 KB |
| Photo | ~2 MB |
| Minute of 1080p video | ~50 MB |

---

## 2. The method

Five steps, in order.

**1. Daily volume.** Start from users, not requests. `DAU × actions per user per day`.

**2. Convert to rps.** Divide by 100,000.

**3. Apply a peak factor.** Traffic is never flat. **Peak ≈ 2–3× average** for a global consumer
service, and **5–10×** for anything with a schedule (ticket sales, sports, payroll). You must
provision for peak, so this number is the one that costs money.

**4. Split reads and writes.** Compute the ratio explicitly. It drives more decisions than the
absolute number.

**5. Storage = write rate × record size × retention.** Then multiply by replication factor, and add
30–50% for indexes and overhead.

---

## 3. Worked example — URL shortener

Matches the [live scene](19-diagrams/scenes/url-shortener.json) you can scrub in the visualizer.

**Given:** 100M new URLs per month, read:write ≈ 100:1, keep data 5 years.

**Writes**

```
100M/month ÷ 2.5M s  ≈  40 writes/sec
peak (×3)            ≈  120 writes/sec
```

**Reads**

```
40 × 100  =  4,000 reads/sec
peak      ≈  12,000 reads/sec
```

**Storage**

```
row = short code 7B + long URL ~200B + user 16B + timestamps 16B + overhead
    ≈ 500 B, call it 1 KB with indexes

5 years = 60 months × 100M = 6B rows
6B × 1 KB = 6 TB
× 3 (replication) = ~18 TB
```

**Cache sizing.** Assume the classic 80/20: roughly 20% of keys serve most reads. Cache one day of
hot reads:

```
4,000 reads/s × 86,400 s ≈ 350M reads/day
20% distinct hot keys, ~1 KB each  →  a few hundred GB
```

Too much for one node — which is precisely how you *derive* the need for a distributed cache rather
than asserting it. Cache the top 1% instead and you are at a few GB, which fits comfortably. Both are
defensible; state which you chose and why.

**Bandwidth**

```
reads: 12,000/s × 500 B ≈ 6 MB/s outbound at peak
```

Trivial. Worth computing precisely because it tells you bandwidth is *not* the constraint here — and
knowing what is *not* a bottleneck is as useful as knowing what is.

**What these numbers decided**

| Number | Consequence |
|---|---|
| 12,000 peak reads/s | One database will not serve this. Cache or replicas required. |
| 100:1 read:write | Caching pays enormously. This is the single most important number. |
| 18 TB | Beyond one comfortable node — sharding eventually required. |
| 120 peak writes/s | Trivial. Do **not** design for write scale here. |
| 6 MB/s | Bandwidth is a non-issue. Stop thinking about it. |

That last table is the actual output of estimation. Not the numbers — the decisions they force.

---

## 4. Sanity checks

- **Per-machine reality.** A well-tuned service handles ~1,000–10,000 rps per core-heavy box for
  simple work; a database does far fewer complex queries. If your estimate says one server does
  200,000 rps, you have an error.
- **The 1M-rows rule.** Under ~1M rows, almost any storage works and almost any query is fast. Do not
  design for scale you do not have.
- **Cost check.** Multiply storage by roughly $0.02/GB/month and see whether the answer is absurd.
  18 TB ≈ $360/month, which is fine. 18 PB is a different company.
- **Does it fit in RAM?** If the whole working set fits in memory on one machine, most of your
  distributed design is unnecessary. Check this before designing anything.

---

## 5. Common mistakes

| Mistake | Fix |
|---|---|
| Averaging away the peak | Always apply the peak factor. You provision for peak. |
| Forgetting replication | ×3 on every storage number |
| Ignoring indexes | +30–50% on top of row size |
| Quoting five significant figures | Round. Precision implies confidence you do not have. |
| Estimating, then ignoring the result | The numbers exist to force decisions — say which ones they forced |
| Designing for hypothetical growth | Design for 10× current, not 1000× |

---

## Related

- [System design thinking](SYSTEM-DESIGN-THINKING.md) — step 6 of the method
- [Trade-off framework](TRADEOFF-FRAMEWORK.md) — what to do with the numbers
- [Design checklist](DESIGN-CHECKLIST.md)

<!-- PATH:BEGIN -->

---

<sub>**The reading path** · step 2 of 23 · *Estimation*</sub>

◀ **Previous** [System design thinking](SYSTEM-DESIGN-THINKING.md) &nbsp;·&nbsp; **Next** [Trade-off framework](TRADEOFF-FRAMEWORK.md) ▶

<!-- PATH:END -->
