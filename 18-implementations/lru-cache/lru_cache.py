"""An LRU cache with TTL, and the segmented variant that survives a scan.

Two things kill caches in production, and neither of them is the eviction
algorithm being slow.

The first is stale data. That is what the TTL is for, and it is checked
*lazily* on read rather than swept by a background thread -- see `_expired`.

The second is a **scan**. One batch job, one crawler, one analyst running
`SELECT *`, touching every key in the keyspace exactly once and never again.
Plain LRU treats "just touched" as "will be touched again", so it evicts the
entire hot working set to make room for data nobody will ever ask for twice.
Hit rate goes to zero, the full read load lands on the database that the cache
existed to protect, and the cache is now worse than useless: you are paying for
it, and it is adding a round trip to every miss.

`LRUCache` has that vulnerability and `test_lru_cache.py` asserts it happens --
a single pass over 1,000 cold keys wipes all 10 hot ones.
`SegmentedLRUCache` fixes it with one rule -- an entry is promoted to the
protected segment only on its SECOND read, because a second read is the only
evidence that caching something was worth anything -- and the same test proves
the same scan leaves the hot set completely intact. That contrast is the point
of this file.

Both are O(1) for get and put: a dict for lookup, a doubly-linked list for
recency order. The list is hand-rolled rather than delegated to `OrderedDict`
because the mechanism is the lesson; bench.py measures what that choice costs
against the C implementation, and the honest answer is "use OrderedDict".

Stdlib only, single process, thread-safe via one lock.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Iterator

_UNSET = object()  # so `ttl=None` can mean "never expires", overriding a default


class _Node:
    """One cache entry, and its two pointers.

    `__slots__` because a cache holding a million of these is the only reason
    anyone hand-rolls a linked list in Python -- a per-node `__dict__` would
    cost more than the values being cached.
    """

    __slots__ = ("key", "value", "expires_at", "prev", "next", "protected")

    def __init__(self, key: Any = None, value: Any = None, expires_at: float | None = None):
        self.key = key
        self.value = value
        self.expires_at = expires_at
        self.prev: _Node | None = None
        self.next: _Node | None = None
        self.protected = False  # used only by SegmentedLRUCache


class _List:
    """Doubly-linked list with sentinel ends, most-recent at the front.

    Sentinels rather than `None` checks: every unlink and every insert is then
    four unconditional pointer writes with no special case for the first or the
    last element. Hand-rolled LRU caches get their bugs in exactly those two
    special cases, and sentinels delete both.

    One consequence worth knowing before shipping this: a doubly-linked list is
    a *reference cycle*. Dropping the last reference to a cache does not free
    it -- reference counting cannot, because every node still points at its
    neighbours -- so the memory sits there until the cyclic collector runs. A
    process that creates and discards caches will hold every dead one in the
    meantime, and with a million entries each that is not a rounding error.
    `unlink` breaks the node's own pointers for this reason, but the live list
    stays cyclic through the sentinels by construction.
    """

    __slots__ = ("_head", "_tail", "_size")

    def __init__(self) -> None:
        self._head = _Node()  # most-recently-used side
        self._tail = _Node()  # least-recently-used side, i.e. the eviction end
        self._head.next = self._tail
        self._tail.prev = self._head
        self._size = 0

    def push_front(self, node: _Node) -> None:
        node.prev = self._head
        node.next = self._head.next
        self._head.next.prev = node
        self._head.next = node
        self._size += 1

    def unlink(self, node: _Node) -> None:
        node.prev.next = node.next
        node.next.prev = node.prev
        node.prev = node.next = None
        self._size -= 1

    def touch(self, node: _Node) -> None:
        """Move to the front. The entire cost of "recently used" bookkeeping."""
        self.unlink(node)
        self.push_front(node)

    def back(self) -> _Node | None:
        """The eviction candidate: one pointer read, never a search."""
        node = self._tail.prev
        return None if node is self._head else node

    def __len__(self) -> int:
        return self._size

    def __iter__(self) -> Iterator[_Node]:
        node = self._head.next
        while node is not self._tail:
            yield node
            node = node.next


class LRUCache:
    """Least-recently-used eviction with an optional TTL. O(1) get and put.

    Fast, simple, and the right default -- until something scans the keyspace.
    `SegmentedLRUCache` below is the same cache with that hole closed.
    """

    def __init__(self, capacity: int, *, ttl: float | None = None) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        if ttl is not None and ttl <= 0:
            raise ValueError("ttl must be positive or None")
        self.capacity = capacity
        self.ttl = ttl
        self._map: dict[Any, _Node] = {}
        self._order = _List()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expirations = 0

    # ------------------------------------------------------------------ read

    @staticmethod
    def _expired(node: _Node, now: float) -> bool:
        return node.expires_at is not None and node.expires_at <= now

    def get(self, key: Any, default: Any = None, now: float | None = None) -> Any:
        """Fetch and mark as recently used.

        `now` is injectable so tests can cross a TTL boundary without sleeping.
        A cache tested with real sleeps is slow, flaky, and cannot assert
        anything about the instant an entry dies.
        """
        t = time.monotonic() if now is None else now
        with self._lock:
            node = self._map.get(key)
            if node is None:
                self.misses += 1
                return default
            if self._expired(node, t):
                # Lazy expiry: the entry was found, and it is dead. Nothing swept
                # it -- a background thread per cache does not survive a few
                # thousand caches, and a global sweeper has to walk everything.
                # The cost is that a dead entry holds memory until someone asks
                # for it or it reaches the eviction end.
                self._drop(node)
                self.expirations += 1
                self.misses += 1
                return default
            self._order.touch(node)
            self.hits += 1
            return node.value

    def peek(self, key: Any, default: Any = None, now: float | None = None) -> Any:
        """Read without promoting and without counting. For tests and metrics.

        A `get` that is really an existence check silently reorders the cache;
        having a non-mutating read available is what stops that happening.
        """
        t = time.monotonic() if now is None else now
        node = self._map.get(key)
        if node is None or self._expired(node, t):
            return default
        return node.value

    # ----------------------------------------------------------------- write

    def put(self, key: Any, value: Any, now: float | None = None, ttl: Any = _UNSET) -> None:
        t = time.monotonic() if now is None else now
        effective_ttl = self.ttl if ttl is _UNSET else ttl
        expires_at = None if effective_ttl is None else t + effective_ttl

        with self._lock:
            node = self._map.get(key)
            if node is not None:
                node.value = value
                node.expires_at = expires_at  # a write refreshes the TTL
                self._order.touch(node)
                return
            if len(self._map) >= self.capacity:
                self._evict_one(t)
            node = _Node(key, value, expires_at)
            self._map[key] = node
            self._order.push_front(node)

    def _evict_one(self, now: float) -> None:
        """Remove the tail. Exactly one node is inspected, never a search.

        The temptation is to hunt down the list for an already-expired entry
        and free that instead of a live one. Resist it: that turns an O(1) put
        into an O(n) put precisely when the cache is full, which is precisely
        when it is under load. Expired entries at the tail get reclaimed here
        anyway -- they are just counted differently, because "evicted while
        still useful" and "expired" call for opposite fixes.
        """
        victim = self._order.back()
        if victim is None:
            return
        if self._expired(victim, now):
            self.expirations += 1
        else:
            self.evictions += 1
        self._drop(victim)

    def _drop(self, node: _Node) -> None:
        del self._map[node.key]
        self._order.unlink(node)

    def discard(self, key: Any) -> bool:
        with self._lock:
            node = self._map.get(key)
            if node is None:
                return False
            self._drop(node)
            return True

    def clear(self) -> None:
        with self._lock:
            self._map.clear()
            self._order = _List()

    # ------------------------------------------------------------ inspection

    @property
    def hit_rate(self) -> float:
        """Hits / lookups -- the only number that says whether this was worth it.

        A cache at 20% is not "helping a bit". It is adding a lookup, a network
        hop and a consistency problem to 80% of your reads in exchange for
        skipping a fifth of them. Measure this or do not run a cache; it is
        also the number that collapses first when something scans the keyspace,
        which makes it the earliest warning you get.
        """
        lookups = self.hits + self.misses
        return 0.0 if lookups == 0 else self.hits / lookups

    def stats(self) -> dict[str, float]:
        return {
            "size": len(self._map),
            "capacity": self.capacity,
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "hit_rate": self.hit_rate,
        }

    def reset_stats(self) -> None:
        self.hits = self.misses = self.evictions = self.expirations = 0

    def keys(self) -> list[Any]:
        """Most-recently-used first. The eviction order, reversed."""
        return [n.key for n in self._order]

    def __len__(self) -> int:
        return len(self._map)

    def __contains__(self, key: object) -> bool:
        """Deliberately does not promote and does not count -- see `peek`."""
        node = self._map.get(key)
        return node is not None and not self._expired(node, time.monotonic())

    def __repr__(self) -> str:
        return f"LRUCache(size={len(self._map)}/{self.capacity}, hit_rate={self.hit_rate:.1%})"


class SegmentedLRUCache(LRUCache):
    """LRU in two segments, so one pass over the keyspace cannot evict the hot set.

    Everything enters PROBATION. An entry moves to PROTECTED only when it is
    read a second time. That single rule is the whole defence: scanned keys are
    by definition read once, so they churn through probation against each other
    and never touch the protected segment at all.

    When protected is full its own LRU is *demoted* to the front of probation
    rather than deleted -- falling out of the hot set should cost an entry its
    protection, not its existence, because working sets shift back.

    Probation is allowed to exceed its nominal share whenever protected is
    under-full. An empty protected segment reserving space it is not using
    would make a cold cache smaller than the plain LRU it is meant to beat.

    This is the shape real caches converge on -- SLRU, and the TinyLFU family
    that supersedes it -- and it is bought for one extra pointer move per
    promotion and a boolean per node.
    """

    def __init__(
        self,
        capacity: int,
        *,
        protected_ratio: float = 0.8,
        ttl: float | None = None,
    ) -> None:
        super().__init__(capacity, ttl=ttl)
        if not 0.0 < protected_ratio < 1.0:
            raise ValueError("protected_ratio must be strictly between 0 and 1")
        self.protected_capacity = max(1, int(capacity * protected_ratio))
        if self.protected_capacity >= capacity:
            # Probation must always be able to hold at least one entry, or new
            # keys have nowhere to land and nothing is ever admitted.
            self.protected_capacity = capacity - 1
        if self.protected_capacity < 1:
            raise ValueError("capacity must be at least 2 for a segmented cache")
        self._protected = _List()
        self._probation = _List()
        self.promotions = 0
        self.demotions = 0
        del self._order  # superseded by the two segments; keep no stale copy

    def _segment(self, node: _Node) -> _List:
        return self._protected if node.protected else self._probation

    def get(self, key: Any, default: Any = None, now: float | None = None) -> Any:
        t = time.monotonic() if now is None else now
        with self._lock:
            node = self._map.get(key)
            if node is None:
                self.misses += 1
                return default
            if self._expired(node, t):
                self._drop(node)
                self.expirations += 1
                self.misses += 1
                return default
            self.hits += 1
            if node.protected:
                self._protected.touch(node)
            else:
                self._promote(node)
            return node.value

    def _promote(self, node: _Node) -> None:
        """Second read: this key has proved reuse, so protect it."""
        self._probation.unlink(node)
        node.protected = True
        self._protected.push_front(node)
        self.promotions += 1
        if len(self._protected) > self.protected_capacity:
            victim = self._protected.back()
            self._protected.unlink(victim)
            victim.protected = False
            self._probation.push_front(victim)
            self.demotions += 1

    def put(self, key: Any, value: Any, now: float | None = None, ttl: Any = _UNSET) -> None:
        t = time.monotonic() if now is None else now
        effective_ttl = self.ttl if ttl is _UNSET else ttl
        expires_at = None if effective_ttl is None else t + effective_ttl

        with self._lock:
            node = self._map.get(key)
            if node is not None:
                node.value = value
                node.expires_at = expires_at
                # A write is not evidence of reuse, so it refreshes recency
                # within the current segment but never promotes. Otherwise a
                # write-heavy scan would defeat the protection just as a
                # read-heavy one does.
                self._segment(node).touch(node)
                return
            if len(self._map) >= self.capacity:
                self._evict_one(t)
            node = _Node(key, value, expires_at)
            self._map[key] = node
            self._probation.push_front(node)

    def _evict_one(self, now: float) -> None:
        # Always from probation. Protected entries are only reachable for
        # eviction after being demoted, which requires competition from another
        # entry that also proved reuse -- never from a one-touch scan.
        victim = self._probation.back() or self._protected.back()
        if victim is None:
            return
        if self._expired(victim, now):
            self.expirations += 1
        else:
            self.evictions += 1
        self._drop(victim)

    def _drop(self, node: _Node) -> None:
        del self._map[node.key]
        self._segment(node).unlink(node)

    def clear(self) -> None:
        with self._lock:
            self._map.clear()
            self._protected = _List()
            self._probation = _List()

    def keys(self) -> list[Any]:
        return [n.key for n in self._protected] + [n.key for n in self._probation]

    def stats(self) -> dict[str, float]:
        s = super().stats()
        s.update(
            protected=len(self._protected),
            probation=len(self._probation),
            promotions=self.promotions,
            demotions=self.demotions,
        )
        return s

    def __repr__(self) -> str:
        return (
            f"SegmentedLRUCache(protected={len(self._protected)}/{self.protected_capacity}, "
            f"probation={len(self._probation)}, hit_rate={self.hit_rate:.1%})"
        )
