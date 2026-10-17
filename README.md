# Service Monitor

A small Python service that tracks the global fraction of HTTP requests ending in
server errors. It accepts request events, stores monitor configurations, and records
alert and recovery transitions when you evaluate a monitor.

## Run locally

Requires Python 3.9 or later. There are no third-party dependencies.

```sh
python3 -m unittest -v
python3 app.py
```

The server listens on `http://127.0.0.1:8000`. Stop it with Ctrl-C.

## API scenario test

`test_api.py` exercises monitor creation, event ingestion, alerting, inspection,
and recovery through the API dispatcher. It is an integration test with fresh
in-memory state and fixed timestamps; it needs no running server or network access.

```sh
python3 -m unittest -v test_api
```

## API behavior

### Inputs and evaluation

- Events require `timestamp`, `service`, and `status`. Timestamps are finite,
  nonnegative Unix seconds; fractional seconds are allowed. Service must be a
  nonempty string of at most 100 characters. HTTP status codes are integers from
  100 through 599.
- Monitors require a positive `window_seconds` and a `threshold` in `(0, 1]`.
  Every monitor counts requests across all services; only 500 through 599 are errors.
- Evaluation accepts `{"now": ...}` for reproducible results, or `{}` to use the
  current clock. `now` follows the timestamp rules and cannot move backward per
  monitor, though equal times are allowed. Retention also requires a shared
  nondecreasing evaluation time across monitors; see `REVIEW-PR.md`.
- A window includes events in `(now - window_seconds, now]`: the start is excluded
  and the end included. Out-of-order and future events may be ingested. Events
  later than `now` are excluded; late ingestion can change a subsequent evaluation
  at the same time.
- POST bodies must be JSON objects with the exact supported fields and be at most
  64 KiB. The GET and POST routes are exercised in `test_api.py`.

### Results and history

- Monitors start `UNEVALUATED`. A nonempty window reports `ALERT` when its error
  fraction is greater than or equal to the threshold, and `OK` otherwise.
  An empty window reports `NO_DATA` with `error_fraction: null`, distinct from zero.
- Evaluation and inspection return the monitor configuration, current state,
  `incident_open`, `last_evaluation`, and `history`. Each monitor has independent
  state and history. Evaluation results include `now`, `total`, `errors`, and
  `error_fraction`; history entries include a `kind`, `timestamp`, and those counts
  and fraction.
- History records one `ALERT` when an incident opens and one `RECOVERY` when it
  closes. `NO_DATA` leaves an open incident open; only `OK` closes it. Repeated
  evaluations do not duplicate notifications while the incident remains in the
  same condition.
- Creation returns HTTP 201. Reads and evaluations return 200. Invalid fields or
  values return 400 with a JSON `error`; unknown routes and monitor IDs return 404.

## Scope

This service is intended for local exploration.

### State and capacity

- Events, monitors, and history live in one process's memory. Restarting loses them.
- Evaluation prunes old events; history has no size limit. Time retention does not
  impose a hard memory bound. See `REVIEW-PR.md` for retention guarantees and limits.
- The HTTP server handles one request at a time.

### Integrations and deployment

- Evaluations are requested explicitly; there is no background scheduling.
- History entries represent notifications locally; no notifications are delivered.
- There is no authentication, persistence, deployment configuration, or external
  integration.
