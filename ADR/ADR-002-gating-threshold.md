# ADR-002: Gating Threshold = 0.65

> **Status:** accepted
> **Date:** 2026-07-16
> **Supersedes:** —
> **Superseded by:** —

## Context

A Signal with a composite score must be assigned a `status` of `active`, `held`, or `rejected`. The threshold above which a Signal becomes `active` (publishable) is the most consequential single number in the system: too low, and the report is full of noise; too high, and the system rarely publishes anything useful.

The competing concerns:

- **Reader attention** — curators and analysts have ~5 minutes per daily brief. Every published Signal competes for that attention. False positives are expensive.
- **Recall** — a missed Signal is a missed investment opportunity. The whole reason the system exists is to surface things humans would miss. False negatives are also expensive.
- **Calibration** — the threshold must align with our calibration targets in [00 §7](../00_project_context.md): ≥70% of high-confidence Signals should be corroborated within 7 days.

## Decision

We set the gating threshold at **composite ≥ 0.65 → active**. Signals in `[0.45, 0.65)` are routed to `held` for curator review; below 0.45 → `rejected`.

The threshold is **configurable** in `config/gates.yaml` and may be tuned per-environment based on observed calibration drift.

## Alternatives Considered

### 0.60
- Used in an early draft. **Rejected** because it produced too many `active` Signals at calibration targets below 70% — the daily brief became noisy.
- See the consistency pass ([REVIEW_NOTES §2.1](../REVIEW_NOTES.md)) for the conflict-resolution record.

### 0.70
- More conservative. **Rejected** because it suppressed legitimate Signals during testing; analyst review found that 0.65–0.70 band was reliably corroborated.

### 0.50
- **Rejected.** Below the empirical corroboration threshold; not justified by calibration data.

### Tier-specific thresholds
- e.g., tier_1 uses 0.60, tier_4 uses 0.70. **Rejected for v1.x** as too complex; may revisit in v1.4.

## Trade-offs

- **Gained:** high precision at the cost of some recall. Aligns with curator attention budget.
- **Gave up:** some recall at the borderline. Mitigated by the `held` queue, where curators can promote.

## Consequences

- The `held` queue must be actively managed. If curators don't process it, Signals decay without ever being reviewed. The weekly review ([13 §4](../13_report_template.md)) includes a held-queue summary.
- If calibration drifts (e.g., corroboration rate drops below 70%), the threshold must be raised. Drift detection ([06 §6.1](../06_scoring_framework.md)) triggers this.

## References

- [03 §S8](../03_workflow_constitution.md) — gating implementation
- [06 §5](../06_scoring_framework.md) — bands and thresholds
- [00 §7.1](../00_project_context.md) — calibration targets
- [REVIEW_NOTES §2.1](../REVIEW_NOTES.md) — conflict resolution with 03