---
topic: Adapter, Decorator, Proxy, Facade
category: Implementation
difficulty: Intermediate
concepts: [adapter, decorator, proxy, facade, middleware, n-plus-one]
---

# Wrappers — implementation

Four of the seven structural patterns are the same five lines of code:

```python
class Wrapper:
    def __init__(self, inner): self._inner = inner
    def do(self, x):           return self._inner.do(x)
```

They differ by **intent**, which is exactly the kind of distinction that dissolves when you read
four separate descriptions on four separate days. So they are in one file, wrapping one object,
with the discriminators **asserted** rather than described.

```bash
pytest test_wrappers.py -q     # 11 tests
python wrappers.py             # the same assertions, no test runner
```

No `bench.py` — one measurement matters here and it is in a test, because it is a correctness
property rather than a performance one.

## Telling them apart in two questions

```
how many objects does it wrap?            many  ->  FACADE
is its interface the same as the
  thing it wraps?                    different  ->  ADAPTER
```

That leaves Decorator and Proxy, which is the genuinely hard pair:

> **Proxy decides *whether* the inner call happens.
> Decorator changes *what happens around* a call it always makes.**

Sharper than "one adds behaviour", and unlike that phrasing it is a property a test can assert:

```python
deco, prox = GzipDecorator(r1), CachingProxy(r2)
deco.render(); deco.render()
prox.render(); prox.render()

assert r1.renders == 2      # a decorator needs a result, so it always calls inner
assert r2.renders == 1      # a proxy decides whether the call happens at all
```

Same interface, same two calls, same wrapped object. **One integer is the entire distinction** —
and `test_both_are_indistinguishable_by_type` makes the other half explicit: both satisfy the
protocol, both take an inner of it, no type system separates them.

| | Interface vs what it wraps | Calls inner? | Wraps | Stackable |
|---|---|---|---|---|
| **Adapter** | **different** | always | one | no — two translations means one was aimed wrong |
| **Decorator** | same | **always** | one | **yes, that is the point** |
| **Proxy** | same | **maybe not** | one | rarely |
| **Facade** | **new and smaller** | always | **many** | no |

## Decorator order is part of the design, and invisible at the call site

```python
wrong = GzipDecorator(EncryptDecorator(report)).render()    # encrypt, then compress
right = EncryptDecorator(GzipDecorator(report)).render()    # compress, then encrypt
```

Both type-check. Both run. Measured:

```
raw                      9600 bytes
compress -> encrypt        80 bytes
encrypt  -> compress     9611 bytes      ← larger than the input
```

**120×**, and the wrong one is *bigger than the raw data* because ciphertext has no exploitable
structure and zlib's framing is pure overhead. The two expressions differ by six characters.

This is the generalisable point, not a compression anecdote: **in a middleware stack the ordering
is the security model.** Auth-then-log and log-then-auth are different systems, and nothing at the
call site shows which one you built.

> Worth knowing the follow-up: compress-then-encrypt is correct here and is itself a known hazard
> when an attacker controls part of the plaintext — the compressed length leaks information. That
> is CRIME and BREACH. "Compress first" is right for a log file and wrong for a session cookie.

## The most expensive proxy in production

```python
rows = [LazyRow(k, store) for k in store]     # "one query" to list them
assert QUERIES == []                          # constructing touched nothing

values = [r.value for r in rows]              # looks like attribute access

assert len(QUERIES) == 100                    # 1 + N
```

`LazyRow` is every ORM's lazy-loaded relation. It looks like an object, behaves like an object, and
touching `.value` is a round trip. **The call site reads like it is touching fields on objects it
already has.**

The transparency is the bug. A proxy that hid the cost badly would have been found in review; this
one hides it perfectly, which is why N+1 is the most common performance defect in web applications
and why the only reliable way to find it is to instrument the driver and count — which is what
`QUERIES` is.

## The trap: forwarding everything automatically

Writing one delegating method per interface method is tedious, and **every wrapper pays it** — add
a method to the interface and all of them need editing, the same O(N) tax
[Abstract Factory](../abstract-factory/) charges for a new product. `__getattr__` looks like the
escape hatch:

```python
wrapped = MagicWrapper(report)

assert wrapped.render()          # ordinary methods forward fine
assert wrapped.rows == ROWS      # so do attributes
assert len(report) == 400        # and the inner object supports len()

with pytest.raises(TypeError, match="has no len"):
    len(wrapped)                 # ← never reaches __getattr__
```

**Python looks special methods up on the type, not on the instance**, so `__getattr__` is never
consulted for them. The wrapper is a drop-in replacement right up until someone calls `len()`,
indexes it, iterates it, compares it, or puts it in an f-string.

The failure is quiet in the worst way: it works in every test that calls methods and breaks in the
one place that uses a builtin.

## Verified by inverting each one

Each distinction was broken deliberately and the right test caught it:

| Break | What failed |
|---|---|
| Proxy always forwards (behaves like a decorator) | `test_proxy_may_not_call_inner` |
| Decorator caches (behaves like a proxy) | `test_decorator_always_calls_inner` **and** the ordering test |
| `LazyRow` loads in `__init__` (stops being lazy) | `test_a_lazy_proxy_is_the_n_plus_one_problem` |

A test suite where swapping Proxy and Decorator still passes has not tested the distinction, which
is the whole subject.

## What this deliberately does NOT implement

- **Bridge, Composite, Flyweight.** The other three structural patterns, and none of them is a
  wrapper — they belong with their own problems rather than in a file about telling wrappers apart.
- **A real middleware framework.** Two decorators are enough to show that order matters; a
  framework would add routing and obscure it.
- **A remote proxy.** The interesting half is the failure modes — a proxy reachable while its
  subject is not — and that is [circuit breaker](../circuit-breaker/) territory.
- **`__getattr__` done properly.** It can be made to work for dunders by generating them onto the
  class, and the result is a metaclass nobody wants to debug. The lesson is the trap, not a way
  round it.

## Related

- **[Wrappers — the pattern page](../../13-design-patterns/wrappers/)** — the full treatment: four
  intents, Python and Java, the network-layer counterparts, interview follow-ups
- [Circuit breaker](../circuit-breaker/) — what a *remote* proxy's call needs around it
- [LRU cache](../lru-cache/) — what a caching proxy should hold
- [Abstract Factory](../abstract-factory/) — the same O(N) tax, for the same structural reason
- [Pattern catalogue](../../13-design-patterns/CATALOGUE.md#adapter) · [Design patterns](../../13-design-patterns/)
