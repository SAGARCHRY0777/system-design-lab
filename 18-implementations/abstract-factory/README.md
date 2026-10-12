---
topic: Abstract Factory
category: Implementation
difficulty: Intermediate
concepts: [abstract-factory, family-invariant, provider-abstraction, capability-negotiation]
---

# Abstract Factory — implementation

The pattern does not make objects easier to create. **It makes an illegal combination harder to
express** — an S3 store next to an in-memory queue — and that negative guarantee is the entire
product.

```bash
pytest test_abstract_factory.py -q     # 15 tests
python abstract_factory.py             # the same assertions, no test runner
```

No `bench.py`. Nothing here is a performance question; the expensive thing about this pattern is
what it costs to *change*, which is counted below rather than timed.

## Three things, in order of what they cost in real work

| # | Thing | Proved by |
|---|---|---|
| 1 | The family invariant | `test_every_factory_hands_out_a_matched_set`, swept over all of them |
| 2 | **The asymmetry — the actual decision rule** | `test_adding_a_product_breaks_every_factory` |
| 3 | **The family that leaks** | four tests, one per option, all runnable |

## 1. The invariant, checked across every factory

```python
@pytest.mark.parametrize("factory", FACTORIES, ids=lambda f: f.family)
def test_every_factory_hands_out_a_matched_set(factory):
    assert factory.store().family == factory.family
    assert factory.queue().family == factory.family
```

Checking *one* factory proves the pattern was understood. Checking all of them catches the realistic
bug — a copy-pasted fourth factory whose `queue()` still returns the third family's queue. Verified
by making exactly that mistake: `LocalFactory.queue()` returning `SqsQueue` fails
`test_every_factory_hands_out_a_matched_set[local]` with `- local / + s3`.

### Being honest about the guarantee in Python

```python
assert S3Store().family != MemoryQueue().family, "hand-mixing is still legal here"
```

Python has no package-private constructor, so a caller who bypasses the factory can still build a
mixed pair by hand. What the pattern buys is that **no path through the factory can mix** — `upload`
contains no expression that could. In Java, with package-private product constructors, it really is
unrepresentable. Here it is unreachable by anyone using the intended door, which is weaker and worth
saying rather than glossing.

## 2. The asymmetry — what "rigid" means in numbers

```
                   add a FAMILY              add a PRODUCT
                   ──────────────────        ─────────────────────
edits              1 new class               1 interface method
                   0 existing files          + 1 method in EVERY factory

cost               O(1)                      O(F)
```

> **The rule: use Abstract Factory when the number of *families* grows and the number of *products*
> is stable.** Invert that and you have chosen the pattern that charges you on exactly the axis you
> are growing.

Both halves are demonstrated, not asserted as arithmetic. A new family is defined inline inside the
test, works immediately, and nothing existing moves. A new product puts every factory into this
state:

```python
class Incomplete(BackendFactory):
    family = "broken"
    def store(self) -> Store: return DiskStore()
    # no queue() -- a third product was added and this one was missed

with pytest.raises(TypeError):
    Incomplete()          # Can't instantiate abstract class ...
```

### Where the ABC earns its keep

This is the opposite of the advice on the [Singleton](../singleton/) and
[Factory Method](../factory-method/) pages, where the Python answer was to skip the hierarchy. Here
the ABC does real work: **add an abstract method and every concrete factory fails loudly, at
instantiation.** That is not an annoyance, it is the cost arriving at the moment you incur it.
Duck-typed, the same change fails later, at a call site, in production.

## 3. The family that leaks

Providers differ in **capability**, not only in naming. `LocalFactory` has no presigned URLs and
never will. There are four responses, and the first three are the ones people actually pick:

| Option | What it does | Test |
|---|---|---|
| **Union** | `presign` on the base; local raises `NotImplementedError`. **The type says you may call it and the runtime disagrees** — the worst one, and the most commonly chosen because it compiles | `test_the_union_option_makes_the_type_system_lie` |
| **Intersection** | Drop `presign` from the interface; three of four providers lose a feature they have. Nothing raises and nothing lies, which is why it looks responsible — the cost is silent | `test_the_intersection_option_costs_everyone_the_feature` |
| **`isinstance`** | `if isinstance(factory, S3Factory): ...`. The abstraction is dead and still being maintained; every new provider needs another branch in every function that does this | `test_the_isinstance_option_couples_the_caller_to_the_concrete_type` |
| **Declare capabilities** | `supports("presign")`. The asymmetry becomes a documented, checkable value | `test_capabilities_declare_the_asymmetry_instead_of_hiding_it` |

```python
s3, local = S3Factory(), LocalFactory()

assert s3.supports("presign")
assert not local.supports("presign")
assert not hasattr(local, "presign"), "absent, rather than present and raising"
```

The fourth is not in the Gang of Four description and is the most useful thing in the file. It does
not pretend the family is symmetric; it makes the asymmetry something a caller can branch on without
knowing a concrete type. That is what mature libraries settle on.

**The better answer, where you can take it, is not to abstract at all.** Use one provider and accept
the lock-in. The abstraction tax is paid every day; the migration happens once, or never.

> **Why JDBC works and multi-cloud does not:** JDBC families are symmetric *by specification* — a
> standards body forced every driver to the same surface. Cloud providers had no such constraint and
> competed on differentiation. No amount of interface design makes an asymmetric family symmetric.

## What to actually write in Python

```python
@dataclass(frozen=True)
class Backend:
    family: str
    store: Callable[[], Store]
    queue: Callable[[], Queue]
    capabilities: frozenset[str] = frozenset()

BACKENDS = {
    "s3":    Backend("s3",    S3Store,   SqsQueue, frozenset({"presign", "versioning"})),
    "local": Backend("local", DiskStore, MemoryQueue),
}
```

**One class in total**, instead of one per family. The invariant survives — both fields are
required, so there is no way to construct half a family, and `frozen=True` stops anyone swapping a
member out afterwards:

```python
with pytest.raises(TypeError):
    Backend("s3", S3Store)        # half a family will not construct
```

What it gives up is the loud failure: a third product breaks the `Backend(...)` call sites rather
than every factory at instantiation. Nearly as loud, considerably less ceremony.

What it gains is that **families become values** — dict them, pass them, and sweep a test over every
one without naming any of them. That is the same "classes are values" theme as the previous two
implementations, and here it keeps the invariant rather than trading it away.

## What this deliberately does NOT implement

- **A real cloud client.** Needs network and credentials, and the lesson is about interface shape,
  not about S3.
- **The cross-platform UI toolkit.** The clearest *teaching* example and a dated one — nobody ships
  widget sets this way any more.
- **A registry to choose the factory.** Picking the factory is itself a factory problem, and it is
  [Factory Method's](../factory-method/) — including its registration bug.
- **Runtime capability discovery.** `capabilities` is a static declaration. Probing a live provider
  for what it supports is a different, much larger design.

## Related

- **[Abstract Factory — the pattern page](../../13-design-patterns/abstract-factory/)** — the full
  treatment: the invariant, the decision rule, why provider abstraction leaks, interview follow-ups
- [Factory Method](../factory-method/) — one product by inheritance, against a family by composition
- [Singleton](../singleton/) — the other creational pattern whose real cost is a scope nobody names
- [Pattern catalogue](../../13-design-patterns/CATALOGUE.md#abstract-factory)
- [Monolith vs microservices](../../02-architecture/monolith-vs-microservices/) — where the family
  invariant stops being enforceable by a type
