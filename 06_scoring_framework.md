# 06 · Scoring Framework

> **Document role:** Defines the five scoring dimensions, the composite formula, and the gating logic. Pure math + rules — independent of any specific LLM.
>
> Requires: `00_project_context.md ≥ 0.2`, `01_signal_constitution.md ≥ 0.1`, `02_agent_constitution.md ≥ 0.1`, `04_data_schema.md ≥ 1.0`, `05_reasoning_framework.md ≥ 0.1`.

---

## 1. Why Scoring Is Separate from Reasoning

| Reasoning | Scoring |
|---|---|
| Qualitative (significance, durability, causality) | Quantitative ([0, 1] floats) |
| Per-Signal judgement | Cross-Signal comparable |
| Mostly LLM-assigned | LLM assigns dimensions; **math computes composite** |
| Output: prose + structured object | Output: 5 numbers + composite + band |

This separation is deliberate: it makes the scoring **auditable, reproducible, and tunable without retraining**.

---

## 2. The Five Dimensions

All dimensions are `float[0, 1]`. All are LLM-assigned by the `scorer` agent ([02 §A5](02_agent_constitution.md)) using the rubric below.

### 2.1 Magnitude

**What it measures.** Size of the impact, in absolute and relative terms.

| Score | Guideline |
|---|---|
| 0.0–0.2 | Within routine noise |
| 0.2–0.4 | Modest; < 1σ move for the entity |
| 0.4–0.7 | Material; 1–3σ move or 1–5% of market cap |
| 0.7–1.0 | Structural; > 3σ move or > 5% of market cap, M&A-scale |

**Inputs the scorer considers:**
- Raw size of the change (dollars, share count, % of revenue, % of cap)
- Entity's recent volatility (smaller move on a high-vol stock = lower magnitude)
- Whether the change is to a strategic variable (strategy, M&A) vs operational (one quarter's KPI)

**Anti-pattern:** scoring magnitude as 1.0 just because the change is to a "big" variable. Magnitude is about size relative to baseline, not topic importance.

### 2.2 Confidence

**What it measures.** How certain we are about the claim itself (not about its impact).

| Score | Guideline |
|---|---|
| 0.0–0.3 | Speculative; source is unofficial, entity unresolved, quote mismatch |
| 0.3–0.6 | Some uncertainty; single source, secondary source, soft quote |
| 0.6–0.85 | High confidence; primary source, exact quote, multiple corroborating sources |
| 0.85–1.0 | Near-certain; primary source + direct quote + entity resolution + corroboration |

**Inputs:**
- Source quality (regulatory_filing > news_article > social_media; see [04 §5](04_data_schema.md))
- Quote match (exact > fuzzy > missing)
- Entity resolution quality (exact > fuzzy > unresolved)
- Corroboration count (independent sources saying same thing)

**Special rule** (from [05 §5](05_reasoning_framework.md)): if the analyst agent's reasoning is internally inconsistent, the analyst downgrades `confidence` by 0.2 before the scorer reads it. The scorer treats this as authoritative and does not re-evaluate reasoning quality.

### 2.3 Timeliness

**What it measures.** How urgent — does this matter right now or is it informational?

| Score | Guideline |
|---|---|
| 0.0–0.3 | Backward-looking only; historical record with no immediate consequence |
| 0.3–0.6 | Mildly time-sensitive; relevant for next session/decisions |
| 0.6–0.85 | Time-sensitive; affects current session / next decision |
| 0.85–1.0 | Breaking; pre-market, intraday catalyst, regulatory deadline today |

**Anti-pattern:** scoring timeliness high because the news is "fresh" without checking whether the impact decays quickly.

### 2.4 Novelty

**What it measures.** How new is this information relative to consensus / prior Signals on the same entity?

| Score | Guideline |
|---|---|
| 0.0–0.3 | Already known / consensus |
| 0.3–0.6 | Partially new; mixed signal vs prior |
| 0.6–0.85 | New; not in recent Signals, surprising |
| 0.85–1.0 | First-of-kind; no precedent in 12 months for this entity-type combo |

**Computation (deterministic, not LLM):**
The scorer agent may use minhash or embedding similarity against the last 90 days of Signals for the same entity. A high-similarity match (≥ 0.85) auto-caps novelty at 0.3.

**Why this matters:** without novelty penalty, every routine "in-line earnings" would crowd out actually new information.

### 2.5 Actionability

**What it measures.** Can a human act on this Signal within their decision framework?

| Score | Guideline |
|---|---|
| 0.0–0.3 | Background only; no clear decision path |
| 0.3–0.6 | Tangentially relevant; may inform but not trigger action |
| 0.6–0.85 | Actionable; could trigger a position adjustment, alert, or watchlist tier change |
| 0.85–1.0 | Highly actionable; clear thesis change, breaking event |

**Note:** "actionable" is **not** the same as "tradeable." SIGNAL does not produce trade instructions (per [00 §8](00_project_context.md)). Actionable here means "the reader's mental model should update."

---

## 3. Horizon (Signal-level, not Score-level)

`horizon` is a field on the Signal itself, not a score dimension. It describes how long the Signal's effect is expected to persist.

```
horizon ∈ enum[intraday, short, medium, long]

intraday : < 1 trading day
short    : 1–30 trading days
medium   : 30–180 trading days
long     : > 180 trading days
```

Horizon is set by the detector, not the scorer. The scorer does NOT include horizon in the composite formula — horizon affects *when* the Signal decays, not *how important* it is.

See decay rule in [01 §3](01_signal_constitution.md).

---

## 4. The Composite Formula

The composite score is **deterministic** — computed by the `compute_composite()` function, never assigned directly by an LLM. This formula is the **canonical source**; the [02 §A5](02_agent_constitution.md) catalog entry quotes the same weights without redefining them.

```python
def compute_composite(score: Score) -> float:
    return round(
        0.30 * score.magnitude
      + 0.25 * score.confidence
      + 0.20 * score.timeliness
      + 0.15 * score.novelty
      + 0.10 * score.actionability,
        4
    )
```

### 4.1 Weight Rationale

| Weight | Dimension | Why this weight |
|---|---|---|
| 0.30 | magnitude | The single most important property of a Signal |
| 0.25 | confidence | Without confidence, magnitude is speculative |
| 0.20 | timeliness | Stale info is worth less |
| 0.15 | novelty | Avoids redundant alerts |
| 0.10 | actionability | Useful but not central |

The weights are **configurable** in `config/scoring.yaml`. Changing weights is a MINOR version bump of this document.

### 4.2 Boundary Cases

| Case | Handling |
|---|---|
| Any dimension > 1 or < 0 | Clamp before composite |
| All dimensions = 0 | Composite = 0; auto-rejected at gating |
| Single dimension = 1, others = 0 | Composite ≤ 0.30; demoted at gating |
| Missing dimension | Composite cannot be computed; Signal held for review |

### 4.3 Why Not Learned Weights?

A learned-weight composite (e.g., from logistic regression) would be tempting but:
1. Loses auditability — humans cannot justify a learned weight
2. Loses stability — re-training changes the scoring of every past Signal
3. Loses interpretability — readers cannot reason about why a Signal scored high

If a future v2 wants learned weights, it should be **layered on top**, not replace this formula. Both scores reported.

---

## 5. Bands and Thresholds

Bands are categorical buckets of composite, used for gating and UI display.

```
band := composite_to_band(composite)

composite < 0.45       → band = "low"
0.45 ≤ composite < 0.65 → band = "medium"
composite ≥ 0.65       → band = "high"
```

### 5.1 Gating Thresholds (default, configurable)

| Composite | Status | Reasoning |
|---|---|---|
| ≥ 0.65 | `active` | Publish to reports and watchlist |
| 0.45 – 0.65 | `held` | Queue for curator review |
| < 0.45 | `rejected` | Auto-rejected with reason |

(See [03 §S8](03_workflow_constitution.md) for the gating stage implementation.)

### 5.2 Confidence Override

Even with composite ≥ 0.65, if `confidence < 0.30`, the Signal is **auto-rejected** with reason `low_confidence`. This prevents high-magnitude speculation from leaking through.

### 5.3 Borderline Tie-Breaker

If composite is in the borderline zone (0.45–0.65), apply the following tie-breakers in order:

1. Higher `novelty` wins
2. Then higher `timeliness`
3. Then higher `confidence`
4. Else: routed to `held`

---

## 6. Calibration Targets

The scoring framework is considered well-calibrated when:

| Metric | Target |
|---|---|
| Brier score (high-confidence) | ≤ 0.20 |
| Calibration plot slope | 0.9 – 1.1 |
| Calibration plot intercept | -0.05 – 0.05 |
| Spearman correlation (predicted vs actual impact) | ≥ 0.40 |

Calibration is measured on a **holdout set** of Signals with known outcomes (recorded post-hoc by the decay worker, [05 §3.2](05_reasoning_framework.md)).

### 6.1 Drift Detection

Weekly, the system computes:
- Distribution of each dimension (should be roughly stable)
- Distribution of bands
- Outcome-vs-prediction correlation

If any drift exceeds 2σ from the trailing 90-day baseline, an alert fires and the curator is notified.

---

## 7. Worked Example

Continuing from [05 §7](05_reasoning_framework.md):

```yaml
score:
  magnitude: 0.55
  confidence: 0.92
  timeliness: 0.80
  novelty: 0.70        # no buyback in last 90 days for ACME
  actionability: 0.75
  composite: 0.7488    # = 0.30*0.55 + 0.25*0.92 + 0.20*0.80 + 0.15*0.70 + 0.10*0.75
  band: high
  scored_at: 2026-07-16T13:14:02Z
  scored_by: { name: scorer, version: 1.4.2 }
```

Composite 0.7488 ≥ 0.65 → `active`. Confidence 0.92 > 0.30 → no override.

---

## 8. Score Modification by Curator

The curator ([02 §A8](02_agent_constitution.md)) may adjust individual dimension scores via `adjust_score` action.

Rules:
- Curator override is **appended**, not in-place — original dimension values remain in audit log
- The composite is recomputed from overridden values; the system does NOT keep a curator-set composite directly
- Reports show: `system composite: 0.75 | curator composite: 0.85` with reason

Curator adjustment range: each dimension may be adjusted by ±0.20 from system value, with reason required for adjustments > 0.10.

---

## 9. Edge Cases

| Case | Handling |
|---|---|
| Score dimensions partially missing | If ≥ 3 of 5 present, mark `score_partial: true` and use weighted sum over available dims (renormalized) |
| All dimensions 0.99 (suspicious uniformity) | Flag for review; LLM may have rubber-stamped |
| Composite exactly at threshold (e.g., 0.65) | Round UP into band; deterministic rule |
| Score recomputed after curator override | Both scores stored; `metadata.override_active: true` |
| Stored composite doesn't match formula recomputation | An integrity error; alert Operator; investigate |
| Cross-cycle score change (system rescored later) | Allowed; old + new both stored; reports show latest with delta note |

---

## 10. Anti-Patterns (Forbidden)

- ❌ LLM directly assigns composite (only the formula does)
- ❌ Composite formula depends on metadata fields not in the five dimensions
- ❌ Weights vary per Signal type (would prevent cross-type comparability)
- ❌ Score used as primary input to recommendations (out of scope per [00 §8](00_project_context.md))
- ❌ Overriding dimension scores without a reason recorded

---

## 11. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold |

Changes to the five dimensions (§2), composite formula weights (§4), or band thresholds (§5) are MAJOR. New edge cases (§9) or anti-patterns (§10) are MINOR. Wording fixes are PATCH.