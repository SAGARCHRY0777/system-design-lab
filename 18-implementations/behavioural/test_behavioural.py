"""Tests that assert the defining properties, not that the code runs.

Strategy, State and Command are the same skeleton -- an object holding a thing
you call -- so every test here is a *discriminator*, something true of one and
false of another. Three tests each showing a pattern working would prove
nothing about the only question that matters, which is which one you are
looking at.

**The headline pair** is `test_a_strategy_knows_nothing_about_other_strategies`
beside `test_a_state_knows_its_successors`. The usual answer to "Strategy or
State?" restates the names. The property that separates them is on the class:

    a strategy has no method returning another strategy -- the CLIENT picks
    a state has `on(event) -> State`           -- the STATE picks

**The illegal-transition sweep** is the other one worth reading. It generates
every state/event pair from `TRANSITIONS` and asserts the classes agree, so
the table and the six classes cannot drift, and so "illegal transitions are
impossible" is checked for all 36 combinations rather than the two someone
thought of.

Then the three things the usual treatment omits: that a stale writer loses a
compare-and-swap rather than silently winning; that undo is compensation and
the ledger therefore *grows*; and that a retried command double-charges unless
it carries a key.
"""

from __future__ import annotations

import pytest

from behavioural import (
    _APPLIED,
    TRANSITIONS,
    ChargeCard,
    Command,
    ConcurrentTransition,
    ExpressShipping,
    FreeOverThreshold,
    IllegalTransition,
    Invoker,
    Order,
    OrderState,
    Paid,
    Pending,
    ReserveStock,
    SendEmail,
    ShippingStrategy,
    Shipped,
    StandardShipping,
    cheapest,
    express_fn,
    standard_fn,
)

STATES = {s.name: s for s in (Pending(), Paid(), Shipped())}
EVENTS = sorted({e for t in TRANSITIONS.values() for e in t})


@pytest.fixture(autouse=True)
def _clear_idempotency():
    _APPLIED.clear()
    yield
    _APPLIED.clear()


# ── headline pair: Strategy against State ──────────────────────────────────


def test_a_strategy_knows_nothing_about_other_strategies():
    """The defining absence. No method here returns another strategy.

    Which is why `cheapest` has to live outside them: comparing the options
    is something only the client can do, because no strategy knows the others
    exist. That absence is the whole distinction from State.
    """
    options: list[ShippingStrategy] = [
        StandardShipping(), ExpressShipping(), FreeOverThreshold()]

    for o in options:
        assert not hasattr(o, "on"), f"{type(o).__name__} must not pick a successor"
        assert not any(isinstance(getattr(o, n, None), ShippingStrategy) for n in dir(o))

    assert cheapest(25, options) == 0.0, "only the client can compare them"
    assert cheapest(2, options) == 5.0


def test_a_state_knows_its_successors():
    """The defining presence. `on` returns another state, so the state decides.

    That is why State exists: the transition table is distributed across the
    states, each owning its own exits, instead of sitting in a nest of
    if-else at every call site.
    """
    assert isinstance(Pending().on("pay"), OrderState)
    assert Pending().on("pay").name == "paid"
    assert Paid().on("ship").name == "shipped"

    assert not hasattr(StandardShipping(), "on"), "and a strategy has no equivalent"


def test_the_client_picks_a_strategy_and_the_state_picks_itself():
    """Said as one assertion, because it is one idea.

    The client hands `Order` nothing -- the order's own state chose `paid`.
    The client hands `cheapest` everything -- the strategies chose nothing.
    """
    order = Order()
    order.transition("pay")
    assert order.state.name == "paid", "nobody told it that; Pending.on did"

    assert cheapest(2, [StandardShipping(), ExpressShipping()]) == 5.0, "the client chose"


# ── the sweep: illegal transitions are impossible, for all of them ─────────


@pytest.mark.parametrize("state_name", sorted(STATES))
@pytest.mark.parametrize("event", EVENTS)
def test_every_state_event_pair_matches_the_table(state_name, event):
    """All 15 combinations, generated rather than chosen.

    Two things at once. The classes and `TRANSITIONS` cannot drift apart, so
    the comparison the page makes between them stays honest. And "illegal
    transitions are impossible" is checked for every pair, not the two someone
    happened to think of -- which is the only way that claim means anything.
    """
    state = STATES[state_name]
    allowed = TRANSITIONS[state_name]

    if event in allowed:
        assert state.on(event).name == allowed[event]
    else:
        with pytest.raises(IllegalTransition):
            state.on(event)


def test_terminal_states_accept_nothing():
    """Separate, because they are absent from `STATES` by construction."""
    order = Order()
    order.transition("cancel")

    for event in EVENTS:
        with pytest.raises(IllegalTransition, match="terminal"):
            order.state.on(event)


def test_behaviour_differs_per_state_which_is_what_justifies_the_classes():
    """If only transitions differed, the dict would be the better design.

    `cancel` is the case that earns six classes: free before payment, a refund
    after it, impossible once it is in a van. A table cannot express that
    without a second table of behaviours, at which point it is a worse class.
    """
    assert Pending().cancel() == "cancelled, nothing to refund"
    assert Paid().cancel() == "cancelled, refund issued"

    with pytest.raises(IllegalTransition, match="cannot cancel"):
        Shipped().cancel()


# ── the distributed half of State ──────────────────────────────────────────


def test_a_stale_writer_loses_the_compare_and_swap():
    """Two workers both read `paid`; one of them must be told it lost.

    In one process `self.state = self.state.on(event)` is fine. Across
    services it is a lost update -- both read `paid`, both decide to ship,
    both write `shipped`, two shipments, no error. The fix is not a lock, it
    is the conditional update every database already offers:

        UPDATE orders SET state='shipped' WHERE id=? AND state='paid'

    Zero rows affected means you lost, which is why the return value of an
    UPDATE is worth checking.
    """
    order = Order()
    order.transition("pay", expected="pending")      # worker A wins

    with pytest.raises(ConcurrentTransition, match="another writer won"):
        order.transition("ship", expected="pending")  # worker B had a stale read

    assert order.state.name == "paid", "and the loser changed nothing"


def test_the_winner_proceeds_normally():
    """A guard that rejects everything would also pass the test above."""
    order = Order()
    order.transition("pay", expected="pending")
    order.transition("ship", expected="paid")

    assert order.state.name == "shipped"
    assert order.history == ["paid", "shipped"]


# ── Command: the one that reaches into distributed systems ─────────────────


def test_a_command_is_a_call_you_can_store_and_run_later():
    """Arguments bound, nothing executed. That is the whole difference.

    A strategy cannot be queued, because it has no arguments -- it is *how*,
    not *what*. A command is a specific invocation, so it can be put on a
    queue, and once it can be put on a queue it is a message.
    """
    pending: list[Command] = [ReserveStock("abc", 2), ChargeCard(40.0)]
    ledger: list[str] = []

    assert ledger == [], "constructing them did nothing"

    for command in pending:
        command.execute(ledger)

    assert ledger == ["reserve 2xabc", "charge 40.00"]


def test_undo_is_compensation_not_deletion():
    """The ledger GROWS. You cannot un-charge a card.

    A refund is a new, separate movement of money with its own fee and its own
    settlement time, visible to both parties. Modelling undo as "remove the
    row" is how a system ends up unable to explain itself to an auditor -- and
    it is why the distributed version of this pattern is Saga, which
    compensates rather than rolls back.
    """
    inv = Invoker()
    inv.run(ChargeCard(40.0))
    assert inv.ledger == ["charge 40.00"]

    inv.undo_last()

    assert inv.ledger == ["charge 40.00", "refund 40.00"], "two entries, not zero"
    assert len(inv.ledger) == 2


def test_undo_runs_in_reverse_order():
    """Not a detail: steps depend on each other.

    Releasing stock before refunding the card that paid for it leaves a window
    where the customer has neither the goods nor the money.
    """
    inv = Invoker()
    inv.run(ReserveStock("abc", 2))
    inv.run(ChargeCard(40.0))
    inv.run(SendEmail("a@b.dev"))

    inv.undo_last(3)

    assert inv.ledger[3:] == [
        "correction-email a@b.dev", "refund 40.00", "release 2xabc"]
    assert inv.log == [], "and the log is unwound"


def test_some_commands_have_no_meaningful_undo_at_all():
    """A correction email is not an undo. The first one was read.

    Worth asserting because a command log full of reversible operations
    teaches the wrong lesson. Part of designing a saga is noticing which steps
    can never be taken back, and ordering them last.
    """
    inv = Invoker()
    inv.run(SendEmail("customer@example.dev"))
    inv.undo_last()

    assert inv.ledger == ["email customer@example.dev",
                          "correction-email customer@example.dev"]


def test_a_retried_command_double_charges_without_a_key():
    """The first thing anyone discovers after putting commands on a queue.

    A queue that guarantees delivery guarantees *at least once*, so the second
    delivery is not an edge case, it is scheduled.
    """
    ledger: list[str] = []
    command = ChargeCard(99.0)                      # no idempotency key

    command.execute(ledger)
    command.execute(ledger)                         # the redelivery

    assert ledger == ["charge 99.00", "charge 99.00"], "charged twice"


def test_an_idempotency_key_makes_the_retry_a_no_op():
    """At-least-once delivery, exactly-once effect. The key is the whole fix."""
    ledger: list[str] = []
    command = ChargeCard(99.0, idempotency_key="order-7")

    command.execute(ledger)
    command.execute(ledger)
    command.execute(ledger)

    assert ledger == ["charge 99.00"], "delivered three times, applied once"


def test_the_log_can_be_replayed_into_a_fresh_ledger():
    """Which is what makes the log a recovery mechanism rather than a history.

    Locally this is an undo stack. Durably it is a write-ahead log. Shipped
    elsewhere it is a replication stream. Kept forever instead of the state it
    produced, it is event sourcing. Same list, four names.
    """
    inv = Invoker()
    inv.run(ReserveStock("abc", 2))
    inv.run(ChargeCard(40.0))

    rebuilt = inv.replay(into=[])

    assert rebuilt == inv.ledger
    assert rebuilt is not inv.ledger, "a fresh ledger, reconstructed"


# ── the Python note that keeps recurring ───────────────────────────────────


def test_a_strategy_with_one_method_and_no_state_is_a_function():
    """`sorted(key=...)` is Strategy, and nobody writes a class for it.

    The same finding as Factory Method and Builder, reached from a third
    direction: Python has first-class functions, so the class is ceremony
    wherever the strategy has no state of its own. `FreeOverThreshold` keeps
    its class honestly -- it has a threshold.
    """
    for kg in (0.0, 2.5, 10.0, 100.0):
        assert StandardShipping().cost(kg) == standard_fn(kg)
        assert ExpressShipping().cost(kg) == express_fn(kg)

    assert cheapest(2, [StandardShipping(), ExpressShipping()]) == min(
        standard_fn(2), express_fn(2))
