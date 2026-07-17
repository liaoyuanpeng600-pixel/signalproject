# ADR-004: OverrideRecord Is Append-Only

> **Status:** accepted
> **Date:** 2026-07-16
> **Supersedes:** —
> **Superseded by:** —

## Context

The curator ([02 §A8](../02_agent_constitution.md)) is the only agent that accepts human input. When a curator adjusts a Signal's score, marks it noise, or changes a watchlist tier, this action must be **auditable**.

The fundamental tension:

- **Auditability** requires that we can reconstruct what the system looked like before and after any human action.
- **Simplicity** of consumer code would prefer a single "current value" view.

A destructive override (curator edits the Signal in place) loses the system-computed value forever. This is unacceptable for:
1. Compliance review (auditor needs to see what the system said, then what the curator said).
2. Calibration research (we need to know whether curator overrides improved outcomes vs system scores).
3. Bug investigation (was this Signal rejected because the system got it wrong, or because the curator overruled a correct system score?).

## Decision

`OverrideRecord` is **append-only**. The system-computed value is never overwritten. Downstream consumers may apply the override (via `metadata.override_active = true`) but the original value remains in the Signal's `Provenance.override_records[]`.

The complete enum of override actions lives in [04 §6 OverrideRecord.action](../04_data_schema.md) (8 actions).

## Alternatives Considered

### In-place edits
- **Rejected.** Destroys history. Cannot audit, cannot rollback, cannot research curator quality.

### Soft-delete + replace
- Mark old Signal as `superseded`, create new Signal with curator's value.
- **Rejected for v1.x.** Loses the lineage; signals are conceptually the same claim.
- Reconsidered in [ADR-005](ADR-005-superseded-status.md) for the same-event clustering case.

### Dual-store (system + curator)
- Two Signal stores: `signal_system` and `signal_curator`. Joins at read time.
- **Rejected.** Adds complexity for marginal gain; append-only is simpler.

## Trade-offs

- **Gained:** full auditability, ability to revert, ability to analyze curator quality.
- **Gave up:** consumer code must sometimes apply override logic; storage grows linearly with overrides.

## Consequences

- INV-11 enforces this at the database level (append-only triggers).
- Downstream consumers (reports, UI) MUST check `metadata.override_active` and apply overrides.
- Calibration dashboards MUST distinguish "system composite" from "curator composite" — this is already implemented in [06 §8](../06_scoring_framework.md) and [13 §2.4](../13_report_template.md).
- Storage: every override adds ~200 bytes. Expected volume: ~50 overrides/day → ~3.6 MB/year → negligible.

## References

- [02 §A8](../02_agent_constitution.md) — curator agent
- [04 §6 OverrideRecord](../04_data_schema.md) — schema
- [06 §8](../06_scoring_framework.md) — curator score modification
- [14 §9](../14_watchlist.md) — curator sessions
- [INV-11](../INVARIANTS.md) — append-only invariant