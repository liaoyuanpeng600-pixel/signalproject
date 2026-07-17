# ADR-005: `superseded` as a Lifecycle Status

> **Status:** accepted
> **Date:** 2026-07-16
> **Supersedes:** —
> **Superseded by:** —

## Context

In the dedup logic ([01 §4](../01_signal_constitution.md)), two Signals on the same entity with near-identical claims within 24h are collapsed: the higher-score one is kept; the other is marked.

The question is: what is the status of the lower-score one?

Options:

- **`rejected`** — implies the system thinks it's wrong.
- **Delete** — loses the record.
- **New status `superseded`** — "this was valid, but a better version exists."

The cardinality rule (same-claim 24h) fires when **both** Signals are valid; the kept one just happens to score higher. So `rejected` is semantically wrong — the Signal wasn't bad, it was redundant.

## Decision

We add `superseded` to the Signal lifecycle enum ([01 §3](../01_signal_constitution.md), [04 §4.1](../04_data_schema.md)).

A Signal transitions to `superseded` when:

- A newer Signal on the same entity with near-identical claim exists (per [01 §4](../01_signal_constitution.md) rule 1).
- A newer Signal supersedes it as the primary in a same-event cluster (per [01 §4](../01_signal_constitution.md) rule 2).

The transition is made by the `dedup` stage between S4 and S5, or by the `decay_worker` when a same-event cluster forms.

## Alternatives Considered

### Use `rejected` with a `superseded_by` metadata field
- **Rejected.** Conflates "rejected" with "valid but replaced". Downstream filtering by `status=rejected` would lose valid Signals.

### Hard delete
- **Rejected.** Loses audit trail; a curator might want to see what was superseded.

### New status `archived`
- Considered; `archived` is too vague. `superseded` is precise about the cause.

### Mark in metadata only (`metadata.superseded_by`)
- **Rejected.** Easier to miss; harder to filter. A dedicated status is more discoverable.

## Trade-offs

- **Gained:** accurate semantic of "valid but replaced"; clean filtering by status.
- **Gave up:** one more status value; one more transition to validate.

## Consequences

- INV-6 (lifecycle valid) updated to include `superseded` transitions.
- Reports may show `superseded` Signals in a "previous signals" section, but default to hiding them.
- Calibration can include superseded Signals as a "we considered this, but a better version exists" category.
- Storage: superseded Signals are retained for audit (per [09 §11](../09_development_roadmap.md) migration policy).

## References

- [01 §3](../01_signal_constitution.md) — lifecycle enum
- [01 §4](../01_signal_constitution.md) — cardinality rules
- [04 §4.1 Signal.status](../04_data_schema.md) — schema
- [INV-6](../INVARIANTS.md) — lifecycle transition invariant
- [REVIEW_NOTES §3.1](../REVIEW_NOTES.md) — drift fix that added this status