"""Strategy, State, Command: one shape, three intents.

Like the four wrappers, these three are near-identical in structure --

    class Context:
        def __init__(self, thing): self._thing = thing
        def run(self, x):          return self._thing.execute(x)

-- and Bridge looks like it too. Four patterns, one skeleton, told apart by
intent, which is exactly the distinction that dissolves when you read them on
four separate days. So: one file, one domain, and the discriminators asserted.

**Strategy against State is the pair people get wrong**, and the usual answer
("strategy is an algorithm, state is a state") restates the names. The
property that actually separates them:

    **Strategy objects do not know about each other. The CLIENT picks one.
    State objects know their successors. The STATE picks the next one.**

That is why State exists at all -- it replaces a transition table and a nest
of if-else with objects that each own their own exits. `ShippingStrategy` has
no method that returns another strategy; `OrderState.on` returns the next
state. Asserted in `test_a_strategy_knows_nothing_about_other_strategies`.

**Command is the odd one out and the most useful.** Strategy is *how* to do
something; a Command is **a specific invocation, reified** -- arguments bound,
so it can be queued, logged, retried, replayed and undone. That one change
makes it the bridge to every distributed pattern in the catalogue: a command
is a message, the undo log is a write-ahead log, and storing commands instead
of state is event sourcing.

Three things the usual treatment leaves out.

**Undo is not "run the inverse".** Most real operations have no inverse -- you
cannot un-send an email or un-charge a card. What you can do is *compensate*:
issue a refund, send a correction. The history grows; it never shrinks. That
is the Saga pattern, and it is why `undo` here appends rather than deletes.

**A retried command double-charges unless it is idempotent**, which is the
first thing anyone discovers after putting commands on a queue, because a
queue that guarantees delivery guarantees *at least once*.

**A state machine across services has no atomic transition.** Two workers can
both read `paid` and both ship. The fix is not a lock, it is a conditional
update -- compare-and-swap on the state column -- and `Order.transition`
models exactly that.

Stdlib only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable

# ─────────────────────────────────────────────────────────────────────────────
# 1. STRATEGY -- the client chooses, and the choices ignore each other
# ─────────────────────────────────────────────────────────────────────────────


class ShippingStrategy(ABC):
    """An interchangeable algorithm. Note what this class does NOT have.

    There is no method returning another `ShippingStrategy`. A strategy has no
    opinion about which strategy should run next, because that is the client's
    decision -- and that absence is the entire distinction from State.
    """

    @abstractmethod
    def cost(self, weight_kg: float) -> float: ...


class StandardShipping(ShippingStrategy):
    def cost(self, weight_kg: float) -> float:
        return 4.0 + 0.5 * weight_kg


class ExpressShipping(ShippingStrategy):
    def cost(self, weight_kg: float) -> float:
        return 12.0 + 1.5 * weight_kg


class FreeOverThreshold(ShippingStrategy):
    def __init__(self, threshold_kg: float = 20.0) -> None:
        self._threshold = threshold_kg

    def cost(self, weight_kg: float) -> float:
        return 0.0 if weight_kg >= self._threshold else 6.0


def cheapest(weight_kg: float, options: list[ShippingStrategy]) -> float:
    """The client comparing strategies, which only the client can do.

    No strategy could implement this: none of them knows the others exist.
    """
    return min(o.cost(weight_kg) for o in options)


# In Python a strategy is usually a function, and the stdlib agrees: the `key`
# argument to `sorted` is Strategy, and nobody writes a class for it. A class
# with one method and no state is a function with extra ceremony -- the same
# finding as Factory Method and Builder, arrived at from a different direction.
StrategyFn = Callable[[float], float]

standard_fn: StrategyFn = lambda kg: 4.0 + 0.5 * kg      # noqa: E731
express_fn: StrategyFn = lambda kg: 12.0 + 1.5 * kg      # noqa: E731


# ─────────────────────────────────────────────────────────────────────────────
# 2. STATE -- the state chooses, because it knows its own exits
# ─────────────────────────────────────────────────────────────────────────────


class IllegalTransition(Exception):
    """Raised for an event a state does not accept.

    A distinct type because the event usually arrives from outside -- a
    webhook, a user action, a retried message -- which makes an illegal
    transition input validation rather than an internal error. Half the value
    of modelling states as objects is that this exception becomes *possible to
    raise*, where a boolean flag would simply have been overwritten.
    """


class OrderState(ABC):
    """A state. The method that separates this from Strategy is `on`.

    `on` returns **another state**. No strategy has an equivalent, and that is
    the whole difference: a transition table lives here, distributed across
    the states, instead of in a nest of if-else at the call site.
    """

    name: str

    @abstractmethod
    def on(self, event: str) -> OrderState: ...

    def cancel(self) -> str:
        """Per-state behaviour, which is what justifies classes over a table.

        If only the *transitions* differed, a dict of dicts would be simpler
        and better -- see `TRANSITIONS` below, which this is checked against.
        Classes earn their place when the **behaviour** differs too, and
        cancelling is the clearest case: free before payment, a refund after
        it, and impossible once it is in a van.
        """
        raise IllegalTransition(f"cannot cancel an order that is {self.name}")

    def __repr__(self) -> str:
        return f"<{self.name}>"


class Pending(OrderState):
    name = "pending"

    def on(self, event: str) -> OrderState:
        if event == "pay":
            return Paid()
        if event == "cancel":
            return Cancelled()
        raise IllegalTransition(f"{self.name} does not accept {event!r}")

    def cancel(self) -> str:
        return "cancelled, nothing to refund"


class Paid(OrderState):
    name = "paid"

    def on(self, event: str) -> OrderState:
        if event == "ship":
            return Shipped()
        if event == "refund":
            return Refunded()
        raise IllegalTransition(f"{self.name} does not accept {event!r}")

    def cancel(self) -> str:
        return "cancelled, refund issued"       # different behaviour, same method


class Shipped(OrderState):
    name = "shipped"

    def on(self, event: str) -> OrderState:
        if event == "deliver":
            return Delivered()
        raise IllegalTransition(f"{self.name} does not accept {event!r}")
    # cancel() inherits the refusal: once it is in a van, it is not cancellable


class Delivered(OrderState):
    name = "delivered"

    def on(self, event: str) -> OrderState:
        raise IllegalTransition(f"{self.name} is terminal")


class Cancelled(OrderState):
    name = "cancelled"

    def on(self, event: str) -> OrderState:
        raise IllegalTransition(f"{self.name} is terminal")


class Refunded(OrderState):
    name = "refunded"

    def on(self, event: str) -> OrderState:
        raise IllegalTransition(f"{self.name} is terminal")


TRANSITIONS: dict[str, dict[str, str]] = {
    "pending": {"pay": "paid", "cancel": "cancelled"},
    "paid": {"ship": "shipped", "refund": "refunded"},
    "shipped": {"deliver": "delivered"},
    "delivered": {},
    "cancelled": {},
    "refunded": {},
}
"""The same machine as a table, kept so the two can be checked against each other.

Not redundancy -- it is the comparison the page is about. If only transitions
differed, this table would be the better implementation and the six classes
above would be ceremony. The classes earn their place because `cancel` differs
per state, and the test sweeps every state/event pair against this table so
the two cannot drift.
"""


class ConcurrentTransition(Exception):
    """Somebody else moved the order while we were deciding."""


@dataclass
class Order:
    """A state machine with the transition made conditional, not atomic.

    In one process, `self.state = self.state.on(event)` is fine. Across
    services it is a lost update: two workers both read `paid`, both decide to
    ship, and both write `shipped` -- two shipments, one order, no error.

    `expected` models the fix every database already offers:

        UPDATE orders SET state = 'shipped'
         WHERE id = ? AND state = 'paid'        -- 0 rows affected means you lost

    Compare-and-swap, not a lock. The loser finds out by being told nothing
    changed, which is why the return value of an UPDATE is worth checking and
    why `transition` raises instead of silently succeeding.
    """

    state: OrderState = field(default_factory=Pending)
    history: list[str] = field(default_factory=list)

    def transition(self, event: str, expected: str | None = None) -> OrderState:
        if expected is not None and self.state.name != expected:
            raise ConcurrentTransition(
                f"expected {expected!r}, found {self.state.name!r}: another writer won")
        self.state = self.state.on(event)
        self.history.append(self.state.name)
        return self.state


# ─────────────────────────────────────────────────────────────────────────────
# 3. COMMAND -- a call, reified
# ─────────────────────────────────────────────────────────────────────────────


class Command(ABC):
    """An invocation stored as an object: arguments bound, not yet run.

    That is the whole idea and it is what makes the pattern load-bearing in
    distributed systems. A strategy is *how* to do something and cannot be put
    on a queue, because it has no arguments. A command is a *specific* thing
    to do, so it can be queued, logged, retried, replayed and undone -- and
    once it can be queued, it is a message.
    """

    @abstractmethod
    def execute(self, ledger: list[str]) -> None: ...

    @abstractmethod
    def undo(self, ledger: list[str]) -> None: ...


@dataclass
class ReserveStock(Command):
    """The rare command with a true inverse: releasing a reservation."""

    sku: str
    qty: int

    def execute(self, ledger: list[str]) -> None:
        ledger.append(f"reserve {self.qty}x{self.sku}")

    def undo(self, ledger: list[str]) -> None:
        ledger.append(f"release {self.qty}x{self.sku}")


@dataclass
class ChargeCard(Command):
    """The common command with no inverse, only a compensation.

    You cannot un-charge a card. A refund is a **new, separate movement of
    money** that both parties see, with its own fee and its own settlement
    time. The ledger grows; it never shrinks, and `undo` appending rather
    than deleting is the point rather than an implementation shortcut.

    `idempotency_key` is here because a command that can be retried will be:
    a queue that guarantees delivery guarantees *at least once*, so the second
    delivery must be a no-op rather than a second charge.
    """

    amount: float
    idempotency_key: str | None = None

    def execute(self, ledger: list[str]) -> None:
        if self.idempotency_key is not None:
            if self.idempotency_key in _APPLIED:
                return                               # already done; say nothing
            _APPLIED.add(self.idempotency_key)
        ledger.append(f"charge {self.amount:.2f}")

    def undo(self, ledger: list[str]) -> None:
        ledger.append(f"refund {self.amount:.2f}")   # compensation, not deletion


@dataclass
class SendEmail(Command):
    """The command with no inverse and no compensation worth the name.

    A correction email is not an undo; the first one was read. Worth having in
    the list because a command log full of reversible operations teaches the
    wrong lesson -- part of designing a saga is noticing which steps can never
    be taken back and ordering them last.
    """

    to: str

    def execute(self, ledger: list[str]) -> None:
        ledger.append(f"email {self.to}")

    def undo(self, ledger: list[str]) -> None:
        ledger.append(f"correction-email {self.to}")


_APPLIED: set[str] = set()
"""Idempotency keys already applied. A dict in a real system, with a TTL."""


@dataclass
class Invoker:
    """Runs commands and keeps the log that makes undo possible.

    The log is the pattern's real product. Locally it is an undo stack;
    durably it is a write-ahead log; shipped elsewhere it is a replication
    stream; kept forever instead of the state it produced, it is event
    sourcing. Same list.

    `undo_last` unwinds in **reverse** order, which is not a detail: steps
    have dependencies, and releasing stock before refunding the card that
    paid for it leaves a window where the customer has neither.
    """

    ledger: list[str] = field(default_factory=list)
    log: list[Command] = field(default_factory=list)

    def run(self, command: Command) -> None:
        command.execute(self.ledger)
        self.log.append(command)

    def undo_last(self, n: int = 1) -> None:
        for _ in range(min(n, len(self.log))):
            self.log.pop().undo(self.ledger)

    def replay(self, into: list[str]) -> list[str]:
        """Re-run the log against a fresh ledger: the recovery path.

        A log that cannot be replayed is a history, not a recovery mechanism,
        and the difference only shows up when you need it.
        """
        for command in self.log:
            command.execute(into)
        return into


def demo() -> None:
    """Assert the discriminators with no test runner. `python behavioural.py`."""
    # Strategy: the client chooses; strategies ignore each other.
    opts = [StandardShipping(), ExpressShipping(), FreeOverThreshold()]
    assert cheapest(25, opts) == 0.0
    assert not any(hasattr(o, "on") for o in opts), "no strategy returns another strategy"
    assert StandardShipping().cost(10) == standard_fn(10), "a class with one method is a function"

    # State: the state chooses, and illegal transitions are impossible.
    order = Order()
    assert order.transition("pay").name == "paid"
    try:
        order.transition("pay")
        raise AssertionError("paid should not accept 'pay' again")
    except IllegalTransition:
        pass
    assert order.state.cancel() == "cancelled, refund issued"
    assert Pending().cancel() == "cancelled, nothing to refund"

    # Compare-and-swap: the second writer loses, loudly.
    o = Order()
    o.transition("pay", expected="pending")
    try:
        o.transition("ship", expected="pending")
        raise AssertionError("expected the stale writer to be rejected")
    except ConcurrentTransition:
        pass

    # Command: reified, replayable, and undone by compensation.
    inv = Invoker()
    inv.run(ReserveStock("abc", 2))
    inv.run(ChargeCard(40.0))
    inv.run(SendEmail("a@b.dev"))
    assert inv.ledger == ["reserve 2xabc", "charge 40.00", "email a@b.dev"]

    inv.undo_last(3)
    assert inv.ledger[3:] == ["correction-email a@b.dev", "refund 40.00", "release 2xabc"], \
        "unwound in reverse, and every undo APPENDS"

    # Idempotency: the retry must not charge twice.
    _APPLIED.clear()
    led: list[str] = []
    c = ChargeCard(99.0, idempotency_key="order-7")
    c.execute(led)
    c.execute(led)
    assert led == ["charge 99.00"], "at-least-once delivery, exactly-once effect"

    print("strategy: client picks, no strategy knows another · "
          "state: state picks, illegal transitions raise, CAS rejects the stale writer · "
          "command: replayable, undone in reverse by compensation, idempotent on retry")


if __name__ == "__main__":
    demo()
