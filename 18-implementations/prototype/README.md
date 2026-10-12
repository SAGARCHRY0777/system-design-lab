---
topic: Prototype
category: Implementation
difficulty: Intermediate
concepts: [prototype, deep-copy, shallow-copy, identity, cloning]
---

# Prototype — implementation

Copying state is easy. The pattern's entire difficulty is deciding what the copy must **not** carry
over, and the list is always the same four things: **identity, connections, locks, caches.**

```bash
pytest test_prototype.py -q     # 16 tests
python prototype.py             # the same assertions, no test runner
```

No `bench.py`. "Cloning is cheaper than constructing" is counted, not timed —
`test_cloning_skips_the_expensive_construction` asserts five spawns and zero constructions, which
is the claim; how many microseconds it saved depends entirely on what your constructor does.

## The headline, and why it had to be written twice

Python looks like it protects you here. Copying a `threading.Lock` or a `socket` raises
immediately — **shallow and deep alike**:

```
TypeError: cannot pickle '_thread.lock' object
```

And because one unpicklable field makes the **entire object** uncopyable, a class that happens to
hold a lock inherits that guard for free.

**The first version of this file had a `_lock` field on `Document`.** So `copy.deepcopy(doc)` raised,
and the headline claim — that the dangerous clone is the one that *succeeds* — was false of the very
object written to demonstrate it. `python prototype.py` failed on the line asserting it.

That turned out to be the better lesson, and it is now two tests:

> **The guard is incidental.** It comes from a field whose purpose is thread-safety, not copy
> semantics. You get it by accident if your class happens to hold a lock, and you lose it by
> accident the day someone moves locking up a layer — with nothing failing.

```python
plain = copy.deepcopy(Document("Unlocked", ["a"]))        # fine

with pytest.raises(TypeError, match="pickle"):
    copy.deepcopy(ConcurrentDocument("Locked", ["a"]))    # refuses
```

Two classes, one field apart.

## 1. The dangerous clone is the one that does not raise

```python
twin = copy.deepcopy(doc)

assert twin.id == doc.id          # IDENTITY inherited, nothing complained
assert twin.conn is not None      # so was the connection
```

Nothing in `Document` is unpicklable, so both copy functions work. The result is **two objects that
each believe they are row N**, sharing one connection handle.

In production this surfaces weeks later as a unique constraint violation on a table that has been
quietly collecting duplicates — and the traceback points at the insert, not at the copy.

> "You can't copy objects with handles" is often remembered as a general safety net. It is a net
> with one specific hole, and the hole is exactly where people fall: a raw socket raises and saves
> you, while a connection *wrapper*, a pool handle, a cursor proxy or a client holding a session
> token copies happily. `test_a_connection_held_as_a_plain_object_copies_happily` isolates it.

## 2. What a clone must reset

```python
c = doc.clone(title="Report (draft)")

assert c.id != doc.id            # IDENTITY: a new row, not a duplicate
assert c.conn is None            # CONNECTION: dropped, so it must be given one
assert c._render_cache == {}     # CACHE: empty, not the prototype's rendering
```

And the fourth, on the lock-bearing sibling:

```python
assert cd.clone()._lock is not cd._lock    # LOCK: fresh, never shared, never copied
```

**A lock is the one member where both obvious answers are wrong.** Sharing it makes two logically
independent objects serialise against each other; copying it would leave neither protected. Only a
new lock is correct — which `clone` gets for free from the default factory.

> `conn` is **dropped** rather than shared, so the clone must be given one explicitly. Failing
> loudly beats sharing a handle silently: closing one would close both, and whichever is collected
> first takes the other's transport with it.

**A `clone()` whose body is `return deepcopy(self)` has not made these decisions — it has deferred
them** to whoever first notices the duplicate rows. That is the entire pattern, and
`test_a_clone_that_is_just_deepcopy_has_not_decided_anything` states it as a contrast.

## 3. Shallow against deep

The half everyone can recite and few check:

```python
shallow = copy.copy(doc)
shallow.sections.append("appendix")

assert doc.sections == ["intro", "body", "appendix"]   # the original changed
assert shallow.sections is doc.sections                # it is literally one list
```

`copy.copy` copies the attribute *bindings*. `copy.deepcopy` fixes that and brings two new problems:
it is slow, and it faithfully duplicates the things you most wanted dropped — which is §1.

## 4. Why the pattern exists at all

```python
reg.register("report", Document.expensive("Template", ["a", "b"]))

before = len(BUILDS)
spawned = [reg.spawn("report", title=f"doc-{i}") for i in range(5)]

assert len(BUILDS) == before              # five documents, zero constructions
assert len({d.id for d in spawned}) == 5  # and five distinct identities
```

Construction is expensive **and the state you want only exists at runtime** — a parsed template, a
warmed model, an entity configured by a level designer rather than by a constructor. You cannot
write that state as a literal, so you prepare one instance and copy it.

Container images, VM templates and database snapshots are the same idea at a larger scale, with
exactly the same caveat: **a golden image carrying the original host's SSH host key or machine-id is
this file's `id` bug, at fleet scale.**

`test_the_template_itself_is_never_mutated_by_a_spawn` guards the failure that makes a registry
worse than no registry — if a spawn can reach back into the template, every later spawn inherits the
change, and the symptom is that documents created after lunch differ from documents created before
it with nothing in any diff to explain why.

## What this deliberately does NOT implement

- **`__copy__` / `__deepcopy__` hooks.** They let `copy.copy(obj)` do the right thing, which sounds
  strictly better and is worse here: an explicit `clone()` makes the decisions visible at the call
  site, where a hook makes an innocuous-looking `deepcopy` behave specially at a distance.
- **`copy-on-write` / lazy cloning.** A real optimisation for large payloads and a different
  pattern's problem.
- **Serialization-based cloning** (`pickle.loads(pickle.dumps(x))`). Common, slow, and it inherits
  every hazard above plus pickle's own.
- **A timing benchmark.** How much cloning saves is entirely a property of your constructor.

## Related

- **[Prototype — the pattern page](../../13-design-patterns/prototype/)** — the full treatment: the
  four resets, Python and Java, container images, interview follow-ups
- [Builder](../builder/) — the other creational pattern about an object's path into existence
- [Singleton](../singleton/) — where identity is the point, rather than the thing to reset
- [Pattern catalogue](../../13-design-patterns/CATALOGUE.md#prototype)
