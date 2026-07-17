# 04 · Data Schema — Canonical Contracts

> **Document role:** Single source of truth for every persisted and inter-agent data structure. All schemas referenced by other documents are defined here.
>
> Requires: `00_project_context.md ≥ 0.2`, `01_signal_constitution.md ≥ 0.1`.

---

## 1. Why This Document Exists

Per principle P2, schemas live in exactly one place. This document is that place. Other documents reference these schemas by `name` and never redefine fields.

If you find yourself defining a field in another document that should live here — stop and move it here.

---

## 2. Format Conventions

All schemas are defined as **typed records** in a pseudo-JSON-Schema notation:

```
TypeName := {
  field_name : Type,
  ...
  <constraint>
}
```

- `string` with no annotation — free-form string
- `ULID` — 26-character ULID (lexicographically sortable)
- `ISO8601` — UTC timestamp string
- `enum[A, B, C]` — closed set
- `?Type` — optional field
- `Type[≥n]` — array with minimum cardinality
- `<ref:name>` — reference to another type in this document

Schema changes are versioned (see §13).

---

## 3. Core Identifier Types

### 3.1 EntityRef

```
EntityRef := {
  kind : enum[company, industry, macro_variable, sector],
  id   : string     // stable identifier per kind (see 12_company_schema.md)
}
```

| Kind | ID format | Defined in |
|---|---|---|
| `company` | `<TICKER>.<EXCHANGE>` (e.g., `ACME.US`) | [12_company_schema.md](12_company_schema.md) |
| `industry` | chain-node ID | [11_industry_mapping.md](11_industry_mapping.md) |
| `macro_variable` | macro ID (e.g., `FEDFUNDS`, `CPIAUCSL`) | (system registry) |
| `sector` | GICS-style code | (system registry) |

Resolution rule: an EntityRef of `kind=company` MUST resolve to a Company entity; otherwise the Signal is rejected at verification (see [02 §A3](02_agent_constitution.md)).

### 3.2 ULID

All entity IDs use ULID format (26 chars, Crockford base32). ULIDs are lexicographically sortable by creation time, simplifying cold-storage scans.

---

## 4. Signal Schema

The Signal schema is **authoritative** — referenced from [01_signal_constitution.md §1](01_signal_constitution.md), [02 §A2–A5](02_agent_constitution.md), [05](05_reasoning_framework.md), [06](06_scoring_framework.md), and all output documents.

### 4.1 Full Type

```
Signal := {
  id            : ULID,
  cycle_id      : ULID,                  // workflow run that produced it
  entity_ref    : EntityRef,
  type          : SignalType,            // see 10_signal_taxonomy.md
  claim         : string,                // one sentence, falsifiable
  direction     : enum[bullish, bearish, neutral],
  horizon       : enum[intraday, short, medium, long],
  evidence      : Evidence[≥1],          // see §5
  timestamp     : ISO8601,               // when underlying event occurred
  detected_at   : ISO8601,               // when system emitted it
  score         : Score,                 // see §7 / 06_scoring_framework.md
  status        : enum[draft, verified, active, decayed, rejected, superseded],
  reasoning     : Reasoning?,            // see §8 / 05_reasoning_framework.md
  cluster_id    : ULID?,                 // see §11
  provenance    : Provenance,            // see §9
  metadata      : Metadata              // see §10
}
```

### 4.2 Cardinality Constraints

| Field | Constraint | Why |
|---|---|---|
| `claim` | 1–280 chars, no newline | Single sentence, fits in any UI |
| `evidence` | ≥ 1 | Invariant from [01 §1](01_signal_constitution.md) |
| `timestamp ≤ detected_at` | always | Cannot detect before event |
| `timestamp ≥ detected_at - 7d` | default | Signals about events > 7d old are usually stale |

### 4.3 Field-Level Validation Rules

| Field | Rule |
|---|---|
| `type` | MUST be valid value in [10_signal_taxonomy.md](10_signal_taxonomy.md) |
| `direction` | MUST be set; default `neutral` only if detector truly cannot determine |
| `horizon` | MUST be set; rules in [06 §3](06_scoring_framework.md) |
| `status` | transitions MUST follow lifecycle in [01 §3](01_signal_constitution.md) |

---

## 5. Evidence Schema

```
Evidence := {
  source_url    : URL,
  source_type   : enum[regulatory_filing, news_article, earnings_call,
                       press_release, social_media, blog_post,
                       research_report, government_data, other],
  retrieved_at  : ISO8601,
  quote?        : string,                // if given, must appear in fetched source
  char_offset?  : [int, int],            // [start, end] of quote within source text
  document_hash : string,                // sha256:hex
  excerpt?      : string                 // ≤ 500 chars around the quote for context
}
```

### 5.1 Quotation Invariant

If `quote` is provided, the verifier ([02 §A3](02_agent_constitution.md)) checks:
1. The quote appears verbatim in the fetched source text.
2. The `char_offset` matches (within ±5 chars tolerance).
3. The context window (50 chars before/after) does not change the meaning (LLM semantic check).

Any of these failing → Signal rejected with `quote_mismatch`.

### 5.2 Document Hash

`document_hash` is `sha256:` + lowercase hex digest of the canonical text content. The canonical form:
- Lowercased
- Whitespace collapsed
- HTML stripped (if HTML source)

This enables exact-dedup at S3 of the workflow ([03 §S3](03_workflow_constitution.md)).

---

## 6. Provenance Schema

```
Provenance := {
  agent_chain       : [AgentRef],        // ordered list
  agent_versions    : { agent_name: semver },
  prompt_versions   : { prompt_id: semver },
  model_versions    : { task: model_id },
  temperature       : float,              // per call
  seed?             : int,                // if model supports
  cycle_id          : ULID,
  emitted_at        : ISO8601,
  input_hashes      : { artifact_name: sha256:hex },
  override_records? : [OverrideRecord]   // appended by curator agent
}

AgentRef := {
  name    : string,
  version : semver
}

OverrideRecord := {
  by        : string,                     // curator user id
  at        : ISO8601,
  action    : enum[adjust_score, mark_noise, mark_redundant, change_tier,
                    add_entity, remove_entity, bind_industry_position,
                    update_notes],
  before    : <varies>,                   // snapshot of affected field
  after     : <varies>,                   // new value
  reason    : string
}
```

### 6.1 Why Provenance is Mandatory

- Auditability — every Signal can be regenerated from inputs + provenance
- Reproducibility — pinned versions enable replay (W5 in [03 §9](03_workflow_constitution.md))
- Trust — Reader can see exactly which agent/model/prompt produced each claim
- Debugging — failure modes can be traced to specific agent versions

---

## 7. Score Schema

```
Score := {
  magnitude      : float[0,1],          // see 06 §2
  confidence     : float[0,1],          // see 06 §2
  timeliness     : float[0,1],          // see 06 §2
  novelty        : float[0,1],          // see 06 §2
  actionability  : float[0,1],          // see 06 §2
  composite      : float[0,1],          // weighted sum, see 06 §4
  band           : enum[high, medium, low],  // composite bucket, see 06 §5
  scored_at      : ISO8601,
  scored_by      : AgentRef
}
```

All values are clamped to [0, 1]. Composite is recomputed deterministically from the five dimensions — the LLM never directly assigns composite.

---

## 8. Reasoning Schema

Populated by the `analyst` agent ([02 §A4](02_agent_constitution.md)). See [05_reasoning_framework.md](05_reasoning_framework.md) for methodology.

```
Reasoning := {
  significance   : float[0,1],          // how material
  causality      : [CausalLink],        // downstream effects
  durability     : enum[transient, short, structural],
  reversibility  : enum[irreversible, hard, easy],
  precedents     : [PrecedentRef],      // similar historical Signals
  one_liner      : string               // ≤ 140 chars, for reports
}

CausalLink := {
  to_entity      : EntityRef,
  mechanism      : string,              // ≤ 280 chars
  likelihood     : enum[low, medium, high],
  time_horizon   : enum[intraday, short, medium, long]
}

PrecedentRef := {
  signal_id      : ULID,
  similarity     : float[0,1],
  outcome        : string               // what actually happened, recorded post-hoc
}
```

### 8.1 When Reasoning May Be Skipped

In degrade mode ([03 §6.3](03_workflow_constitution.md)), reasoning is skipped. In that case:
- `reasoning` is null
- `metadata.reasoning_skipped: true` is set
- Such Signals are flagged in reports

---

## 9. Metadata Schema

Free-form but typed bag for fields not in the core schema.

```
Metadata := {
  source_doc_id        : ULID,             // FK to RawDocument
  cluster_size?        : int,              // set if part of a ThesisDelta (≥3)
  burst_triggered?     : bool,
  reasoning_skipped?   : bool,             // set if analyst agent was skipped
  reasoning_partial?   : bool,             // set if reasoning produced with reduced fields
  score_partial?       : bool,             // set if <5 dimensions were scored
  degrade_mode?        : bool,
  override_active?     : bool,
  precedent_basis?     : enum[entity, industry, none],   // see [05 §6]
  precedent_conflict?  : bool,             // see [05 §6]
  custom_tags?         : [string]          // taxonomy-defined tags, see [10 §8](10_signal_taxonomy.md)
}
```

`Metadata` MUST NOT contain data that should be in a core field. If you find yourself reaching for `custom_tags` for something essential, propose adding it to the core schema instead.

---

## 10. Other Schemas

### 10.1 RawDocument

```
RawDocument := {
  id              : ULID,
  source_id       : string,              // e.g., "sec_edgar"
  source_url      : URL,
  cleaned_url     : URL,
  raw_content     : string,              // as-fetched
  cleaned_text    : string,              // normalized
  document_hash   : string,              // sha256:hex of canonical cleaned_text
  retrieved_at    : ISO8601,
  published_at?   : ISO8601,             // if extractable from source
  language?       : enum[en, zh, ja, de, fr, es, other],
  metadata        : { author?, title?, tags? }
}
```

### 10.2 ThesisDelta

```
ThesisDelta := {
  id                : ULID,
  entity_ref        : EntityRef,
  window_start      : ISO8601,
  window_end        : ISO8601,
  signal_ids        : [ULID],            // ≥ 3
  net_direction     : enum[bullish, bearish, neutral, mixed],
  net_magnitude     : float[0,1],
  summary           : string,            // ≤ 500 chars
  detailed_analysis?: string,            // longer prose
  previous_delta_id?: ULID,              // for diff over time
  generated_at      : ISO8601,
  generated_by      : AgentRef
}
```

### 10.3 VerificationReport

```
VerificationReport := {
  signal_id          : ULID,
  source_reachable   : bool,
  quote_match        : enum[exact, fuzzy, missing, not_applicable],
  entity_resolved    : bool,
  resolved_entity_id?: string,
  overall            : enum[pass, fail],
  failure_reasons?   : [string],
  verified_at        : ISO8601,
  verified_by        : AgentRef
}
```

### 10.4 FailureEvent

```
FailureEvent := {
  id              : ULID,
  cycle_id        : ULID,
  stage           : string,              // e.g., "S4.detect"
  error_code      : string,              // see 02 §12
  message         : string,
  input_ref       : { type, id },
  occurred_at     : ISO8601,
  recovered       : bool,
  recovery_action?: string
}
```

### 10.5 CycleReport

```
CycleReport := {
  cycle_id              : ULID,
  workflow_name         : string,
  workflow_version      : semver,
  started_at            : ISO8601,
  ended_at              : ISO8601,
  stage_durations       : { stage: seconds },
  stage_outcomes        : { stage: { success: int, failed: int } },
  signals_emitted       : { draft: int, verified: int, active: int,
                            rejected: int, decayed: int, superseded: int, held: int },
  llm_cost_actual       : dollars,
  breach_reasons?       : [string],
  degrade_mode_active   : bool,
  errors                : [ULID]            // FKs to FailureEvent
}
```

### 10.6 Company (sketch — see 12_company_schema.md for full)

```
Company := {
  id              : string,              // <TICKER>.<EXCHANGE>
  ticker          : string,
  exchange        : string,
  name            : string,
  aliases         : [string],            // for entity resolution
  sector          : string,              // GICS code
  industries      : [string],            // chain-node IDs, see 11
  market_cap      : dollars?,
  currency        : string,
  fiscal_year_end?: string,
  metadata        : { ... }
}
```

---

## 11. Cluster Schema

A `cluster_id` on a Signal references a `Cluster`:

```
Cluster := {
  id            : ULID,
  entity_ref    : EntityRef,
  signal_ids    : [ULID],
  window_start  : ISO8601,
  window_end    : ISO8601,
  cluster_type  : enum[thesis_delta, same_event, supply_chain_cascade],
  created_at    : ISO8601,
  created_by    : AgentRef
}
```

A Signal with `cluster_id` set is part of a cluster. Signals without `cluster_id` are standalone.

---

## 12. JSON Encoding Notes

When schemas are serialized to JSON:

- ULIDs are strings (no special encoding)
- Timestamps are ISO8601 UTC strings (e.g., `"2026-07-16T13:00:00Z"`)
- Floats are encoded as JSON numbers; clamping is enforced at write-time
- Enum values are lowercase strings
- Optional fields omit the key entirely (not `null`) when absent, **except** for fields that distinguish "absent" from "empty" (e.g., `cluster_id` uses null to mean "not clustered")

---

## 13. Schema Versioning

| Schema | Version | Date | Change |
|---|---|---|---|
| Signal | 1.0.0 | 2026-07-16 | Initial |
| Evidence | 1.0.0 | 2026-07-16 | Initial |
| Provenance | 1.0.0 | 2026-07-16 | Initial |
| Score | 1.0.0 | 2026-07-16 | Initial |
| Reasoning | 1.0.0 | 2026-07-16 | Initial |
| Metadata | 1.0.0 | 2026-07-16 | Initial |
| RawDocument | 1.0.0 | 2026-07-16 | Initial |
| ThesisDelta | 1.0.0 | 2026-07-16 | Initial |
| VerificationReport | 1.0.0 | 2026-07-16 | Initial |
| FailureEvent | 1.0.0 | 2026-07-16 | Initial |
| CycleReport | 1.0.0 | 2026-07-16 | Initial |
| Cluster | 1.0.0 | 2026-07-16 | Initial |
| EntityRef | 1.0.0 | 2026-07-16 | Initial |
| OverrideRecord | 1.0.0 | 2026-07-16 | Initial |
| Company | 1.0.0 | 2026-07-16 | Initial (full spec in [12_company_schema.md](12_company_schema.md)) |

### Breaking-change policy

A field added is MINOR. A field removed or type-changed is MAJOR. Renaming a field is MAJOR (treat as remove + add). Optionality changes (required → optional) are MINOR. Optional → required is MAJOR.

### Migration

A schema MAJOR bump requires a `migrations/` directory entry. See [09_development_roadmap.md](09_development_roadmap.md) for the migration log.