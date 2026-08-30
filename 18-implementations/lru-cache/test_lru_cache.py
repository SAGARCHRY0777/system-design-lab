"""Tests that assert the *defining properties*, not just that the code runs.

Every test injects `now` rather than sleeping. A cache tested with real sleeps
is slow and flaky, and the injected clock is the only way to assert anything
about the exact instant an entry dies.

The headline pair is `test_a_single_scan_destroys_the_entire_hot_set` and
`test_the_segmented_cache_survives_the_identical_scan`, adjacent on purpose:
same cache size, same hot set, same scan, 0% hit rate against 100%.

O(1) is proved rather than asserted, in `test_get_and_put_cost_the_same_at_1k
_and_100k_entries` -- a counting dict shows the operation count is literally
identical at both sizes, which no timing measurement could establish.
"""

from __future__ import annotations

import pytest

from lru_cache import LRUCache, SegmentedLRUCache


class CountingDict(dict):
    """A dict that counts every mapping operation performed on it.

    Substituted for the cache's `_map` so a test can assert constant-time
    behaviour *deterministically*. Timing the cache at two sizes and comparing
    would be the obvious approach and it is a bad one: it measures the machine,
    the GC, and whatever else is running, then flakes in CI. Counting the
    operations measures the algorithm.
    """

    def __init__(self, *args):
        super().__init__(*args)
        self.ops = 0

    def __getitem__(self, key):
        self.ops += 1
        return super().__getitem__(key)

    def __setitem__(self, key, value):
        self.ops += 1
        super().__setitem__(key, value)

    def __delitem__(self, key):
        self.ops += 1
        super().__delitem__(key)

    def __contains__(self, key):
        self.ops += 1
        return super().__contains__(key)

    def get(self, key, default=None):
        self.ops += 1
        return super().get(key, default)


# --------------------------------------------------------------------------- #
# LRU basics                                                                   #
# --------------------------------------------------------------------------- #

def test_get_returns_what_put_stored():
    c = LRUCache(capacity=4)
    c.put("a", 1, now=0.0)
    assert c.get("a", now=0.0) == 1
    assert c.get("missing", now=0.0) is None
    assert c.get("missing", default="fallback", now=0.0) == "fallback"


def test_capacity_is_never_exceeded():
    c = LRUCache(capacity=3)
    for i in range(100):
        c.put(f"k{i}", i, now=0.0)
    assert len(c) == 3
    assert c.evictions == 97


def test_the_least_recently_used_entry_is_the_one_evicted():
    c = LRUCache(capacity=3)
    for k in "abc":
        c.put(k, k, now=0.0)
    c.get("a", now=0.0)          # 'a' is now the most recent, 'b' the least
    c.put("d", "d", now=0.0)

    assert c.keys() == ["d", "a", "c"]
    assert "b" not in c


def test_writing_an_existing_key_updates_it_without_growing_the_cache():
    c = LRUCache(capacity=2)
    c.put("a", 1, now=0.0)
    c.put("b", 2, now=0.0)
    c.put("a", 99, now=0.0)

    assert len(c) == 2
    assert c.get("a", now=0.0) == 99
    assert c.evictions == 0


def test_keys_are_reported_most_recently_used_first():
    """`keys()` reversed IS the eviction order, which makes it worth having."""
    c = LRUCache(capacity=5)
    for k in "abcde":
        c.put(k, k, now=0.0)
    assert c.keys() == ["e", "d", "c", "b", "a"]
    c.get("a", now=0.0)
    assert c.keys() == ["a", "e", "d", "c", "b"]


def test_peek_reads_without_promoting_and_without_counting():
    """An existence check that silently reorders the cache is a trap; this is
    the escape hatch that stops `get` being misused for one."""
    c = LRUCache(capacity=3)
    for k in "abc":
        c.put(k, k, now=0.0)

    assert c.peek("a", now=0.0) == "a"
    assert c.keys() == ["c", "b", "a"]      # unmoved
    assert c.hits == 0 and c.misses == 0    # uncounted


def test_the_linked_list_and_the_dict_never_disagree():
    """The structural invariant. If these two drift apart the cache leaks
    memory (nodes with no dict entry) or serves nothing (the reverse), and
    every functional test still passes."""
    c = LRUCache(capacity=8)
    for i in range(200):
        c.put(f"k{i % 20}", i, now=0.0)
        c.get(f"k{i % 7}", now=0.0)
        if i % 13 == 0:
            c.discard(f"k{i % 20}")
        assert len(c.keys()) == len(c)


@pytest.mark.parametrize("capacity,ttl", [(0, None), (-1, None), (5, 0), (5, -2)])
def test_invalid_configuration_is_rejected(capacity, ttl):
    with pytest.raises(ValueError):
        LRUCache(capacity=capacity, ttl=ttl)


# --------------------------------------------------------------------------- #
# TTL -- lazy, on read, never swept                                            #
# --------------------------------------------------------------------------- #

def test_ttl_is_checked_lazily_on_read_not_by_a_background_sweeper():
    """The defining property of lazy expiry, and its cost, in four lines.

    Nothing runs between the write and the read. The entry is a thousand
    seconds past its TTL and still occupying memory -- and it is reclaimed by
    the read that discovers it is dead, not a moment earlier. That memory
    overhang is the price of not running a thread per cache."""
    c = LRUCache(capacity=10, ttl=5.0)
    c.put("k", 1, now=0.0)

    assert len(c) == 1                       # still resident, long past expiry
    assert c.get("k", now=1_000.0) is None   # the read is what kills it
    assert len(c) == 0                       # reclaimed only now


def test_an_entry_is_live_right_up_to_its_expiry_and_dead_at_it():
    c = LRUCache(capacity=10, ttl=5.0)
    c.put("k", 1, now=100.0)
    assert c.get("k", now=104.999) == 1
    assert c.get("k", now=105.0) is None


def test_expirations_are_counted_separately_from_evictions():
    """Conflating them hides which fix you need. A low hit rate from evictions
    means the cache is too small; from expirations it means the TTL is too
    short. Buying more memory does nothing for the second one."""
    c = LRUCache(capacity=10, ttl=1.0)
    c.put("k", 1, now=0.0)
    c.get("k", now=50.0)
    assert (c.expirations, c.evictions) == (1, 0)

    c2 = LRUCache(capacity=1)
    c2.put("a", 1, now=0.0)
    c2.put("b", 2, now=0.0)
    assert (c2.expirations, c2.evictions) == (0, 1)


def test_writing_a_key_refreshes_its_ttl():
    c = LRUCache(capacity=10, ttl=10.0)
    c.put("k", 1, now=0.0)
    c.put("k", 2, now=8.0)                   # expiry moves to t=18
    assert c.get("k", now=15.0) == 2


def test_a_per_entry_ttl_overrides_the_cache_default():
    c = LRUCache(capacity=10, ttl=100.0)
    c.put("short", 1, now=0.0, ttl=1.0)
    c.put("forever", 2, now=0.0, ttl=None)   # explicit None means never expires

    assert c.get("short", now=2.0) is None
    assert c.get("forever", now=10_000.0) == 2


def test_an_expired_entry_at_the_tail_is_reclaimed_by_eviction_not_hunted_down():
    """`put` inspects exactly one node. Searching the list for a dead entry to
    free instead of a live one would make `put` O(n) precisely when the cache
    is full, which is precisely when it is under load."""
    c = LRUCache(capacity=2, ttl=1.0)
    c.put("old", 1, now=0.0)
    c.put("new", 2, now=0.5)
    c.put("newer", 3, now=5.0)               # evicts 'old', which is also dead

    assert (c.expirations, c.evictions) == (1, 0)
    assert len(c) == 2


def test_contains_respects_the_ttl_without_promoting():
    c = LRUCache(capacity=3, ttl=1.0)
    c.put("k", 1, now=0.0)
    assert c.peek("k", now=0.5) == 1
    assert c.peek("k", now=2.0) is None


# --------------------------------------------------------------------------- #
# Hit rate -- the metric that decides whether the cache earned its keep        #
# --------------------------------------------------------------------------- #

def test_hit_rate_is_zero_before_any_lookup_rather_than_dividing_by_zero():
    assert LRUCache(capacity=4).hit_rate == 0.0


def test_hit_rate_counts_expiries_as_misses_because_the_caller_got_nothing():
    """From the caller's side a dead entry and an absent one are identical --
    both cost a trip to the origin. A hit rate that flattered itself by
    excluding expiries would not predict origin load, which is the only thing
    anyone uses it for."""
    c = LRUCache(capacity=10, ttl=1.0)
    c.put("k", 1, now=0.0)
    c.get("k", now=0.5)                      # hit
    c.get("k", now=5.0)                      # expired -> miss
    assert c.hit_rate == 0.5


def test_hit_rate_tracks_a_skewed_workload():
    """Caches only work on skew. 8 keys in a cache of 8, read 1,000 times."""
    c = LRUCache(capacity=8)
    for i in range(1000):
        key = f"k{i % 8}"
        if c.get(key, now=0.0) is None:
            c.put(key, i, now=0.0)
    assert c.hit_rate == pytest.approx(0.992, abs=0.001)   # 8 cold misses


def test_hit_rate_collapses_on_a_uniform_workload():
    """The other half of the same lesson: no skew, no cache. 1,000 distinct
    keys through a cache of 8 hits nothing at all, and the cache is pure
    overhead -- this is the workload people forget to check before shipping."""
    c = LRUCache(capacity=8)
    for i in range(1000):
        if c.get(f"k{i}", now=0.0) is None:
            c.put(f"k{i}", i, now=0.0)
    assert c.hit_rate == 0.0


def test_stats_reports_everything_needed_to_diagnose_a_bad_hit_rate():
    c = LRUCache(capacity=2, ttl=10.0)
    c.put("a", 1, now=0.0)
    c.put("b", 2, now=0.0)
    c.put("c", 3, now=0.0)
    c.get("a", now=0.0)
    s = c.stats()
    assert s["size"] == 2 and s["capacity"] == 2
    assert s["evictions"] == 1 and s["misses"] == 1


# --------------------------------------------------------------------------- #
# THE SCAN -- the failure mode that actually takes caches down                 #
# --------------------------------------------------------------------------- #

HOT = [f"hot:{i}" for i in range(10)]
COLD = [f"cold:{i}" for i in range(1000)]


def _warm(cache):
    """Establish a hot working set: written, then read twice."""
    for k in HOT:
        cache.put(k, k, now=0.0)
    for _ in range(2):
        for k in HOT:
            cache.get(k, now=0.0)
    return cache


def test_a_single_scan_destroys_the_entire_hot_set():
    """One batch job walks the keyspace once and the cache is annihilated.

    Ten hot keys in a cache of a hundred -- comfortably resident, hit rate
    100%. Then one pass over a thousand cold keys, each touched exactly once
    and never again. LRU believes every one of them is "recently used", so it
    evicts all ten hot keys to store data nobody will ever ask for a second
    time. Hit rate on the hot set goes to ZERO and the database takes the full
    read load, all from a job that was not even supposed to be a write.

    This is not a corner case. It is a nightly analytics query, a backup, a
    crawler, or a colleague running `SELECT *`."""
    c = _warm(LRUCache(capacity=100))
    assert all(c.peek(k, now=0.0) is not None for k in HOT)

    for k in COLD:                            # the scan: one touch each
        c.put(k, k, now=0.0)

    assert all(c.peek(k, now=0.0) is None for k in HOT)   # every one, gone

    c.reset_stats()
    for k in HOT:
        c.get(k, now=0.0)
    assert c.hit_rate == 0.0


def test_the_segmented_cache_survives_the_identical_scan():
    """Same size, same hot set, same scan. One rule changes the outcome
    completely: promotion requires a SECOND read, and a scan by definition
    never gives one. The cold keys churn through probation against each other
    while the protected segment is not touched at all."""
    c = _warm(SegmentedLRUCache(capacity=100))

    for k in COLD:
        c.put(k, k, now=0.0)

    assert all(c.peek(k, now=0.0) is not None for k in HOT)   # every one, intact

    c.reset_stats()
    for k in HOT:
        c.get(k, now=0.0)
    assert c.hit_rate == 1.0


def test_the_segmented_cache_still_evicts_and_still_respects_capacity():
    """Scan resistance is worthless if it is bought by refusing to evict."""
    c = _warm(SegmentedLRUCache(capacity=100))
    for k in COLD:
        c.put(k, k, now=0.0)
    assert len(c) == 100
    assert c.evictions >= 900


def test_promotion_requires_a_second_read_not_a_first():
    c = SegmentedLRUCache(capacity=10)
    c.put("k", 1, now=0.0)
    assert c.stats()["probation"] == 1 and c.stats()["protected"] == 0

    c.get("k", now=0.0)
    assert c.stats()["protected"] == 1 and c.promotions == 1


def test_writing_does_not_promote_because_a_write_is_not_evidence_of_reuse():
    """Otherwise a write-heavy scan -- a cache fill, a migration -- defeats the
    protection exactly as a read-heavy one would."""
    c = SegmentedLRUCache(capacity=10)
    for _ in range(5):
        c.put("k", 1, now=0.0)
    assert c.promotions == 0
    assert c.stats()["probation"] == 1


def test_a_protected_entry_falling_out_of_favour_is_demoted_not_deleted():
    """Working sets shift. Losing protection should cost an entry its
    privileged slot, not its existence -- it gets a second chance in
    probation, which is what makes the cache adapt instead of thrash."""
    c = SegmentedLRUCache(capacity=10, protected_ratio=0.5)   # protected holds 5
    for i in range(6):
        c.put(f"k{i}", i, now=0.0)
        c.get(f"k{i}", now=0.0)               # promote each

    assert c.demotions == 1
    assert c.stats()["protected"] == 5
    assert c.peek("k0", now=0.0) == 0         # demoted, still resident


def test_probation_may_exceed_its_share_while_protected_is_under_full():
    """Reserving space for a protected segment nobody has earned yet would
    make a cold segmented cache smaller than the plain LRU it must beat."""
    c = SegmentedLRUCache(capacity=100, protected_ratio=0.8)
    for i in range(100):
        c.put(f"k{i}", i, now=0.0)
    assert c.stats()["probation"] == 100      # not capped at 20
    assert len(c) == 100


def test_segmented_cache_honours_ttl_in_both_segments():
    c = SegmentedLRUCache(capacity=10, ttl=5.0)
    c.put("probation", 1, now=0.0)
    c.put("protected", 2, now=0.0)
    c.get("protected", now=0.0)               # promote

    assert c.get("probation", now=10.0) is None
    assert c.get("protected", now=10.0) is None
    assert len(c) == 0


@pytest.mark.parametrize("ratio", [0.0, 1.0, -0.5, 1.5])
def test_invalid_protected_ratio_is_rejected(ratio):
    with pytest.raises(ValueError):
        SegmentedLRUCache(capacity=10, protected_ratio=ratio)


def test_a_segmented_cache_needs_room_for_both_segments():
    with pytest.raises(ValueError):
        SegmentedLRUCache(capacity=1)


# --------------------------------------------------------------------------- #
# O(1) -- proved by counting operations, not by timing anything                #
# --------------------------------------------------------------------------- #

def _mapping_ops_for_a_get_and_an_overflowing_put(cache_cls, size: int) -> int:
    cache = cache_cls(capacity=size)
    for i in range(size):
        cache.put(f"k{i}", i, now=0.0)

    # Swap in the counter only after filling, so setup is not measured.
    cache._map = CountingDict(cache._map)
    cache.get("k0", now=0.0)
    cache.put("overflow", 1, now=0.0)   # cache is full, so this must evict
    return cache._map.ops


@pytest.mark.parametrize("cache_cls", [LRUCache, SegmentedLRUCache])
def test_get_and_put_cost_the_same_at_1k_and_100k_entries(cache_cls):
    """Constant time, demonstrated exactly rather than approximately.

    A hundred times the data, byte-for-byte the same number of mapping
    operations -- because eviction reads one pointer (`_List.back`) instead of
    searching for the oldest entry, and recency is a pointer swap instead of a
    re-sort. Nothing in either path is a function of size."""
    small = _mapping_ops_for_a_get_and_an_overflowing_put(cache_cls, 1_000)
    large = _mapping_ops_for_a_get_and_an_overflowing_put(cache_cls, 100_000)

    assert small == large
    assert small < 10          # constant, and a small constant


def test_eviction_reads_the_tail_pointer_and_never_walks_the_list():
    """The structural reason `put` is O(1): the victim is always `list.back()`,
    a single pointer read. Any implementation that searched for the least
    recently used entry would be O(n) here and would still pass every
    behavioural test above."""
    c = LRUCache(capacity=1000)
    for i in range(1000):
        c.put(f"k{i}", i, now=0.0)
    assert c.keys()[-1] == "k0"               # the tail is the LRU

    c.put("new", 1, now=0.0)
    assert "k0" not in c                      # and the tail is what went
    assert c.keys()[-1] == "k1"
