# ADR-003: Composite Formula Weights

> **Status:** accepted
> **Date:** 2026-07-16
> **Supersedes:** —
> **Superseded by:** —

## Context

The composite score is the weighted sum of five dimensions: magnitude, confidence, timeliness, novelty, actionability. The weights determine how much each dimension influences whether a Signal becomes `active`.

The key constraint ([06 §4.3](../06_scoring_framework.md)) is **interpretability**: a human must be able to explain why a Signal scored high. This rules out learned weights.

## Decision

```
composite = 0.30 * magnitude
         + 0.25 * confidence
         + 0.20 * timeliness
         + 0.15 * novelty
         + 0.10 * actionability
```

Weights are configurable but default to the above. They MUST sum to 1.0 (INV-12).

## Alternatives Considered

### Equal weights (0.20 each)
- **Rejected.** Confidence and magnitude matter more than novelty or actionability; equal weights over-weight noise dimensions.

### Confidence-dominant (0.50 confidence)
- **Rejected.** A high-confidence claim with low magnitude (e.g., "Apple's CEO ate lunch") would dominate.

### Magnitude-dominant (0.50 magnitude)
- **Rejected.** Magnitude without confidence is speculation.

### Learned weights
- **Rejected.** Violates interpretability. See [06 §4.3](../06_scoring_framework.md).

### Dimension-specific weights per signal type
- **Rejected.** Cross-Signal comparability would be lost; can't rank "an earnings beat" vs "a regulatory approval" with type-dependent weights.

## Trade-offs

- **Gained:** interpretability; tunable; auditable; can be re-tuned without retraining.
- **Gave up:** sub-optimal weights for any specific signal type. We accept this for cross-type comparability.

## Consequences

- Weights may need re-tuning as calibration data accumulates. The drift detection ([06 §6.1](../06_scoring_framework.md)) flags when this is needed.
- Future v2 may add **layered** learned weights on top of the deterministic formula (both scores reported), per [06 §4.3](../06_scoring_framework.md).
- Anyone can explain to a curator why a Signal scored 0.85: "0.30 * 0.90 (high magnitude) + 0.25 * 0.95 (high confidence) + ..."

## References

- [06 §4](../06_scoring_framework.md) — formula and rationale
- [04 §7](../04_data_schema.md) — Score schema
- [INV-12](../INVARIANTS.md) — composite weight sum invariant