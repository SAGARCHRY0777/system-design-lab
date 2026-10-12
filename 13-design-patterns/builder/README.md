---
topic: Builder
category: Patterns
difficulty: Intermediate
concepts: [builder, immutability, validation, fluent-api, telescoping-constructor]
related: [prototype, abstract-factory, infrastructure-as-code, idempotency]
---

# Builder

`[INTERMEDIATE]` · Construct a complex object step by step, then produce it in one validated,
immutable piece.

**Two different patterns share this name**, and conflating them is most of the confusion. The one
you will meet is not the one in the Gang of Four book. And in Python you will usually not need
either, because the language already has the feature Java invented Builder to work around.

Every claim here is asserted by a test in
**[`18-implementations/builder/`](../../18-implementations/builder/)**.

---

## 1. One-line definition

An object that accumulates construction parameters through separate calls and produces the finished
object once, validating everything at the moment it has everything.

## 2. Explain like I'm new

A constructor with many optional parameters becomes unreadable:

```java
new Request("https://api.dev", "POST", 30, 3, true, false, null, true);
```

What is `true`? Which `true`? Swap two adjacent booleans and it still compiles, still runs, and does
something different.

A builder names each one at the call site:

```java
new RequestBuilder("https://api.dev")
    .method("POST")
    .timeout(30)
    .retries(3)
    .build();
```

Same object. You can now read it, and you cannot transpose two arguments by accident because there
are no positions to transpose.

## 3. Real-world analogy

A restaurant order. You do not shout every choice in one sentence in a fixed order — you say
"burger", then "no onions", then "fries instead of salad", and the kitchen starts only when you say
*that's everything*.

Two things the analogy gets right that matter later. **The kitchen checks at the end, not after each
sentence** — "no onions" is fine, "extra onions" is fine, and "no onions, extra onions" is only
detectable once you have stopped talking. And **the order pad is single-use**: reusing one pad for
the next table is how someone gets the previous customer's allergies.

## 4. Technical explanation

### The two patterns sharing the name

| | What it is | Who writes it |
|---|---|---|
| **GoF Builder** | A *Director* drives a Builder through steps, separating the construction **process** from the representation | Almost nobody |
| ***Effective Java* Item 2** | Fluent chained setters and a `build()` call | Everyone who says "builder" |

The GoF version's point is that the *same* step sequence can produce different representations —
one director, many builders. That is a genuine idea and it is rarely the problem anybody has.
Everything below is the second one.

### Every word of the definition, decoded

| Term | What it means |
|---|---|
| **telescoping constructor** | The problem: `Request(url)`, `Request(url, method)`, `Request(url, method, timeout)`… one overload per combination |
| **fluent** | Each setter returns the builder, so calls chain |
| **`build()`** | The terminal call. Validates, then produces the product |
| **product** | What `build()` returns — immutable, ideally |
| **single-use** | The builder refuses a second `build()`. See §5b |

## 5. Engineering at scale

### 5a. Where it validates is the whole design

```python
RequestBuilder(url).timeout(30).build()              # legal
RequestBuilder(url).retries(10).timeout(1).build()   # legal
RequestBuilder(url).timeout(30).retries(10).build()  # InvalidRequest
```

30 seconds is a fine timeout. 10 retries is a fine retry count. **30 seconds × 11 attempts is a
330-second worst case in a system whose own deadline is 30 seconds** — and no setter can see that,
because whichever one runs first has no idea what the other will be.

So a per-setter check has two options and both are wrong:

- reject a legal call, because the partner field has not arrived yet, or
- let it through, and make **call order significant** — which is the thing a fluent API is supposed
  to have abolished

`build()` is the first moment every field exists simultaneously. That makes it **the only place a
complete invariant can be enforced**, and that is the real reason the pattern has a terminal call
rather than just returning the product from the last setter.

> This is not an argument that setter validation is wrong. `retries(-1)` is a single-field rule, it
> belongs in the setter, and it gives a faster error. It is an argument that setter validation is
> **insufficient** — and the fields that matter most are usually the paired ones.

### 5b. What reuse leaks

A builder is mutable by definition and its product usually is not, so every hazard is at that seam.

```python
leaky = LeakyBuilder("https://a.dev").retries(5).header("auth", "token-a")
first  = leaky.build()
second = leaky.url("https://b.dev").build()

second["retries"]            # 5    — inherited
second["headers"]["auth"]    # "token-a" — someone else's credential
```

The second request is a **perfectly valid object nobody asked for**. Nothing raises, nothing logs,
and its retry count came from a request built somewhere else in the codebase.

Make the builder single-use. And note that reuse is almost never what was actually wanted: if the
product is immutable, `dataclasses.replace` (or a `toBuilder()` in Java) gives a new object with
some fields changed, sharing nothing mutable and leaving no builder in a dirty state.

### 5c. What `frozen` / `final` does not do

The nastiest one, because every signal says it cannot happen — the product is immutable, the caller
holds it, nobody else has a reference:

```python
built = leaky.build()
leaky.header("y", "2")        # nobody touched `built`
# built's headers now contain "y"
```

Except the builder *does* have a reference. It handed over its own dict rather than a copy, the two
share one object, and the builder is still alive.

> **`frozen=True` freezes the bindings, not the objects behind them.** A frozen dataclass holding a
> plain `list` or `dict` is not immutable in any useful sense. The same is true of `final` in Java
> and `readonly` in C#.

One `tuple(...)` on the way out closes it. The rule: **a builder must copy every mutable field into
the product, not pass it.**

### 5d. The distributed version: there is no "end" to validate at

```python
p = Provisioner(fail_on="database")
p.add("vpc").add("subnet").add("database")    # raises

p.created    # ["vpc", "subnet"] — live and billable
```

A half-built object in a process is garbage collected and costs nothing. **A half-built stack of
cloud resources is already running and already being billed.** `build()` cannot be atomic, because
each step is a separate API call to a separate system that has already committed.

So the local intuition inverts. The useful property is not "validate at the end" — by the end it is
too late. It is **knowing what was created before the failure**, which is why infrastructure tools
keep a state file instead of a builder, and why an error here has to name what it left behind.

The second-order consequence: retrying the whole sequence must be safe, which makes **idempotency**
a requirement rather than a nicety. `add("vpc")` on a retry must find the existing VPC, not create a
second one.

## 6. The problem it solves

An object with many optional parameters, where a positional constructor is unreadable and
error-prone, and where the validity of the whole cannot be judged from any one part.

## 7. The problem it does NOT solve

- **Too many parameters.** A builder makes eight parameters readable; it does not ask whether the
  object should have eight. Sometimes the answer is two objects.
- **Validation you forgot to write.** It gives you one good place to put it, and puts nothing there.
- **Mutability of the product.** §5c — that is a separate decision, and the one people get wrong.
- **Anything atomic across a network.** §5d.
- **Forgetting `build()`.** Nothing catches it; you pass the builder where the product was expected,
  and in a duck-typed language it may even partly work.

## 9. How it works

### 9a. Java — the form you will meet

```java
public final class Request {
    private final String url, method;
    private final int retries;

    private Request(Builder b) {                    // private: only the builder constructs
        this.url = b.url; this.method = b.method; this.retries = b.retries;
    }

    public static final class Builder {
        private final String url;                   // required: a constructor parameter
        private String method = "GET";              // optional: a default
        private int retries = 0;

        public Builder(String url) { this.url = url; }

        public Builder method(String m)  { this.method = m; return this; }
        public Builder retries(int n)    { this.retries = n; return this; }

        public Request build() {
            validate();                             // §5a — once, here
            return new Request(this);
        }
    }
}
```

**Required fields go in the builder's constructor; optional fields get setters.** That is the detail
that makes a builder safe rather than merely pretty — it is the one way the type system can insist
on the mandatory parts.

### 9b. Python — the same thing

```python
class RequestBuilder:
    def __init__(self, url: str) -> None:
        self._url, self._built = url, False
        self._method, self._timeout_s, self._retries = "GET", 30.0, 0
        self._headers: dict[str, str] = {}

    def retries(self, n: int) -> "RequestBuilder":
        self._retries = n
        return self

    def build(self) -> Request:
        if self._built:
            raise InvalidRequest("this builder has already produced a request")
        self._validate()                                    # §5a
        self._built = True
        return Request(..., headers=tuple(sorted(self._headers.items())))   # §5c: a copy
```

### 9c. What you would actually write in Python

```python
@dataclass(frozen=True)
class RequestConfig:
    url: str
    method: str = "GET"
    timeout_s: float = 30.0
    retries: int = 0

    def __post_init__(self) -> None:
        if self.timeout_s * (self.retries + 1) > 120:
            raise InvalidRequest("worst case exceeds the 120s budget")
```

**Java needs Builder because it has neither keyword arguments nor default parameter values.** Eight
optional fields become a telescoping family of overloads, or a call site reading
`new Request(url, true, false, 30, 3)` where nobody can say what the booleans are.

Python has both features:

| Builder gives you | Python already has |
|---|---|
| Readable call site | keyword arguments |
| Optional parameters | default values |
| Immutable product | `@dataclass(frozen=True)` |
| Validation in one place | `__post_init__` |

Five lines, no builder, same guarantees — and the implementation asserts the two produce equal
objects and reject the same inputs. The same reasoning now applies to Java `record`s with compact
constructors for the simpler cases.

### 9d. What survives in Python

The case keyword arguments cannot cover: **construction spread across several places**, where each
adds a piece and nobody holds the whole argument list at once. There is no single call to put the
keywords in.

Query builders and fluent DSLs are the other survivor, and for a different reason — there the
chaining *is* the readability, not a workaround for its absence.

## 13. When to use it

| Use it when | Because |
|---|---|
| Four or more optional parameters, in a language without keyword arguments | The telescoping constructor is the problem it was invented for |
| The product must be **immutable** | A builder is the standard way to assemble one incrementally |
| The validity of the whole depends on **several fields together** | §5a |
| Construction is **spread across call sites** | §9d — the one case keyword arguments cannot cover |
| It is a fluent DSL (queries, HTTP, test fixtures) | The chaining is the point |

## 14. When NOT to use it

- **In Python, for a plain configuration object.** §9c. Use a frozen dataclass.
- **For two or three required parameters.** A constructor is shorter and clearer.
- **When the product is mutable anyway.** You have added ceremony and bought nothing.
- **To paper over a class with too many fields.** Ask whether it should be two classes.
- **For anything that provisions across a network.** §5d — you want a state file, not a builder.

## 17. Trade-offs

| Axis | What you gain | What you give up |
|---|---|---|
| Call-site clarity | Every argument is named; transposition is impossible | — |
| Validation | One place, with every field present | Nothing, if you use it |
| Immutability | A product that can be frozen all the way down | Only if the builder copies. §5c |
| Code volume | — | Roughly double the fields, written twice |
| Safety | — | An unbuilt builder is an easy thing to leave dangling |
| Reuse | — | A reusable builder leaks. §5b |

**The one sentence:** *call-site clarity bought with boilerplate.*

## 18. Alternatives — the "why not?" table

| Instead of Builder | Why | When it is right |
|---|---|---|
| **Keyword arguments + defaults** | Same readability, no second class | Python, Kotlin, C#, Swift — i.e. default |
| **Frozen dataclass / `record`** | Adds immutability and one validation hook | Python always; Java for simple products |
| **`dataclasses.replace` / `toBuilder()`** | A variant of an existing object | What people want when they reach for reuse |
| **A parameter object** | Group related fields into their own type | When the eight fields are really two concepts |
| **Generated builder** (Lombok, `attrs`) | Removes the boilerplate | And **none** of the decisions — it still picks where validation lives and whether reuse is allowed, usually wrongly |

## 19. Failure scenarios

| Architecture | What happens |
|---|---|
| **Monolith** | Works as designed. A half-built builder is garbage collected |
| **Concurrent use** | A builder shared between threads is a mutable object with no lock. Builders are not thread-safe and are not meant to be — build in one thread, share the frozen product |
| **Long-lived / cached builder** | §5b at its worst: a builder held as a field accumulates state across unrelated requests, and the leak crosses users |
| **Infrastructure provisioning** | §5d. No atomic `build()`; a failure leaves live resources. Needs a state file and idempotent steps |

### The distributed counterpart

**Fluent request builders · infrastructure-as-code.** The intent survives — accumulate, then
commit — and the guarantee does not. Locally, nothing exists until `build()`. Across a network,
**each step has already happened**, so there is no moment before which nothing is real.

## 25. Without it → With it → New problem → Next

| Stage | State of the world |
|---|---|
| **Without it** | `new Request(url, true, false, 30, 3)`. Two adjacent booleans get transposed in review and nobody notices |
| **With it** | Every argument named at the call site; validation in one place; the product can be frozen |
| **New problem** | The builder is mutable and the product is not, so the seam leaks: reuse carries fields across builds, and a shared mutable field defeats `frozen` |
| **Next** | Single-use builder, copy every mutable field into the product, `replace` for variants |
| **And then** | In Python, notice that keyword arguments and a frozen dataclass did all of it in five lines, and delete the builder |

## 27. Implementation

**[`18-implementations/builder/`](../../18-implementations/builder/)** — runnable, stdlib only.

```bash
pytest test_builder.py -q     # 11 tests
python builder.py             # the same assertions, no test runner
```

Pinned there rather than claimed:

- a cross-field invariant that **cannot** be checked in a setter — each value legal alone, the pair
  not, and order-independent either way
- reuse carrying a previous build's retries **and its auth header**; the single-use builder raising
- an "immutable" product **changing after it was handed out**, because the builder kept the dict
- the builder and the dataclass producing **equal objects** and rejecting the same inputs
- a provisioning failure leaving two resources **live and billable**

No `bench.py` — a builder's cost is a few allocations nobody will find in a profile.

## 28. Common mistakes

1. **Validating in setters only.** Cross-field invariants are unreachable there. §5a.
2. **A reusable builder.** The second product inherits the first. §5b.
3. **Handing over a mutable field.** `frozen` then means nothing. §5c.
4. **Required fields as setters.** Put them in the builder's constructor so they cannot be omitted.
5. **A mutable product.** Half the reason to use a builder, discarded.
6. **Forgetting `build()`.** No type system catches it.
7. **Writing one in Python for a config object.** §9c.
8. **Sharing a builder between threads.** It is a mutable object with no lock.
9. **Expecting `build()` to be atomic across a network.** §5d.
10. **Reaching for Lombok and assuming the decisions came with it.** They did not.

## 30. Testing

1. **Test the invalid combination, not just the invalid field.** A suite that only checks
   `retries(-1)` would pass against a builder with no cross-field validation at all.
2. **Build twice from one builder** and assert it refuses — or, if you allow reuse, assert the
   second product does *not* inherit the first.
3. **Mutate the builder after `build()`** and assert the product did not change. This is the test
   nobody writes and the bug nobody sees.
4. **Assert the two implementations agree** if you keep both a builder and a direct constructor;
   duplicated validation rules drift.

## 31. Exercises

**1. Find the cross-field rule.** In a builder you own, find two fields that are individually valid
and jointly invalid. If `build()` does not check it, nothing does.

**2. Break the frozen product.** Build an object, then mutate the builder, then inspect the product.
If it changed, `build()` is handing over references.

**3. Delete a builder.** Take a Python builder and replace it with a frozen dataclass. Count the
lines removed and name what you lost.

**4. Kill a provision midway.** Run an infrastructure script and interrupt it. List what exists.
Then run it again and see whether it is idempotent.

<details>
<summary><strong>Interview: "Why a builder instead of a constructor?" — and the follow-ups</strong></summary>

**The answer:** a constructor with many optional parameters forces either a telescoping family of
overloads or unreadable positional arguments where two adjacent booleans can be transposed silently.
A builder names every argument at the call site and gives you **one place where all fields exist at
once**, which is the only place a cross-field invariant can be validated.

Lead with the validation point. Most candidates say "readability" and stop, which is the smaller
half.

| Follow-up | What they want to hear |
|---|---|
| *"Where do you validate?"* | `build()`, and **why**: a setter cannot see a field that has not been set |
| *"Can I reuse the builder?"* | Make it single-use. Reuse means the second product inherits the first. For variants, `toBuilder()` / `replace` |
| *"Your product is immutable. Is it?"* | Only if `build()` **copied** the mutable fields. `final`/`frozen` is shallow |
| *"How do you make a field required?"* | In the builder's constructor, not as a setter |
| *"Do it in Python."* | Keyword arguments and a frozen dataclass. Volunteering that the pattern is largely unnecessary there is the senior move |
| *"Thread safety?"* | Builders are not thread-safe and are not meant to be. Build in one thread, share the frozen product |
| *"Now it provisions cloud resources."* | There is no atomic `build()`; a failure leaves live, billable resources. State file, idempotent steps |

**What marks a senior answer:** treating it as a question about **where validation can live**,
not about fluent syntax.
</details>

## 33. Related

- **[Implementation](../../18-implementations/builder/)** — the runnable version of every claim here
- [Prototype](../prototype/) — the other creational pattern about an object's path into existence,
  and what a copy must not inherit
- [Abstract Factory](../abstract-factory/) — where the frozen-dataclass trick applies to families
- [Factory Method](../factory-method/) · [Singleton](../singleton/)
- [Pattern catalogue](../CATALOGUE.md#builder) · [Design patterns](../)
- [Retries](../../08-reliability/retries/) — why §5d's provisioning steps must be idempotent
- [Glossary: idempotency](../../GLOSSARY.md#idempotency)
