# 13 · Report Template

> **Document role:** Output format specification for every report SIGNAL emits. Defines structure, required sections, ground rules for prose, and a worked example. Authoritative for the `reporter` agent.
>
> Requires: `00_project_context.md ≥ 0.2`, `01_signal_constitution.md ≥ 0.1`, `04_data_schema.md ≥ 1.0`.

---

## 1. Why a Template

A report that does not follow a template is:
- Hard to scan (variable structure)
- Hard to compare across days
- Hard to audit (no fixed fields)
- Easy to fabricate (prose can drift from data)

Every SIGNAL report **conforms** to one of three templates defined here:
- Daily Brief
- Weekly Review
- Per-Entity Brief

Ad-hoc reports are not permitted in v1.x.

---

## 2. Universal Rules (Apply to All Reports)

These rules apply regardless of report type.

### 2.1 Grounding

Every fact in a report **must** reference a Signal ID. No orphan facts.

```
Bad:  "ACME had a strong quarter."
Good: "ACME had a strong quarter [sig_01HXY...], with EPS beating by 14%."
```

### 2.2 No Inventions

The reporter agent **must not** add facts not present in the underlying Signals. If a section cannot be filled from available data, omit it (do not invent).

### 2.3 Neutrality

Reports **do not** contain buy/sell language, target prices, or position recommendations (per [00 §8](00_project_context.md)). They surface evidence and let humans decide.

### 2.4 Provenance Footer

Every report ends with a footer listing:
- Cycle IDs covered
- Agent versions used
- Prompt versions used
- Degrade mode status (if any)
- Coverage gaps (entities with zero Signals in window)

### 2.5 Citation Format

Inline citations use a short format: `[sig:01HXY...]` for individual Signals or `[thesis:01HW2...]` for ThesisDeltas. The full provenance is in the JSON companion file.

### 2.6 Length Caps

| Section type | Max length |
|---|---|
| Headline | 100 chars |
| Per-entity summary | 280 chars |
| Per-cluster narrative | 500 chars |
| Daily Brief total | 5,000 words |
| Weekly Review total | 15,000 words |

A section that exceeds its cap is a prompt bug; report is rejected and re-rendered.

### 2.7 Banned Words

The reporter prompt enforces a denylist. These phrases **must not** appear in any output:

- "We recommend..." / "We suggest buying/selling..."
- "Target price: $X"
- "Significantly" without a number
- "Game-changer", "moon", "rocket" (and other hype terms)
- "Strong quarter" (too vague — use "EPS +14% vs consensus")
- "Buy", "Sell", "Hold" as verbs on a position
- "Definitely", "certainly" (overconfident without warrant)

The denylist is enforced by a post-generation regex check.

---

## 3. Daily Brief

### 3.1 Purpose

A morning snapshot of what changed in the watchlist overnight and pre-market. Designed to be read in 5–10 minutes.

### 3.2 Cadence

- Generated at 06:30 ET (pre-US-market open)
- Window covered: previous US close → 06:25 ET
- Plus an end-of-day version at 16:30 ET

### 3.3 Sections

```
# Daily Brief — <DATE>

## 1. Top Movers (by composite score)
[Top 5 Signals by composite, each with claim + 1-sentence impact]

## 2. Watchlist Activity
[Per-entity 1-line summary for any entity with ≥ 1 Signal in window]

## 3. Cluster View
[Each cluster (≥ 3 Signals, same entity, 24h): narrative + entity]

## 4. Industry / Macro
[Non-entity Signals affecting watchlist; cascade implications]

## 5. Decay Watch
[Signals about to decay in next 48h; reminder for review]

## 6. Provenance
[Cycle IDs, agent versions, degrade mode status, coverage gaps]
```

### 3.4 Section Specifications

#### §1 Top Movers

```markdown
## 1. Top Movers

| Rank | Signal | Entity | Composite | Band | Source |
|------|--------|--------|-----------|------|--------|
| 1 | [sig:01HXY...] | ACME.US | 0.92 | high | 8-K |
| 2 | [sig:01HW2...] | BETA.US | 0.85 | high | earnings_call |
| ... |
```

Followed by a short prose paragraph per top-3 Signal explaining the impact in plain English (1–2 sentences).

#### §2 Watchlist Activity

```markdown
## 2. Watchlist Activity

- **ACME.US** (Tier 1): 3 Signals — buyback announcement [sig:01HXY...], CFO change [sig:01HXZ...], Q2 preview [sig:01HY1...]. Net direction: bullish.
- **BETA.US** (Tier 1): 1 Signal — guidance cut [sig:01HW2...]. Net direction: bearish.
- **GAMMA.TW** (Tier 3): No Signals. Last activity: 2026-06-30.
```

#### §3 Cluster View

```markdown
## 3. Cluster View

### Cluster cluster_abc — ACME.US (3 Signals, last 24h)
> Primary signal [sig:01HXY...]: ACME acquiring XYZ for $2.3B.
> Supporting [sig:01HXZ...]: CFO to lead integration; XYZ CEO departing.
> Supporting [sig:01HY1...]: $80M expected synergies by Y3.

Net direction: bullish (M&A-driven growth, with execution risk).
```

#### §4 Industry / Macro

```markdown
## 4. Industry / Macro

- Fed held rates [sig:01HM1...] — neutral for Tech, slight negative for REITs.
- EU semis inventory 92 days [sig:01HN3...] — bearish for downstream OEMs [causal:cluster_abc].
```

#### §5 Decay Watch

```markdown
## 5. Decay Watch

The following Signals will decay within 48h and require re-review:
- [sig:01H8Y...] (ACME.US, earnings) — set 2026-04-30, horizon=short, expires 2026-07-18
- ...
```

If empty: "No Signals scheduled for decay in next 48h."

#### §6 Provenance

```markdown
## 6. Provenance

- Window: 2026-07-15T16:30:00Z – 2026-07-16T13:25:00Z
- Cycles covered: 01HXA..., 01HXB..., 01HXC..., 01HXD... (ULIDs per [03 §8.2](03_workflow_constitution.md))
- Detector: v1.4.2 (claude-opus-4-8)
- Scorer: v1.2.0
- Reasoning: v0.3.1
- Degrade mode: inactive
- Coverage gaps: GAMMA.TW (Tier 3) — no Signals in 14d, review needed
```

### 3.5 Worked Example (abbreviated)

```markdown
# Daily Brief — 2026-07-16

## 1. Top Movers

| Rank | Signal | Entity | Composite | Band | Source |
|------|--------|--------|-----------|------|--------|
| 1 | [sig:01HXY...] | ACME.US | 0.92 | high | 8-K |

ACME announced a $500M share buyback [sig:01HXY...], ~3.2% of market cap, signaling management confidence in cash flow. Two similar historical buybacks averaged 4.1% price appreciation within 30 days.

## 2. Watchlist Activity
- **ACME.US** (Tier 1): 1 Signal — buyback. Net direction: bullish.
- (other entities omitted for brevity)

## 6. Provenance
- Window: 2026-07-15T16:30:00Z – 2026-07-16T13:25:00Z
- Cycles: cycle_01HXD
- Detector: v1.4.2
- Degrade mode: inactive
- Coverage gaps: none
```

---

## 4. Weekly Review

### 4.1 Purpose

A retrospective on the week's Signals: what played out, what was calibrated correctly, what wasn't. Designed for Curator and Reader to evaluate system quality.

### 4.2 Cadence

- Generated Friday at 17:00 ET (post-US-close)

### 4.3 Sections

```
# Weekly Review — Week of <DATE>

## 1. Headline Statistics
[Volume, calibration, cost summary]

## 2. Top 10 Signals of the Week
[Highest-composite Signals of the week, ranked]

## 3. Calibration Report
[Brier score, corroboration rate, by band]

## 4. Watchlist Movement
[Entities with most Signal activity; tier-change recommendations]

## 5. Source Performance
[Per-source yield: Signals per day, calibration by source]

## 6. Failure Post-Mortem
[Significant failures: missed Signals, false positives, processing errors]

## 7. Curator Actions
[Override summary, tier changes, marks]

## 8. Next Week Lookahead
[Scheduled catalysts, expected earnings, known events]

## 9. Provenance
```

### 4.4 Section Specifications

#### §1 Headline Statistics

```markdown
## 1. Headline Statistics

| Metric | This Week | Last Week | Trend |
|---|---|---|---|
| Signals emitted (active) | 312 | 287 | ↑ |
| Median composite | 0.62 | 0.61 | → |
| Calibration (Brier) | 0.18 | 0.19 | ↓ better |
| Corroboration rate (high-confidence) | 73% | 71% | ↑ |
| Cost per Signal | $0.27 | $0.29 | ↓ |
| Watchlist entities with 0 Signals | 12 | 18 | ↓ |
```

#### §3 Calibration Report

Table by composite band:

| Band | Count | Corroboration Rate | Avg Return (T+30d) |
|---|---|---|---|
| high (≥0.65) | 47 | 73% | +2.1% |
| medium (0.45–0.65) | 81 | 52% | +0.4% |
| low (<0.45) | 184 | 38% | -0.1% |

Plus a brief interpretation: "Calibration remains within target. The medium band is below the 60% target — consider raising the medium→high threshold by 0.05."

#### §6 Failure Post-Mortem

```markdown
## 6. Failure Post-Mortem

### Missed Signal
- **Date:** 2026-07-12
- **What:** XYZ.US announced 10% workforce reduction at 16:02 ET, missed by detector
- **Why:** Press release arrived 3 minutes after cycle window closed; next cycle picked it up but with 4h delay
- **Fix:** Burst trigger to be retuned; threshold for "workforce reduction" keyword lowered

### False Positive
- **Date:** 2026-07-14
- **Signal:** [sig:01HK3...] claimed regulatory approval
- **What actually happened:** Announcement was a clinical-trial milestone, not approval
- **Why:** Detector conflated "milestone" with "approval"
- **Fix:** Add explicit prompt constraint: "regulatory approval requires agency action, not company announcement"
```

---

## 5. Per-Entity Brief

### 5.1 Purpose

A focused report on a single entity, useful for onboarding a new entity to the watchlist or refreshing coverage after a quiet period.

### 5.2 Cadence

- On-demand (Curator or Reader request)
- Auto-generated when entity enters Tier 1 or 2

### 5.3 Sections

```
# Entity Brief — <TICKER> — <DATE>

## 1. Identity
[Name, exchanges, classification, financials snapshot]

## 2. Last 90 Days — Signals
[All active Signals in last 90 days, ranked]

## 3. Last 90 Days — ThesisDelta Summary
[Most recent ThesisDelta if any; otherwise "No clusters in 90d"]

## 4. Industry Position
[Chain nodes + key edges]

## 5. Historical Calibration
[Past Signal outcomes for this entity; corroboration rate]

## 6. Watchlist Tier Recommendation
[System recommendation; Curator action]

## 7. Provenance
```

### 5.4 Section Specifications

#### §1 Identity

Pulls from Company master ([12_company_schema.md](12_company_schema.md)). One line per field. No prose.

```markdown
## 1. Identity

| Field | Value |
|---|---|
| Name | ACME Corporation |
| Ticker | ACME (US) |
| Sector | Information Technology / Semiconductors |
| Market Cap | $15.6B (as of 2026-07-15) |
| CEO | Jane Smith (since 2022-04-01) |
| Industry Positions | wafer-fab (85%), foundry-service (15%) |
```

#### §5 Historical Calibration

For this entity, over the last 12 months:

```markdown
## 5. Historical Calibration

| Metric | Value |
|---|---|
| Total Signals emitted | 87 |
| Active Signals | 76 |
| Corroborated (within 7d) | 58 / 76 (76%) |
| Avg composite | 0.61 |
| Most-cited Signal type | earnings (35% of total) |
```

---

## 6. JSON Companion

Every report has a JSON sidecar with machine-readable content:

```json
{
  "report_type": "daily_brief",
  "report_id": "ULID",
  "generated_at": "ISO8601",
  "window": { "start": "ISO8601", "end": "ISO8601" },
  "cycle_ids": ["ULID", ...],
  "agent_versions": { "detector": "v1.4.2", ... },
  "degrade_mode_active": false,
  "sections": [
    {
      "section_id": "top_movers",
      "items": [
        { "signal_id": "ULID", "composite": 0.92, "rank": 1, ... }
      ]
    },
    ...
  ]
}
```

The JSON is the source of truth for the UI; the markdown is the human-readable view.

---

## 7. Reporter Prompt Contract

The `reporter` agent prompt ([02 §A7](02_agent_constitution.md)) MUST:

1. Receive the filtered Signals, ThesisDeltas, and watchlist state
2. Output strictly per the chosen template structure
3. Include `[sig:...]` and `[thesis:...]` citations on every fact
4. Obey length caps (§2.6)
5. Obey banned-word list (§2.7)
6. Output raw markdown (no surrounding explanation)

A post-generation validator checks:
- All sections present
- All claims have citations
- No banned words
- Length caps respected
- Provenance footer complete

Reports that fail validation are **not delivered**; the agent retries once with stricter instructions.

---

## 8. Edge Cases

| Case | Handling |
|---|---|
| Zero Signals in window | Daily Brief still generated with empty §1–§3, plus explanation in §2 that all entities are quiet |
| Massive Signal volume (e.g., 100+ in a day) | Cap at top 10 by composite; mention count in §1 |
| All entities in degrade mode | Add banner to top of report: "Generated in degrade mode — reasoning skipped on N Signals" |
| Cluster spans multiple entities | Place in §4 Industry / Macro, not §3 Cluster View |
| Curator override during report window | Show both system and override values where relevant; flag in §7 of weekly |
| Report fails validation | Alert Operator; manual regeneration required |

---

## 9. Future Templates

Reserved for v2.x:

- **Pre-earnings preview** — Signals aggregated in the 7 days before an earnings event
- **Sector deep-dive** — multi-entity report on a sector (≥ 10 entities)
- **Crisis post-mortem** — generated after a market shock
- **Causal cascade** — generated when a cross-entity contagion is detected

---

## 10. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold |

Adding a new report template is MAJOR. Adding sections to an existing template is MINOR (requires Curator acceptance). Wording clarifications are PATCH.