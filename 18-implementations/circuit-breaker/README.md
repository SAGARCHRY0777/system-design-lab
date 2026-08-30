---
topic: Circuit Breaker
category: Implementation
difficulty: Intermediate
concepts: [reliability, fault-tolerance, timeouts, cascading-failure]
---

# Circuit Breaker — implementation

A three-state breaker, and a benchmark that measures the only thing it is for. The breaker's job is
not to stop calls. It is to **turn a slow failure into a fast one**, because fast failure is the only
kind a caller can do anything about.

```bash
pytest test_circuit_breaker.py -q   # 26 tests
python bench.py                     # real measurements, run them yourself
```

## What this demonstrates

| State | Behaviour | Cost per call |
|---|---|---|
| `CLOSED` | Calls pass; consecutive failures counted | 0.250 µs — invisible |
| `OPEN` | Rejected **without being made**; cooldown runs | 0.290 µs vs 10,000 µs of hanging |
| `HALF_OPEN` | Exactly **one** trial admitted; success closes, failure reopens | one probe per cooldown |

Half-open is the whole design. Without it there are two options and both are bad: stay open forever
and never recover automatically, or resume full production traffic the instant the timer fires and
knock a half-recovered dependency straight back over. Half-open asks the cheapest possible question —
one request — and lets the answer decide.

### It genuinely does not call the function

Every state assertion in this file would still pass if `allow()` returned `False` *after* dialling
the dependency and discarding the answer. Counting what the dependency actually received is the only
proof that anything was saved:

```python
def test_an_open_breaker_does_not_call_the_wrapped_function():
    ...
    for _ in range(500):
        with pytest.raises(CircuitOpenError):
            breaker.call(dep)

    assert dep.calls == 2          # not 502. The dependency was never touched.
```

Over a longer outage the bound is one probe per cooldown window, not one per request:
`test_a_slow_dependency_gets_probed_once_per_cooldown_and_no_more` runs a thousand requests across a
hundred seconds against a dependency that is down the whole time, and exactly **ten** reach it.

### Slow failure becomes fast failure

The failure people design for is a refused connection, which returns in microseconds and is nearly
harmless. The failure that actually takes systems down is a dependency that has gone *slow* — it
still accepts connections, it still eventually answers, it just takes eight seconds instead of eight
milliseconds. Every caller thread sits blocked on a socket, the pool fills, requests that never
needed that dependency queue behind the ones that do, and the caller falls over while its own code is
fine.

```python
def test_the_breaker_turns_a_slow_failure_into_a_fast_one():
    ...
    assert unprotected_clock.t == 500.0      # 100 calls x 5s blocked
    assert protected_clock.t == 15.0         # 3 calls x 5s, then instant refusal
    assert unprotected_dep.calls == 100
    assert protected_dep.calls == 3
```

Ninety-seven callers get an answer in microseconds instead of five seconds. Those ninety-seven can
serve a stale cache entry, degrade the feature, return a partial response, or shed the request — none
of which a blocked thread can do.

### A slow success counts as a failure

The subtlety that makes the above possible at all. A dependency in brownout never returns an error;
it returns `200 OK` and takes eight seconds to do it. It is up by every health check and it is taking
you down. `slow_call_threshold_s` is the mechanism by which the breaker can see that:

```python
def test_a_slow_success_counts_as_a_failure():
    ...
    for _ in range(3):
        assert breaker.call(dep) == "ok"     # every call SUCCEEDS
    assert breaker.state() is State.OPEN
```

### Tests drive the clock, benchmarks use the real one

Every test passes `now=` or a `FakeClock`. A breaker tested with real sleeps costs its
`reset_timeout_s` in wall-clock seconds per test and is flaky at exactly the boundary it needs to
assert — the instant the cooldown expires. The benchmark is the one place that really sleeps, because
wall-clock is the thing it measures.

## Measured

Run on the machine below by `bench.py`. **These are real; nothing here is estimated.** The dependency
genuinely blocks — that is the measurement.

```
machine : Intel64 Family 6 Model 183 Stepping 1, GenuineIntel
python  : 3.14.6 (Windows 11)
scenario: 200 calls to a dependency that hangs 10ms then fails

SLOW FAILURE vs FAST FAILURE  (real wall-clock, the dependency really blocks)
                     total       mean        p50        p99   reached dep
  no breaker        2.061s   10.304ms   10.286ms   10.677ms      200
  with breaker      0.051s    0.257ms    0.001ms   10.305ms        5

  40x less blocked thread time.
  Median latency 10.286ms -> 0.0013ms.

BREAKER OVERHEAD  (what you pay on the happy path, best of 3)
  allow(), closed              0.250 us/op
  allow(), open (rejecting)    0.290 us/op
  call() wrapping a no-op      0.684 us/op
  the no-op alone              0.021 us/op

  Wrapper cost: 0.663 us per call -- 0.066% of a 1ms network hop.
  Rejecting costs 0.290 us against 10,000 us of hanging: ~34,481x cheaper.
```

**The p99 column is the honest one and it is worth dwelling on.** With the breaker, p99 is still
10.3ms — the five calls that trip it pay full price, and the probes after each cooldown will too. A
breaker does not make the tail disappear. It makes the *median* nearly 8,000× faster and bounds how
many callers ever see the tail at all, which is a different and far more achievable promise than "no
slow calls".

**The overhead table settles the "is it worth fitting?" question.** 0.66 µs on the happy path against
a network call that costs at least a thousand times that. The wrapper is free in every sense that
matters, which is why a breaker belongs on the dependency *by default* rather than being retrofitted
after the first outage.

**The 40× figure understates the real benefit**, and the understatement is the interesting part. On
one thread this reads as a latency win. On a pool of 200 threads it is the difference between a
degraded feature and a caller with no threads left to serve anything — including the endpoints that
never touched the broken dependency. That second-order effect is why cascading failure is the actual
subject here, and it cannot be measured on one thread.

Note also `reached dep`: 200 versus 5. The dependency's own error-rate dashboard sees almost no
traffic during the outage and therefore almost no errors, which is why it can look healthy while
everything upstream is on fire. The number to alert on is the *caller's* `rejected` counter.

## What this deliberately does NOT implement

Everything that makes breakers hard in production:

- **Actual timeout enforcement.** This is the big honest gap. A synchronous breaker in pure stdlib
  cannot interrupt a blocking call — it can only notice afterwards that one was slow. If the callee
  hangs for ever, so does `call()`. Real deployments set a socket/request timeout on the client
  *underneath* the breaker; the breaker counts the timeouts, it does not create them. A breaker
  without a client timeout underneath it is decoration.
- **Distributed state.** Each process has its own breaker. Ten app servers each need their own five
  failures before any of them stops calling, so a dead dependency absorbs fifty probes per cooldown
  rather than five. Shared state fixes the count and costs a network round trip on the hot path to a
  store that may itself be the thing that is down.
- **Rolling-window error rates.** Failures here are *consecutive*. That is easy to reason about and
  wrong for high-volume services, where a dependency failing 40% of the time may never string five
  together while being comprehensively broken. Production counts errors over a sliding window and
  trips on a rate, with a minimum-throughput floor so three calls at 100% failure do not trip
  anything.
- **Error classification.** Any exception counts as a failure. A `404` from the dependency means
  *your request* was wrong, not that the dependency is unhealthy — counting it trips the breaker on a
  bug in your own code and takes out a service that is perfectly fine.
- **Bulkheads.** A breaker limits calls to a failing dependency; it does not cap concurrent calls to
  a *healthy* one. Between the dependency going slow and the fifth failure landing, unbounded threads
  can still pile in. A concurrency limiter alongside the breaker is what actually protects the pool.
- **Jitter on the cooldown.** Every instance trips at roughly the same moment and therefore probes at
  roughly the same moment — a synchronised herd of probes every `reset_timeout_s`. Production
  randomises the cooldown per instance.
- **A fallback.** The breaker fails fast; it has nothing to say about what you do with the time it
  gave back. That is the entire value, and it is the caller's job: a cached answer, a default, a
  degraded response, or a queued write.
- **Clock skew.** `time.monotonic()` is per-process. Nothing here coordinates cooldowns across nodes,
  and nothing needs to — until the state is shared, at which point it does.

## Choosing

```
Dependency is optional, a degraded answer exists    -> breaker + fallback   <- the usual answer
Dependency is mandatory, no meaningful fallback     -> breaker anyway; fail fast beats fail slow
Failures are frequent but the service is fine       -> rolling-window rate, not consecutive count
Calls are cheap, idempotent, and fail instantly     -> retries with backoff; a breaker adds nothing
Protecting a healthy dependency from your own load  -> rate limiter or bulkhead, not a breaker
```

The tuning, in the order it goes wrong:

```
failure_threshold      too low -> trips on a blip; too high -> the pool fills before it trips
reset_timeout_s        too low -> probes hammer a recovering service; too high -> slow recovery
slow_call_threshold_s  omitted -> brownouts are invisible and the breaker never trips at all
success_threshold      raise it only for a dependency that flaps
```

The one worth setting deliberately is `slow_call_threshold_s`. Leave it off and the breaker only sees
dependencies that are honestly, cleanly dead — which is the failure mode that was never going to hurt
you much anyway.

## Related

- [Reliability](../../00-foundations/reliability/) — the concept page: doing the right thing when
  parts are broken, and why availability and reliability are not the same number
- [Rate limiter](../rate-limiter/) — the same shape of control, pointed the other way: a breaker
  protects *you* from a dependency, a limiter protects a dependency from *you*
- [LRU cache](../lru-cache/) — where the fallback answer comes from when the breaker fails fast
- [Trade-off framework](../../TRADEOFF-FRAMEWORK.md) — the axes this choice sits on
- [Glossary: circuit breaker](../../GLOSSARY.md#circuit-breaker),
  [retry storm](../../GLOSSARY.md#retry-storm), [timeout](../../GLOSSARY.md#timeout),
  [tail latency](../../GLOSSARY.md#tail-latency)
