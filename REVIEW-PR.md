# PR: prune expired request events during evaluation

## Review format

Spend 20 minutes reviewing this change. Explain correctness and user impact using
concrete examples or tests. No code changes are expected; work without AI tools.
Ask the interviewer for clarification when needed.

## Motivation and proposal

The service currently keeps every request event forever. Remove events that no
configured monitor can use again, reducing retained history and evaluation work.
This is a retention optimization; monitor configuration and response formats stay
the same.

## Required behavior

- Preserve current evaluation metrics and alert/recovery history for all configured
  monitors, including monitors with different window durations. Keep the existing
  rolling boundaries `(now - window_seconds, now]` and 5xx/threshold semantics.
- On each evaluation, discard every stored event that is too old for every
  currently configured monitor. Retain events that any configured monitor may
  still need. Events after the evaluation time must remain available for later.
- Accept events in any arrival order, including late events. On the next evaluation,
  apply the same retention rule to them. An event still within a monitor's current
  window must participate in that evaluation; an already expired event is discarded.
- Cleanup must not change stored monitor configuration or past history. Repeated
  evaluation at the same time remains supported without duplicate notifications.

## Time and history assumptions

Evaluation time is now nondecreasing across the entire service, not just within
one monitor. Evaluating a different monitor at an earlier time returns the normal
validation error without changing that monitor's state. Equal times are allowed.
This explicit restriction makes irreversible time-based cleanup possible; historical
backtesting is outside scope. Cleanup uses the injected evaluation time, not wall time.

With no configured monitors, keep available events. When adding a monitor later,
it can only use history still retained: a newly added longer window does not restore
previously discarded events. No historical completeness is promised for such a new
monitor. Existing configured monitors must continue to receive complete windows.
There is no monitor deletion or window editing API in this change.

## Run the tests

From this snapshot's directory:

```sh
python3 -m unittest -v test_retention
python3 -m unittest -v
```

The added tests cover a cleanup boundary, recent out-of-order arrivals, the shared
evaluation clock, and cleanup before configuration. The full suite includes the
unchanged baseline tests. Review coverage as well as implementation. No manually
started server or additional dependency is needed; the transport test creates and
stops its own temporary loopback server.

## Scope

Keep the single-process, in-memory implementation. No scheduler, persistence,
distributed coordination, UI, real notification delivery, or additional dependency
is needed. Retention limits event age, not event count: an unlimited event rate can
still consume unlimited memory. Future-dated events and transition history are not
subject to a hard size limit either.
