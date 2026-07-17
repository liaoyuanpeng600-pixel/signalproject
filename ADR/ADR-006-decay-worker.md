# ADR-006: Decay Worker Is a Background Job, Not an Agent

> **Status:** accepted
> **Date:** 2026-07-16
> **Supersedes:** —
> **Superseded by:** —

## Context

A Signal has a finite useful life. Once it has decayed past its `horizon` window, it should no longer appear in active reports. The job of marking Signals as `decayed` and recording `PrecedentOutcome` (for future reasoning) needs to happen continuously.

This work is:
- **Deterministic** — it's time-based, not LLM-based.
- **Continuous** — not tied to a cycle trigger.
- **Background** — doesn't block the ingest pipeline.
- **Cross-cutting** — affects all Signals, not just one batch.

We could model it as:
- **An agent** (A9 in [02 §2](../02_agent_constitution.md)) — invoked periodically like other agents.
- **A background job** — runs continuously, separate from the workflow runner.

## Decision

The decay worker is a **background job**, not an agent. It runs:
- Every 60 seconds (configurable)
- Independent of the workflow runner
- With no LLM cost
- Against the SignalStore directly

It performs:
1. Find Signals with `status=active` and `timestamp + horizon < now()` → set `status=decayed`.
2. Find Signals that need `PrecedentOutcome` recorded (per [05 §3.2](../05_reasoning_framework.md)) → fetch outcomes, write record.
3. Emit operational metrics.

## Alternatives Considered

### A9 decay agent in the workflow
- **Rejected.** Decay should not block the ingest cycle. Adding it as an agent means either (a) calling it every cycle (wasteful), or (b) calling it as a separate workflow (then it's not really an "agent" in the sense of [02 §1](../02_agent_constitution.md)).

### A cron job that calls the workflow runner
- **Rejected.** The workflow runner is built around cycles; a cron would need to fake cycle context.

### Database-side triggers
- **Rejected.** Hard to test, hard to version, hard to audit. Better to keep logic in application code.

## Trade-offs

- **Gained:** decoupled from cycle; continuous; deterministic; testable in isolation.
- **Gave up:** it's not formally an "agent" in [02 §2](../02_agent_constitution.md), so the inventory doesn't list it. This is intentional — agents and background jobs are different things.

## Consequences

- The decay worker is documented in [00 §5.3](../00_project_context.md) (mentioned implicitly) and now here.
- Operationally, it needs its own health metric (separate from cycle health).
- Deployment: it runs as a separate process; scaling is independent.
- The agent inventory in [02 §2](../02_agent_constitution.md) lists 8 agents; the decay worker is the 9th operational component, but not an "agent" in the spec sense.

## References

- [02 §A6 synthesizer](../02_agent_constitution.md) — the closest analogue (also deterministic but in the workflow)
- [01 §3 lifecycle](../01_signal_constitution.md) — `decayed` status
- [05 §3.2](../05_reasoning_framework.md) — precedent outcome recording