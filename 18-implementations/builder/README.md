---
topic: Builder
category: Implementation
difficulty: Intermediate
concepts: [builder, immutability, validation, fluent-api, infrastructure-as-code]
---

# Builder — implementation

Two different patterns share this name, and conflating them is most of the confusion:

| | What it is | Who writes it |
|---|---|---|
| **GoF Builder** | A *Director* drives a Builder through steps, separating the construction **process** from the representation | Almost nobody |
| ***Effective Java* Item 2** | Fluent chained setters and a `build()` call | Everyone who says "builder" |

This implements the second one.

```bash
pytest test_builder.py -q     # 11 tests
python builder.py             # the same assertions, no test runner
```

No `bench.py`. A builder's cost is a few allocations nobody will find in a profile; what it costs is
correctness at the seam between a mutable builder and an immutable product.

## 1. Where it validates is the whole design

```python
assert RequestBuilder(URL).timeout(30).build().timeout_s == 30     # fine alone
assert RequestBuilder(URL).retries(10).timeout(1).build()          # fine alone

with pytest.raises(InvalidRequest):
    RequestBuilder(URL).timeout(30).retries(10).build()            # not fine together
```

30 seconds is legal. 10 retries is legal. **30 seconds × 11 attempts is a 330-second worst case in a
system whose own deadline is 30**, and no setter can see that — whichever one runs first has no idea
what the other will be.

So a per-setter check has two options and both are wrong: reject a legal call because its partner
field has not arrived yet, or let it through and make **call order significant**. `build()` is the
first moment every field exists simultaneously, which makes it the only place a complete invariant
can be enforced.

> Not an argument that setter validation is *wrong* — `retries(-1)` is a single-field rule and
> belongs there, where it gives a faster error. It is an argument that it is **insufficient**, and
> the fields that matter most are usually the paired ones.
> `test_per_setter_validation_catches_only_the_single_field_cases` holds both halves.

## 2. What reuse leaks

```python
leaky = LeakyBuilder("https://a.dev").retries(5).header("auth", "token-a")
first  = leaky.build()
second = leaky.url("https://b.dev").build()

assert second["url"]     == "https://b.dev"   # the part that was intended
assert second["retries"] == 5                 # and the part that was not
assert second["headers"]["auth"] == "token-a" # including someone's credential
```

The documented footgun, and it is quiet: the second request is a perfectly valid object nobody asked
for. Nothing raises, nothing logs, and its retry count came from a request built somewhere else.

The correct builder refuses:

```python
b = RequestBuilder("https://a.dev").timeout(5).retries(5)
b.build()
with pytest.raises(InvalidRequest, match="already produced"):
    b.build()
```

**And reuse is almost never what you actually wanted.** If the product is immutable,
`dataclasses.replace` gives a new object with some fields changed, sharing nothing mutable, leaving
no builder in a dirty state:

```python
other = variant_of(base, url="https://b.dev")     # base is untouched
```

## 3. What `frozen=True` does not do

The nastiest one, because every signal says it cannot happen — the product is "immutable", the
caller holds it, nobody else has a reference:

```python
leaky = LeakyBuilder(URL).header("x", "1")
built = leaky.build()

leaky.header("y", "2")                 # nobody touched `built`

assert set(built["headers"]) == {"x", "y"}      # it changed anyway
```

Except the builder *does* have a reference. It passed its own dict rather than a copy, so the two
share one object and the builder is still alive.

**`frozen=True` freezes the bindings, not the objects behind them.** A frozen dataclass holding a
plain `list` or `dict` is not immutable in any useful sense. One `tuple(...)` in `build()` closes
the seam:

```python
headers=tuple(sorted(self._headers.items()))
```

## 4. Python rarely needs any of this

```python
built  = RequestBuilder(URL).method("POST").timeout(5).retries(2).build()
direct = RequestConfig(URL, method="POST", timeout_s=5, retries=2)

assert dataclasses.asdict(built) == dataclasses.asdict(direct)
```

Java needs Builder because it has **neither keyword arguments nor default parameter values**, so
eight optional fields become a telescoping family of overloads or a call site reading
`new Request(url, true, false, 30, 3)` where nobody can say what the booleans are.

Python has both. Keyword arguments give the call-site readability, defaults give the optionality,
`frozen=True` gives the immutability, and `__post_init__` validates at exactly the moment `build()`
does — and for the same reason: it is the first point where every field exists.

**Five lines, no builder, same guarantees.**

## 5. What survives in Python — and the distributed lesson

The case keyword arguments cannot cover is construction **spread across several places**, where each
adds a piece and nobody holds the whole argument list at once. There is no single call to put the
keywords in.

That is also where the local intuition about builders stops being true:

```python
p = Provisioner(fail_on="database")

with pytest.raises(RuntimeError):
    p.add("vpc").add("subnet").add("database").add("cache")

assert p.created == ["vpc", "subnet"]        # live and billable
```

A half-built object in a process is garbage collected and costs nothing. **A half-built stack of
cloud resources is already running and already being billed**, and `build()` cannot be atomic
because each step is a separate API call to a separate system that has already committed.

So the useful property is not "validate at the end" — by the end it is too late. It is **knowing
what was created before the failure**, which is why infrastructure tools keep a state file rather
than a builder, and why the error message here has to name what it left behind.

## What this deliberately does NOT implement

- **The GoF Director.** Separating the construction *process* from the representation is a real
  distinction and almost nobody needs it. It would teach the name, not the pattern people use.
- **A generated builder** (Lombok `@Builder`, `attrs`). The generator removes the boilerplate and
  none of the decisions above — it still picks where validation lives and whether the product is
  reusable, usually by defaulting to the wrong answer on both.
- **A type-state builder** that makes `build()` uncallable until required fields are set. Elegant,
  and in Python it needs either a `Protocol` maze or runtime checks that are just `_validate` again.
- **Rollback on provisioning failure.** The hard part of infrastructure-as-code and far beyond one
  teaching file; the lesson here is that the failure leaves things behind, not how to clean them up.

## Related

- **[Builder — the pattern page](../../13-design-patterns/builder/)** — the full treatment: the two
  patterns sharing the name, Python and Java, interview follow-ups
- [Prototype](../prototype/) — the other creational pattern about copying state, and what a copy
  must not inherit
- [Abstract Factory](../abstract-factory/) — the frozen-dataclass trick, used for families
- [Pattern catalogue](../../13-design-patterns/CATALOGUE.md#builder)
- [Glossary: idempotency](../../GLOSSARY.md#idempotency) — what a retried `provision` needs
