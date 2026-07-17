# ADR-001: 9-Stage Pipeline Design

> **Status:** accepted
> **Date:** 2026-07-16
> **Supersedes:** —
> **Superseded by:** —

## Context

The SIGNAL ingest pipeline must turn raw source data into published Signals. The natural tension is:

- **More stages** = more validation, more accurate scoring, more context — but slower, more failure modes, harder to debug.
- **Fewer stages** = faster, simpler — but lower quality output, harder to debug failures.

We needed a stage decomposition that:
1. Separates **deterministic** transformations (cheap, no LLM) from **probabilistic** ones (LLM).
2. Makes every stage's failure mode independent.
3. Allows per-tier skipping (tier_3 / tier_4 don't need full reasoning).

## Decision

We use a **9-stage pipeline** for the `ingest_cycle` workflow (W1):

```
S1 Harvest → S2 Normalize → S3 Dedup → S4 Detect → S5 Verify
              → S6 Reason → S7 Score → S8 Gating → S9 Persist
```

- S2, S3, S8, S9 are **deterministic functions** (no LLM).
- S1, S4, S5, S6, S7 are **agents** (may invoke LLM).
- Synthesis (W3) and Reporting (W4) are **separate workflows**, not stages in the ingest cycle.

## Alternatives Considered

### 7-stage pipeline
- Combine S2+S3 into "process", and S8+S9 into "publish".
- **Rejected:** lost the ability to dedup before detection (wasted LLM calls on duplicates) and to gate before persist (wasted writes).

### 10-stage pipeline
- Split S7 Score into "score_dimensions" and "compute_composite" as separate stages.
- **Rejected:** the composite computation is a deterministic function and runs inline with the LLM-assigned dimensions in S7. Splitting them adds a stage without adding information.

### Single mega-agent
- One LLM call that does detect+verify+reason+score.
- **Rejected:** violates P4 (deterministic glue, probabilistic brain). Cannot debug partial failures, cannot version each piece independently, cannot tune verification without retraining detection.

### Separate workflows for synthesis and reporting
- **Adopted.** W3 `synthesis_cycle` and W4 `report_cycle` are independent from W1, triggered on different cadences.

## Trade-offs

- **Gained:** clear separation of concerns, each stage independently testable, deterministic stages can be cached, per-tier stage-skipping is straightforward.
- **Gave up:** slightly more wiring; stage boundaries add coordination cost.

## Consequences

- Easier to reason about: each stage has one responsibility.
- Easier to test: each stage can be tested with synthetic input.
- Easier to scale: stages can be parallelized within their bounds.
- Future stages can be added without breaking the graph (just bump 03 to a new MAJOR).

## References

- [03 §3](../03_workflow_constitution.md) — stage catalog
- [00 §5.1](../00_project_context.md) — pipeline table
- [02 §1](../02_agent_constitution.md) — agent vs function distinction