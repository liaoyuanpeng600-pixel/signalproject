# 05 · Reasoning Framework

> **Document role:** Defines how the `analyst` agent reasons about a Signal's significance, causality, durability, and precedent. Pure methodology — independent of model choice.
>
> Requires: `00_project_context.md ≥ 0.2`, `01_signal_constitution.md ≥ 0.1`, `02_agent_constitution.md ≥ 0.1`, `04_data_schema.md ≥ 1.0`.

---

## 1. Why Reasoning Is Its Own Layer

A Signal is a **claim about change**. To be useful, it must answer four implicit questions:

1. **Does it matter?** (significance)
2. **What does it cause?** (causality)
3. **How long does it last?** (durability)
4. **What usually happens next?** (precedent)

Detection tells us *what happened*. Scoring tells us *how confident we are*. Reasoning tells us *what it means*.

---

## 2. The Four Reasoning Tasks

### 2.1 Significance

**Definition.** How material is the change relative to the entity's size, prior volatility, and industry baseline?

```
significance ∈ [0, 1]

Guidelines (NOT a formula; the analyst LLM assigns):
- 0.0–0.2  : within routine noise band (e.g., 1% price move on a high-vol stock)
- 0.2–0.4  : notable but expected (e.g., in-line guidance)
- 0.4–0.7  : material (e.g., beat by > 5%, new product announcement)
- 0.7–1.0  : structural (e.g., CEO departure, M&A, regulatory action)
```

**Inputs considered:**
- Magnitude relative to entity's recent range
- Whether the event is within analyst consensus or outside it
- Whether the change is to a strategic vs operational variable
- Industry context (see [11_industry_mapping.md](11_industry_mapping.md))

**Anti-patterns:**
- Inflating significance for novel events regardless of magnitude
- Deflating significance for "boring" event types
- Using only absolute magnitude (always relative)

### 2.2 Causality

**Definition.** What downstream effects can this plausibly cause, on what entities, via what mechanism, with what probability?

```
CausalLink := {
  to_entity     : EntityRef,
  mechanism     : string,        // ≤ 280 chars, concrete causal claim
  likelihood    : enum[low, medium, high],
  time_horizon  : enum[intraday, short, medium, long]
}
```

**Process.**
1. Identify the **immediate** direct effect on the entity itself
2. Identify **second-order** effects on related entities (suppliers, customers, competitors — see [11_industry_mapping.md](11_industry_mapping.md))
3. For each, specify the mechanism in plain language
4. For each, assign likelihood (low = speculative, medium = plausible, high = highly probable)
5. Cap at 5 CausalLinks per Signal (more dilutes focus)

**Likelihood rubric:**

| Likelihood | Definition |
|---|---|
| `low` | Speculative; would require multiple additional events to manifest |
| `medium` | Plausible; mechanism is concrete but contingent on intermediate steps |
| `high` | Highly probable; mechanism is direct and well-established |

**Anti-patterns:**
- Causality chains beyond 3 hops (model accuracy collapses)
- Mechanism stated as "may affect" (non-falsifiable — disallowed)
- Linking to entities without an industry-chain relationship

### 2.3 Durability

**Definition.** How long is the effect likely to persist?

```
durability ∈ enum[transient, short, structural]

transient : < 1 trading day
short     : 1–30 trading days
structural: > 30 trading days
```

**Rubric:**

| Class | Typical events |
|---|---|
| `transient` | Single-day price spike on rumor, intraday volume spike |
| `short` | One earnings cycle, one quarter's guidance, one product launch window |
| `structural` | Regulatory change, CEO/strategy change, M&A, business model shift |

**Tie-breakers:**
- If reversible easily → downgrade one tier
- If officially confirmed → upgrade one tier
- The `horizon` field in Signal metadata should align with durability but is not required to

### 2.4 Reversibility

**Definition.** How easily could this change be undone?

```
reversibility ∈ enum[irreversible, hard, easy]

irreversible : M&A close, business divestiture, regulatory ban
hard         : Strategy pivot, large capex, multi-year contract
easy         : Guidance revision, hiring, single-quarter decision
```

**Why reversibility is separate from durability:**
- An M&A close is **structural AND irreversible**
- A guidance cut is **short AND easy** (just guide up next quarter)
- A regulatory change is **structural AND hard** (multi-year to repeal)

Both fields together give a richer picture than either alone.

---

## 3. Precedent Matching

**Definition.** Has a similar Signal on a comparable entity played out before?

```
PrecedentRef := {
  signal_id    : ULID,
  similarity   : float[0, 1],
  outcome      : string
}
```

### 3.1 Similarity Score

Similarity is a composite of:
- **Type match** (same `type` in taxonomy, see [10](10_signal_taxonomy.md)): weight 0.4
- **Direction match**: weight 0.2
- **Magnitude similarity** (within 0.2): weight 0.2
- **Entity context similarity** (same sector or industry chain): weight 0.2

A precedent with `similarity < 0.6` is excluded.

### 3.2 Outcome

`outcome` is recorded **post-hoc** by the decay worker:
- After 30 days, the decay worker queries outcomes (price action, subsequent filings) and writes a `PrecedentOutcome` record
- This creates a closed feedback loop that improves future reasoning

### 3.3 Why This Matters

Without precedent, every Signal is judged in isolation — leading to over- or under-weighting common patterns. With precedent, the system learns "earnings beats of this magnitude in this sector historically produce X% price drift over 30 days."

---

## 4. Reasoning Prompt Contract

The analyst agent's prompt MUST follow [07_prompt_guidelines.md](07_prompt_guidelines.md) and additionally:

1. Receive the Signal's claim, evidence, entity context, and recent entity Signals (last 30 days)
2. Be instructed to output **exactly** the JSON shape of the `Reasoning` schema ([04 §8](04_data_schema.md))
3. Be instructed to **never invent** precedents — only reference Signals in the provided recent list
4. Be instructed to **justify** each CausalLink with a concrete mechanism
5. Have a one-liner summary in plain English (used by the reporter)

### 4.1 Anti-patterns the prompt must forbid

- "This could affect..." without a mechanism
- Listing entities without industry-chain relationship
- Speculating on price targets
- Using words like "significant" without quantifying
- Inventing precedents not in the provided list

---

## 5. Confidence Calibration

Reasoning affects `confidence` on the Score ([04 §7](04_data_schema.md), [06 §2](06_scoring_framework.md)).

**Rule:** if the analyst's reasoning is internally inconsistent or evidence is thin, confidence is downgraded by 0.2.

**Reasoning quality signals:**
- All CausalLinks have concrete mechanisms (not vague)
- Durability/reversibility combination is internally consistent
- Precedents cited have similarity ≥ 0.6
- One-liner summary ≤ 140 chars and contains a number or fact

**Calibration target:** among Signals with `confidence ≥ 0.7`, ≥ 70% should be corroborated within 7 days (see [00 §7.1](00_project_context.md)).

---

## 6. Edge Cases

| Case | Handling |
|---|---|
| Recent entity Signals unavailable (cold start) | Use industry-level precedents instead; mark `metadata.precedent_basis: industry` |
| Entity context too large to fit in prompt | Summarize via `summarizer` function before reasoning; record summary hash in provenance |
| LLM produces malformed Reasoning JSON | Retry once with stricter prompt; if still fails, mark `reasoning_skipped: true` and route to curator |
| Multiple precedent clusters conflict | Pick the higher-similarity cluster; document the conflict in `metadata.precedent_conflict: true` |
| Reasoning contradicts itself | Auto-flag for curator review; do not auto-publish |

---

## 7. Worked Example

### Input

```yaml
signal:
  id: 01HXY...
  entity_ref: { kind: company, id: ACME.US }
  type: capital_action
  claim: "ACME announced a $500M share buyback program, ~3.2% of market cap."
  direction: bullish
  horizon: short
  evidence:
    - source_url: "https://www.sec.gov/.../8-k.htm"
      quote: "The Board authorized a $500 million share repurchase program."
evidence_summary:
  - direct quote from primary regulatory filing
recent_signals_ACME_US:
  - { type: earnings, direction: bullish, score_composite: 0.71, detected_at: 2026-05-02 }
  - { type: guidance, direction: bullish, score_composite: 0.68, detected_at: 2026-05-02 }
industry_chain:
  sector: Technology
  upstream: [...]
  downstream: [...]
```

### Output (analyst)

```yaml
reasoning:
  significance: 0.55
  causality:
    - to_entity: { kind: company, id: ACME.US }
      mechanism: "Reduces share count by ~1.2% on average; supports EPS by similar magnitude over 12 months."
      likelihood: high
      time_horizon: medium
    - to_entity: { kind: company, id: ACME.US }
      mechanism: "Signals management confidence in cash flow generation and undervaluation."
      likelihood: high
      time_horizon: short
    - to_entity: { kind: sector, id: TECHNOLOGY }
      mechanism: "Sector-wide capital return trend; ACME's move reinforces."
      likelihood: medium
      time_horizon: medium
  durability: short
  reversibility: hard
  precedents:
    - signal_id: 01HW2...     # ACME 2024 buyback
      similarity: 0.88
      outcome: "5.2% price appreciation in 30 days; subsequent earnings beat"
    - signal_id: 01HV9...     # peer ZZZ 2025 buyback
      similarity: 0.71
      outcome: "3.1% price appreciation in 30 days"
  one_liner: "$500M buyback (~3% of mcap) signals mgmt confidence; historical peers averaged ~4% upside in 30d."
```

This Reasoning field then flows into the `scorer` agent ([02 §A5](02_agent_constitution.md)).

---

## 8. Why Not Just Let the LLM Free-Form?

The temptation to skip structured reasoning and let the LLM write a paragraph is real — and wrong, for three reasons:

1. **Auditability** — structured fields can be queried, filtered, and aggregated; prose cannot
2. **Consistency** — every Signal has comparable dimensions across the corpus
3. **Replay** — structured fields reproduce bit-identically (with temperature=0); prose does not

The analyst's prose output is supplementary; the structured `Reasoning` object is the deliverable.

---

## 9. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold |

Changes to the four reasoning tasks (§2), the precedent rubric (§3), or the worked example (§7) are MAJOR. New anti-patterns (§4.1) are MINOR. Wording clarifications are PATCH.