# 10 · Signal Taxonomy

> **Document role:** Closed enumeration of every Signal type SIGNAL recognizes. Defines what each type means, typical examples, expected evidence, and typical direction. Authoritative for the `type` field on Signals.
>
> Requires: `00_project_context.md ≥ 0.2`, `01_signal_constitution.md ≥ 0.1`, `04_data_schema.md ≥ 1.0`.

---

## 1. Why a Taxonomy

Without a closed set of types:
- Detection prompts cannot be specific
- Cross-Signal analytics are impossible
- Reports cannot group meaningfully
- Scoring rubrics vary per type, breaking comparability

A type is added only when **all** of:
1. The category has at least 5 historical examples in real markets
2. The category has a distinct evidence pattern
3. The category requires different reasoning from existing types
4. Operators agree it is worth the schema complexity

A type is removed only when its usage falls below 0.1% of total Signals for 6 consecutive months.

---

## 2. Top-Level Categories

SIGNAL defines **ten** top-level categories. Each is a closed enum value used as `type` on the Signal.

| Code | Name | Typical source |
|---|---|---|
| `earnings` | Earnings / Financial Results | Earnings releases, transcripts |
| `guidance` | Forward Guidance / Outlook | Earnings calls, press releases |
| `capital_action` | Capital Actions | 8-K filings, press releases |
| `management` | Management Changes | 8-K, news |
| `operational` | Operational KPIs | Press releases, conference talks |
| `industry` | Industry / Sector | Industry reports, news |
| `macro` | Macro Variables | Government data, central bank |
| `regulatory` | Regulatory / Legal | SEC, FDA, agency filings |
| `sentiment` | Sentiment Shift | Survey data, social, news tone |
| `catalyst` | Discrete Event Catalysts | Calendar, announcements |

The codes are the `type` enum values. Names are for human reading.

---

## 3. Type Specifications

Each type follows the same template:

```
Type := {
  code        : enum_string,
  name        : human_readable,
  definition  : one sentence,
  typical_evidence_source_types : [enum],
  typical_direction_distribution : { bullish, bearish, neutral, mixed },
  typical_horizon                : enum[intraday, short, medium, long],
  default_durability             : enum[transient, short, structural],
  precedent_richness             : enum[high, medium, low],  // for reasoning
  examples                       : [string],
  anti_examples                  : [string]   // things that LOOK like this type but are not
}
```

---

### 3.1 `earnings`

| Field | Value |
|---|---|
| **Definition** | A discrete reported financial result (revenue, EPS, margin) that differs materially from consensus or prior period. |
| **Typical evidence** | `regulatory_filing` (10-Q, 10-K, 6-K), `earnings_call`, `press_release` |
| **Typical directions** | bullish 50%, bearish 40%, neutral 10% |
| **Typical horizon** | short |
| **Default durability** | short |
| **Precedent richness** | high |
| **Examples** | "ACME reported Q2 EPS of $1.20 vs consensus $1.05 (+14%)." |
| **Anti-examples** | Forward guidance (use `guidance`); operational KPIs like DAU (use `operational`); macro CPI release (use `macro`). |

### 3.2 `guidance`

| Field | Value |
|---|---|
| **Definition** | A company-provided forward-looking range or qualitative direction for future financial performance. |
| **Typical evidence** | `earnings_call`, `press_release`, `regulatory_filing` (8-K with outlook) |
| **Typical directions** | bullish 30%, bearish 30%, neutral 40% |
| **Typical horizon** | medium |
| **Default durability** | short |
| **Precedent richness** | high |
| **Examples** | "ACME guided FY revenue to $5.0–5.2B vs prior $5.3–5.5B." |
| **Anti-examples** | Actual reported results (use `earnings`); vague qualitative statements without numbers (mark low `actionability`). |

### 3.3 `capital_action`

| Field | Value |
|---|---|
| **Definition** | A discrete change to the company's capital structure: buyback, dividend, M&A, equity issuance, debt issuance, spinoff, bankruptcy. |
| **Typical evidence** | `regulatory_filing` (8-K, S-1, S-4, proxy), `press_release` |
| **Typical directions** | bullish 50%, bearish 40%, neutral 10% |
| **Typical horizon** | short |
| **Default durability** | structural (for M&A, bankruptcy) or short (for buyback, dividend) |
| **Precedent richness** | high |
| **Examples** | "ACME announced $500M buyback, ~3.2% of market cap." |
| **Anti-examples** | Operational cost cuts (use `operational`); rumor of M&A (not a Signal until official). |

### 3.4 `management`

| Field | Value |
|---|---|
| **Definition** | A change in CEO, CFO, board composition, or other senior leadership with strategic impact. |
| **Typical evidence** | `regulatory_filing` (8-K, DEF 14A), `press_release`, `news_article` |
| **Typical directions** | mixed (direction depends on context) |
| **Typical horizon** | long |
| **Default durability** | structural |
| **Precedent richness** | medium |
| **Examples** | "ACME CEO Jane Smith resigned; John Doe appointed interim." |
| **Anti-examples** | Mid-level hiring (no Signal unless strategic role); rumored departures (not Signal until official). |

### 3.5 `operational`

| Field | Value |
|---|---|
| **Definition** | A change in a non-financial operational KPI: subscriber count, same-store sales, DAU, retention, capacity, backlog. |
| **Typical evidence** | `press_release`, `earnings_call`, `regulatory_filing` |
| **Typical directions** | bullish 50%, bearish 40%, neutral 10% |
| **Typical horizon** | short |
| **Default durability** | short |
| **Precedent richness** | medium |
| **Examples** | "ACME added 2.1M net subscribers in Q2, +15% YoY." |
| **Anti-examples** | Macro retail sales data (use `macro`); competitive comparison without ACME-specific data (use `industry`). |

### 3.6 `industry`

| Field | Value |
|---|---|
| **Definition** | A discrete change affecting an industry or sector that is not entity-specific. |
| **Typical evidence** | `research_report`, `news_article`, `government_data`, trade association reports |
| **Typical directions** | varies |
| **Typical horizon** | medium |
| **Default durability** | structural |
| **Precedent richness** | low |
| **Examples** | "EU semiconductor inventory days rose to 92 from 78 last quarter, indicating softening demand." |
| **Anti-examples** | Entity-specific data (use appropriate entity-level type); rumor without sourcing. |

### 3.7 `macro`

| Field | Value |
|---|---|
| **Definition** | A change in a macro variable (rates, FX, inflation, employment, GDP) or a macro policy decision. |
| **Typical evidence** | `government_data`, central bank statements, news wires |
| **Typical directions** | neutral (impact varies by entity) |
| **Typical horizon** | medium |
| **Default durability** | short to structural depending on variable |
| **Precedent richness** | high |
| **Examples** | "Fed held rates at 5.25–5.50%, dot plot signals one cut in 2026." |
| **Anti-examples** | Equity-specific events (use entity-level types); analyst forecasts (not Signals). |

### 3.8 `regulatory`

| Field | Value |
|---|---|
| **Definition** | A regulatory or legal action with material impact: approval, rejection, investigation, fine, ban, lawsuit outcome. |
| **Typical evidence** | `regulatory_filing`, agency press releases, court filings |
| **Typical directions** | varies |
| **Typical horizon** | long |
| **Default durability** | structural |
| **Precedent richness** | medium |
| **Examples** | "FDA approved ACME's drug XYZ for second-line treatment." |
| **Anti-examples** | General regulatory chatter (not a Signal until action); entity's own compliance filings (use `operational`). |

### 3.9 `sentiment`

| Field | Value |
|---|---|
| **Definition** | A measurable shift in market sentiment, survey data, or aggregate narrative tone about an entity. |
| **Typical evidence** | survey data, social media aggregations, news tone analysis |
| **Typical directions** | mixed |
| **Typical horizon** | short |
| **Default durability** | transient |
| **Precedent richness** | low |
| **Examples** | "AAII bull-bear spread fell to -15 from +5, indicating retail pessimism." |
| **Anti-examples** | Single article opinion (not a Signal); price moves alone (use `catalyst` or skip). |

### 3.10 `catalyst`

| Field | Value |
|---|---|
| **Definition** | A scheduled or unscheduled discrete event (FDA decision, court ruling, lockup expiry, conference appearance) whose occurrence has impact. |
| **Typical evidence** | calendar data, company announcement, news |
| **Typical directions** | mixed |
| **Typical horizon** | intraday to short |
| **Default durability** | transient to short |
| **Precedent richness** | medium |
| **Examples** | "ACME's lockup expires 2026-07-20, freeing 12% of float." |
| **Anti-examples** | Routine earnings (use `earnings`); generic calendar reminders with no entity-specific impact. |

---

## 4. Direction Conventions

Each type has a `typical_direction_distribution`. The detector agent ([02 §A2](02_agent_constitution.md)) uses this as a prior in its prompt; if it produces an unusual direction (e.g., bearish for a normally bullish type), the detector prompt lowers `confidence` by 0.1.

Direction is set on the Signal, not the type. The distribution here is just guidance.

---

## 5. Cross-Type Disambiguation Rules

When a single event could be multiple types, use these rules:

| Event description | Primary type | Why |
|---|---|---|
| Earnings call with results + guidance | `earnings` (primary), `guidance` (supporting) | Results are the headline |
| M&A with management change | `capital_action` (primary), `management` (supporting) | Capital structure change dominates |
| Product launch + new revenue guidance | `guidance` (primary), `operational` (supporting) | Forward-looking is more material |
| Industry data + entity-specific impact | `industry` (primary), `operational` (supporting) | Sector-wide context drives |
| Regulatory approval of a product | `regulatory` | Most material; ties to entity's revenue |
| Macro data release | `macro` | Always primary; entity-specific impact is downstream |

Multiple Signals from one event are permitted via `cluster_id` (see [04 §11](04_data_schema.md)).

---

## 6. Adding a New Type

To add a type:

1. Propose with: code, name, definition, 5+ real-world examples, evidence pattern
2. Show that no existing type covers it (per §5 disambiguation)
3. Add scoring rubric overrides if any dimension needs adjustment
4. Update detector prompt's enum list (MAJOR prompt version bump)
5. Update this document (MINOR version bump)
6. Add to Phase X+1 in [09_development_roadmap.md](09_development_roadmap.md)

If a proposed type doesn't satisfy (1)–(3), it should be modeled as a `metadata.custom_tags` entry on an existing type, not a new type.

---

## 7. Removing a Type

To remove a type:

1. Show usage < 0.1% over 6 months
2. Provide migration: which existing type maps to which removed type
3. Run shadow mode for 30 days where removed-type Signals are mapped to the replacement
4. Bump this document MAJOR
5. Update detector prompt (MAJOR)
6. Migrate in-flight Signals per migration log in [09 §11](09_development_roadmap.md)

---

## 8. Tag Layer (Non-Taxonomy)

Some attributes are not type-level but appear in `metadata.custom_tags`:

| Tag | Meaning |
|---|---|
| `first_time` | First occurrence of this type for this entity in 12 months |
| `consensus_breaker` | Direction diverges from analyst consensus by ≥ 1σ |
| `guidance_initiation` | First-ever guidance (not just revision) |
| `multi_source_confirmed` | ≥ 3 independent sources within 6 hours |
| `language:zh` | Source language (for multi-lingual support) |

Tags are **optional** and never required for type validation.

---

## 9. Worked Examples

### Example 1 — Single-Type Signal

```yaml
type: earnings
claim: "ACME Q2 EPS of $1.20 vs consensus $1.05, beat by 14%."
direction: bullish
horizon: short
```

### Example 2 — Multi-Type Cluster

```yaml
# Primary
- type: capital_action
  cluster_id: cluster_abc
  claim: "ACME acquiring XYZ for $2.3B in cash + stock."

# Supporting
- type: management
  cluster_id: cluster_abc
  claim: "ACME's CFO to lead integration; XYZ CEO departing at close."

# Supporting
- type: operational
  cluster_id: cluster_abc
  claim: "Combined entity expected to capture $80M annual synergies by Y3."
```

Three Signals, one `cluster_id`, one underlying event. Reporter renders the cluster as a single narrative with three supporting references.

### Example 3 — Anti-Type (must be rejected)

```yaml
type: earnings
claim: "ACME's CEO said earnings might be good next quarter."
direction: bullish
evidence: [{ source_url: "https://twitter.com/...", quote: "..." }]
```

This is not a Signal — the "earnings" type requires **reported results**, not speculation. And the source is social media with no primary corroboration. Detector should emit no Signal, or classify as `sentiment` with low confidence.

---

## 10. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold with 10 types |

Adding a new type (§6) is MAJOR (for downstream detector). Removing a type (§7) is MAJOR. Adding new tags (§8) is MINOR. Wording fixes are PATCH.