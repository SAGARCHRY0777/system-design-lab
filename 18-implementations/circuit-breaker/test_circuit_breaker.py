"""Tests that assert the *defining properties*, not just that the code runs.

Every test drives the clock by hand. A breaker tested with real sleeps takes
its `reset_timeout_s` in wall-clock seconds per test and is flaky at exactly
the boundary it needs to assert -- the instant the cooldown expires.

The headline is `test_the_breaker_turns_a_slow_failure_into_a_fast_one`. It
runs the identical hundred-call loop against the identical broken dependency,
with and without a breaker, and measures the thread time each consumed: 500
seconds against 15. That conversion is the only reason to fit a breaker.
"""

from __future__ import annotations

import pytest

from circuit_breaker import CircuitBreaker, CircuitOpenError, State


class FakeClock:
    """A clock the test advances by hand, in simulated seconds.

    Passed as `clock=` rather than `now=` because `call()` also needs to
    measure how long the wrapped function took -- a dependency that hangs is
    simulated by having it advance this clock, which is the only way to test
    slow-call detection without actually being slow.
    """

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> float:
        self.t += dt
        return self.t


class Dependency:
    """A stand-in service that counts how many times it was actually reached.

    The count is the point. A breaker that "rejects" by calling through and
    discarding the answer has done nothing at all, and every state assertion
    would still pass.
    """

    def __init__(self, clock: FakeClock, latency_s: float = 0.0, healthy: bool = True) -> None:
        self.clock = clock
        self.latency_s = latency_s
        self.healthy = healthy
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        self.clock.advance(self.latency_s)   # time spent blocked on a socket
        if not self.healthy:
            raise TimeoutError("upstream did not answer")
        return "ok"


# --------------------------------------------------------------------------- #
# CLOSED -- the normal state                                                   #
# --------------------------------------------------------------------------- #

def test_a_closed_breaker_is_invisible():
    """The overwhelmingly common case: nothing is wrong, so nothing happens."""
    clock = FakeClock()
    dep = Dependency(clock)
    breaker = CircuitBreaker(clock=clock)

    for _ in range(100):
        assert breaker.call(dep) == "ok"

    assert dep.calls == 100
    assert breaker.state() is State.CLOSED
    assert breaker.rejected == 0


def test_it_opens_after_the_failure_threshold():
    clock = FakeClock()
    breaker = CircuitBreaker(failure_threshold=3, clock=clock)

    breaker.record_failure(now=0.0)
    breaker.record_failure(now=0.0)
    assert breaker.state(now=0.0) is State.CLOSED   # two is not yet three

    breaker.record_failure(now=0.0)
    assert breaker.state(now=0.0) is State.OPEN
    assert breaker.trips == 1


def test_failures_are_counted_consecutively_not_cumulatively():
    """A count that never resets would trip the breaker on five failures spread
    across a month, which describes every healthy service that has ever run."""
    breaker = CircuitBreaker(failure_threshold=3)

    breaker.record_failure(now=0.0)
    breaker.record_failure(now=1.0)
    breaker.record_success(now=2.0)        # the run is broken here
    breaker.record_failure(now=3.0)
    breaker.record_failure(now=4.0)

    assert breaker.state(now=5.0) is State.CLOSED


def test_call_reraises_the_original_exception_rather_than_swallowing_it():
    """The caller still needs to know what went wrong. A breaker that converts
    every error into its own type destroys the information needed to decide
    whether the failure was even the dependency's fault."""
    clock = FakeClock()
    dep = Dependency(clock, healthy=False)
    breaker = CircuitBreaker(failure_threshold=10, clock=clock)

    with pytest.raises(TimeoutError, match="upstream did not answer"):
        breaker.call(dep)


# --------------------------------------------------------------------------- #
# OPEN -- rejecting without calling, which is the entire value                 #
# --------------------------------------------------------------------------- #

def test_an_open_breaker_does_not_call_the_wrapped_function():
    """The assertion that matters, and the one that is easy to forget to make.

    Every state test below would still pass if `allow()` returned False *after*
    dialling the dependency and throwing the answer away. Counting the calls
    the dependency actually received is the only proof that anything was
    saved."""
    clock = FakeClock()
    dep = Dependency(clock, healthy=False)
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_s=60.0, clock=clock)

    for _ in range(2):
        with pytest.raises(TimeoutError):
            breaker.call(dep)
    assert dep.calls == 2
    assert breaker.state() is State.OPEN

    for _ in range(500):
        with pytest.raises(CircuitOpenError):
            breaker.call(dep)

    assert dep.calls == 2          # not 502. The dependency was never touched.
    assert breaker.rejected == 500


def test_the_rejection_tells_the_caller_when_to_come_back():
    """A component that says "no" without saying "when" guarantees an immediate
    retry, and a retry storm against a struggling dependency is precisely the
    outcome the breaker exists to prevent."""
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_s=30.0)
    breaker.record_failure(now=100.0)

    assert breaker.retry_after(now=100.0) == pytest.approx(30.0)
    assert breaker.retry_after(now=115.0) == pytest.approx(15.0)

    with pytest.raises(CircuitOpenError) as exc:
        breaker.call(lambda: "never runs", now=110.0)
    assert exc.value.retry_after == pytest.approx(20.0)


def test_retry_after_is_zero_while_calls_are_passing():
    breaker = CircuitBreaker()
    assert breaker.retry_after(now=0.0) == 0.0


def test_a_late_success_cannot_close_an_open_breaker():
    """A call that started while the breaker was closed can return after it has
    tripped. Its result is stale evidence about a dependency we have already
    judged, and letting it close the breaker would reopen the floodgates
    behind the cooldown's back."""
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_s=30.0)
    breaker.record_failure(now=0.0)
    assert breaker.state(now=0.0) is State.OPEN

    breaker.record_success(now=1.0)          # in-flight call finally returns
    assert breaker.state(now=1.0) is State.OPEN


# --------------------------------------------------------------------------- #
# HALF_OPEN -- the recovery probe                                              #
# --------------------------------------------------------------------------- #

def test_it_becomes_half_open_once_the_cooldown_elapses():
    """Time alone drives this transition -- no call arrives to trigger it,
    which is why `state()` is allowed to advance the machine instead of a timer
    thread doing it."""
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_s=10.0)
    breaker.record_failure(now=0.0)

    assert breaker.state(now=9.999) is State.OPEN
    assert breaker.state(now=10.0) is State.HALF_OPEN


def test_half_open_admits_exactly_one_trial_and_rejects_the_rest():
    """This is what half-open means. Ten threads arrive the instant the
    cooldown expires; one is allowed to ask, nine are turned away. Admitting
    all ten would be resuming full traffic against something that has not yet
    proved it is back, which is how you knock over a service that was halfway
    up."""
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_s=10.0)
    breaker.record_failure(now=0.0)

    verdicts = [breaker.allow(now=10.0) for _ in range(10)]
    assert verdicts == [True] + [False] * 9


def test_a_successful_probe_closes_the_breaker():
    clock = FakeClock()
    dep = Dependency(clock, healthy=False)
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_s=10.0, clock=clock)

    with pytest.raises(TimeoutError):
        breaker.call(dep)
    assert breaker.state() is State.OPEN

    dep.healthy = True                       # the dependency recovers
    clock.advance(10.0)
    assert breaker.call(dep) == "ok"

    assert breaker.state() is State.CLOSED
    assert breaker.call(dep) == "ok"         # full traffic resumes


def test_a_failed_probe_reopens_the_breaker_and_restarts_the_cooldown():
    """The recovery is not a one-way door. If the probe fails, the caller must
    wait a full cooldown again -- otherwise a permanently dead dependency gets
    probed on every single request the moment the first timer expires."""
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_s=10.0)
    breaker.record_failure(now=0.0)

    assert breaker.state(now=10.0) is State.HALF_OPEN
    assert breaker.allow(now=10.0) is True
    breaker.record_failure(now=10.0)         # the probe failed

    assert breaker.state(now=10.0) is State.OPEN
    assert breaker.retry_after(now=10.0) == pytest.approx(10.0)   # full cooldown
    assert breaker.state(now=19.0) is State.OPEN
    assert breaker.state(now=20.0) is State.HALF_OPEN


def test_a_slow_dependency_gets_probed_once_per_cooldown_and_no_more():
    """Over a long outage the breaker's cost is one probe per cooldown window,
    not one probe per request. That bound is what makes it safe to leave on."""
    clock = FakeClock()
    dep = Dependency(clock, healthy=False)
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_s=10.0, clock=clock)

    for _ in range(1000):                    # 1,000 requests over 100 seconds
        clock.advance(0.1)
        try:
            breaker.call(dep)
        except (TimeoutError, CircuitOpenError):
            pass

    # 1 call trips it at t=0.1, then one probe per cooldown at t=10.1 .. 90.1.
    # Ten requests out of a thousand reached a dependency that was down for the
    # whole run -- the other 99% were refused for free.
    assert dep.calls == 10


def test_success_threshold_above_one_requires_several_good_probes():
    """A dependency that flaps -- one good response then failure again -- can
    be made to prove itself more than once before full traffic resumes."""
    breaker = CircuitBreaker(
        failure_threshold=1, reset_timeout_s=10.0,
        success_threshold=3, half_open_max_calls=3,
    )
    breaker.record_failure(now=0.0)

    assert breaker.state(now=10.0) is State.HALF_OPEN
    breaker.allow(now=10.0)
    breaker.record_success(now=10.0)
    breaker.allow(now=10.0)
    breaker.record_success(now=10.0)
    assert breaker.state(now=10.0) is State.HALF_OPEN   # two is not yet three

    breaker.allow(now=10.0)
    breaker.record_success(now=10.0)
    assert breaker.state(now=10.0) is State.CLOSED


# --------------------------------------------------------------------------- #
# THE POINT: slow failure becomes fast failure                                 #
# --------------------------------------------------------------------------- #

def test_the_breaker_turns_a_slow_failure_into_a_fast_one():
    """The headline. Same loop, same broken dependency, 500s against 15s.

    The dependency does not refuse connections -- it accepts them and hangs for
    five seconds before timing out, which is the failure that actually takes
    systems down. Without a breaker, a hundred requests consume five hundred
    seconds of blocked thread time; the pool fills, requests that never needed
    this dependency queue behind the ones that do, and the caller falls over
    while its own code is fine.

    With a breaker, three calls pay the five seconds and the other ninety-seven
    return in microseconds. Those ninety-seven can now serve a stale cache
    entry, degrade the feature, or shed the request -- none of which a blocked
    thread can do. Fast failure is the only failure a caller can route
    around."""
    unprotected_clock = FakeClock()
    unprotected_dep = Dependency(unprotected_clock, latency_s=5.0, healthy=False)
    for _ in range(100):
        try:
            unprotected_dep()
        except TimeoutError:
            pass

    protected_clock = FakeClock()
    protected_dep = Dependency(protected_clock, latency_s=5.0, healthy=False)
    breaker = CircuitBreaker(
        failure_threshold=3, reset_timeout_s=300.0, clock=protected_clock,
    )
    for _ in range(100):
        try:
            breaker.call(protected_dep)
        except (TimeoutError, CircuitOpenError):
            pass

    assert unprotected_clock.t == 500.0      # 100 calls x 5s blocked
    assert protected_clock.t == 15.0         # 3 calls x 5s, then instant refusal
    assert unprotected_dep.calls == 100
    assert protected_dep.calls == 3


def test_rejection_consumes_no_time_at_all():
    """Not merely "less time" -- the rejection path does not touch the
    dependency, so the simulated clock, which only advances inside the
    dependency, does not move by a single tick across ten thousand calls."""
    clock = FakeClock()
    dep = Dependency(clock, latency_s=5.0, healthy=False)
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_s=1e9, clock=clock)

    with pytest.raises(TimeoutError):
        breaker.call(dep)
    tripped_at = clock.t

    for _ in range(10_000):
        with pytest.raises(CircuitOpenError):
            breaker.call(dep)

    assert clock.t == tripped_at


def test_a_slow_success_counts_as_a_failure():
    """The brownout. Without this rule the breaker never trips at all: the
    dependency returns 200s forever, it just takes eight seconds to do it,
    while every caller thread sits blocked. It is up by every health check and
    it is taking you down."""
    clock = FakeClock()
    dep = Dependency(clock, latency_s=8.0, healthy=True)   # succeeds, slowly
    breaker = CircuitBreaker(
        failure_threshold=3, slow_call_threshold_s=1.0, reset_timeout_s=60.0,
        clock=clock,
    )

    for _ in range(3):
        assert breaker.call(dep) == "ok"     # every call SUCCEEDS

    assert breaker.state() is State.OPEN
    assert breaker.slow_calls == 3


def test_a_fast_success_is_not_penalised_by_the_slow_call_rule():
    clock = FakeClock()
    dep = Dependency(clock, latency_s=0.05, healthy=True)
    breaker = CircuitBreaker(failure_threshold=2, slow_call_threshold_s=1.0, clock=clock)

    for _ in range(50):
        assert breaker.call(dep) == "ok"

    assert breaker.state() is State.CLOSED
    assert breaker.slow_calls == 0


# --------------------------------------------------------------------------- #
# Configuration and housekeeping                                               #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "kwargs",
    [
        {"failure_threshold": 0},
        {"failure_threshold": -1},
        {"reset_timeout_s": 0},
        {"reset_timeout_s": -5},
        {"success_threshold": 0},
        {"half_open_max_calls": 0},
    ],
)
def test_invalid_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        CircuitBreaker(**kwargs)


def test_reset_forces_the_breaker_closed_for_an_operator_override():
    breaker = CircuitBreaker(failure_threshold=1, reset_timeout_s=3600.0)
    breaker.record_failure(now=0.0)
    assert breaker.state(now=0.0) is State.OPEN

    breaker.reset()
    assert breaker.state(now=0.0) is State.CLOSED


def test_stats_expose_what_a_dashboard_needs():
    """`rejected` is the number to alert on: it counts requests that never
    reached the dependency, which is invisible in the dependency's own metrics
    and is the reason its error rate looks fine during an outage."""
    clock = FakeClock()
    dep = Dependency(clock, healthy=False)
    breaker = CircuitBreaker(failure_threshold=2, reset_timeout_s=60.0, clock=clock)

    for _ in range(20):
        try:
            breaker.call(dep)
        except (TimeoutError, CircuitOpenError):
            pass

    s = breaker.stats()
    assert s["state"] == "open"
    assert s["failures"] == 2
    assert s["rejected"] == 18
    assert s["trips"] == 1
