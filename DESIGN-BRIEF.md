# Design brief: monitoring each service

## Format

You have 20 minutes to propose a design for extending the service you explored.
Work verbally, without coding or AI tools. Ask the interviewer for clarification
and state your assumptions; there is no single required implementation.

## Motivation and goal

A global error rate can hide an outage in a smaller service. In the same window,
990 successful search requests and 10 failed checkout requests produce a 1% global
error rate, while checkout's error rate is 100%.

Add an optional mode that evaluates error rates separately for each service.
Existing monitors should continue to behave globally by default. A user should be
able to identify which service is failing and follow its alert and recovery history.

## Functional requirements

- A user can configure a monitor to evaluate services separately. The monitor's
  configured rolling window and threshold apply to each service independently.
- In that mode, each service's error fraction uses only that service's requests
  in the window. Preserve the existing event-time window boundaries, 5xx error
  definition, and greater-than-or-equal threshold comparison.
- Each service can alert and recover independently. An evaluation that leaves an
  incident unchanged must not create another notification. Activity in one service
  must not change another service's incident, or another monitor's state.
- Configuration, evaluation results, status inspection, and history must make the
  selected mode clear. For service-based results and transitions, users must be able
  to identify the service they belong to.
- Existing global monitors and callers that do not select the new mode remain
  compatible: their calculations, state transitions, and API behavior stay the same.
- Keep evaluation explicitly requested and reproducible with a supplied evaluation
  time, as in the existing service.

## Decisions to discuss

Propose a policy for a service with no requests in the current window, for services
that appear or stop sending traffic, and for very small sample sizes. Explain the
user-visible effect of your choices. Start from the baseline policies where they
apply unless you agree on a change with the interviewer: empty data is distinct
from healthy data, and an open incident does not recover just because data is absent.
You may propose a simple low-volume policy; no particular minimum count is required.

## What to explain

Describe your proposed API changes and walk through the flow from event ingestion
to evaluation, status inspection, and history. Explain what state must be retained
and how it changes over time. Choose a few concrete test scenarios, including the
motivating example and continued global behavior, and explain the tradeoffs in your
design. Prioritize a coherent proposal over implementation detail.

## Scope and simplifications

Keep the existing single-process, in-memory setting. Persistence, distributed
scaling, a UI, scheduling, and real notification delivery are outside this exercise.
Recorded history continues to represent notifications locally.

This is a simplified monitoring exercise, not a Datadog integration or a requirement
to reproduce Datadog's APIs or policies. Use this application's existing rolling
window and explicit evaluation model; no vendor knowledge is needed.
