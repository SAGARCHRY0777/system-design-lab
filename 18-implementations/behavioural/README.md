---
topic: Strategy, State, Command
category: Implementation
difficulty: Intermediate
concepts: [strategy, state, command, state-machine, idempotency, saga, compare-and-swap]
---

# Strategy, State, Command — implementation

Three behavioural patterns with one skeleton — and [Bridge](../structural/) looks like it too:

```python
class Context:
    def __init__(self, thing): self._thing = thing
    def run(self, x):          return self._thing.execute(x)
```

Four patterns, one shape, told apart by intent. Same situation as [the wrappers](../wrappers/), so
the same treatment: one file, one domain, discriminators **asserted** rather than described.

```bash
pytest test_behavioural.py -q     # 30 tests
python behavioural.py             # the same assertions, no test runner
```

## Strategy against State, which is the pair people get wrong

The usual answer — *"a strategy is an algorithm, a state is a state"* — restates the names. The
property that actually separates them is visible on the class:

> **A strategy has no method returning another strategy. The *client* picks one.
> A state has `on(event) -> State`. The *state* picks the next one.**

```python
assert not hasattr(StandardShipping(), "on")      # no strategy picks a successor
assert Pending().on("pay").name == "paid"         # the state did, unprompted
```

That absence is why `cheapest(...)` has to live outside the strategies: comparing the options is
something only the client can do, because **no strategy knows the others exist**.

And it is why State exists at all — the transition table is distributed across the states, each
owning its own exits, instead of sitting in a nest of if-else at every call site.

## Illegal transitions, swept rather than sampled

```python
@pytest.mark.parametrize("state_name", sorted(STATES))
@pytest.mark.parametrize("event", EVENTS)
def test_every_state_event_pair_matches_the_table(state_name, event):
    ...
```

Every state/event pair generated from `TRANSITIONS`, not the two someone thought of. It does two
jobs: *"illegal transitions are impossible"* becomes a claim about all 15 combinations, and the
six classes cannot drift from the table they are compared against.

Verified — making `Shipped` accept `pay` fails exactly `[pay-shipped]`.

### When a table beats the classes

`TRANSITIONS` is kept deliberately, because **if only the transitions differed, the dict would be
the better implementation** and six classes would be ceremony. What earns them is behaviour that
differs per state:

```python
Pending().cancel()   # "cancelled, nothing to refund"
Paid().cancel()      # "cancelled, refund issued"
Shipped().cancel()   # IllegalTransition — it is in a van
```

A table cannot express that without a second table of behaviours, at which point it is a worse
class.

## The distributed half of State

```python
order.transition("pay",  expected="pending")   # worker A wins
order.transition("ship", expected="pending")   # worker B had a stale read -> raises
```

In one process `self.state = self.state.on(event)` is fine. Across services it is a **lost
update**: both workers read `paid`, both decide to ship, both write `shipped`. Two shipments, one
order, no error anywhere.

The fix is not a lock. It is the conditional update every database already offers:

```sql
UPDATE orders SET state = 'shipped' WHERE id = ? AND state = 'paid'
```

**Zero rows affected means you lost** — which is why the return value of an `UPDATE` is worth
checking, and why `transition` raises rather than silently succeeding.

## Command — the one that reaches into distributed systems

A strategy is *how* to do something and cannot be queued, because it has no arguments. **A command
is a specific invocation with its arguments bound**, so it can be queued, logged, retried, replayed
and undone. Once it can be queued, it is a message.

### Undo is compensation, not deletion

```python
inv.run(ChargeCard(40.0))
inv.undo_last()

assert inv.ledger == ["charge 40.00", "refund 40.00"]    # two entries, not zero
```

**You cannot un-charge a card.** A refund is a new, separate movement of money with its own fee and
its own settlement time, visible to both parties. The ledger grows; it never shrinks.

Modelling undo as "remove the row" is how a system ends up unable to explain itself to an auditor —
and it is exactly why the distributed version of this pattern is **Saga**, which compensates rather
than rolls back.

Some commands have no meaningful undo at all. A correction email is not an undo; the first one was
read. **Part of designing a saga is noticing which steps can never be taken back, and ordering them
last.**

### Undo runs in reverse, and that is not a detail

```python
inv.undo_last(3)
assert inv.ledger[3:] == ["correction-email …", "refund 40.00", "release 2xabc"]
```

Steps depend on each other. Releasing stock before refunding the card that paid for it leaves a
window where the customer has neither the goods nor the money.

### A retried command double-charges

```python
ChargeCard(99.0).execute(ledger)                      # delivered
ChargeCard(99.0).execute(ledger)                      # redelivered
# ["charge 99.00", "charge 99.00"]

c = ChargeCard(99.0, idempotency_key="order-7")
c.execute(ledger); c.execute(ledger); c.execute(ledger)
# ["charge 99.00"]
```

The first thing anyone discovers after putting commands on a queue: **a queue that guarantees
delivery guarantees *at least once*.** The second delivery is not an edge case, it is scheduled.
At-least-once delivery, exactly-once effect, and the key is the whole fix.

### The log is the product

```python
rebuilt = inv.replay(into=[])
assert rebuilt == inv.ledger
```

Same list, four names: locally an **undo stack**; durably a **write-ahead log**; shipped elsewhere
a **replication stream**; kept forever instead of the state it produced, **event sourcing**.

A log that cannot be replayed is a history, not a recovery mechanism, and the difference only shows
up when you need it.

## The Python note that keeps recurring

```python
assert StandardShipping().cost(kg) == standard_fn(kg)
```

`sorted(key=...)` is Strategy, and nobody writes a class for it. Python has first-class functions,
so **a class with one method and no state is a function with ceremony** — the same finding as
[Factory Method](../factory-method/) and [Builder](../builder/), reached from a third direction.
`FreeOverThreshold` keeps its class honestly: it has a threshold.

## Verified by breaking it

Seven deliberate breaks, each expected to fail a named test, all caught:

| Break | Caught by |
|---|---|
| A strategy starts picking its successor | **both** headline tests |
| `Shipped` accepts `pay` | the sweep, at `[pay-shipped]` |
| Every state cancels identically | `test_behaviour_differs_per_state…` |
| Compare-and-swap guard removed | `test_a_stale_writer_loses…` |
| Undo deletes instead of compensating | two tests |
| Undo runs forwards | `test_undo_runs_in_reverse_order` |
| Idempotency key ignored | `test_an_idempotency_key_makes_the_retry_a_no_op` |

## What this deliberately does NOT implement

- **The other eight behavioural patterns.** Observer, Iterator, Template Method, Chain of
  Responsibility, Mediator, Memento, Visitor, Interpreter — they are not this shape and do not
  belong in a file about telling this shape apart.
- **A real saga coordinator.** Compensation ordering is shown; orchestration, timeouts and
  partial-failure recovery are a [distributed pattern](../../13-design-patterns/CATALOGUE.md#distributed-systems-patterns).
- **Durable storage for the command log.** The log *is* a WAL conceptually; making it one is a
  different exercise.
- **A state machine DSL.** Generated transition tables are a real technique and would hide the
  single comparison this file is making.

## Related

- **[Strategy, State, Command — the pattern page](../../13-design-patterns/behavioural/)**
- [Wrappers](../wrappers/) — the structural family's version of the same "one shape, many intents"
- [Structural](../structural/) — Bridge, which is this shape again
- [Circuit breaker](../circuit-breaker/) — a state machine with exactly this problem, in production
- [Rate limiter](../rate-limiter/) — where idempotency keys and retries meet
- [Pattern catalogue](../../13-design-patterns/CATALOGUE.md#strategy)
