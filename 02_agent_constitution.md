# 02 · Agent Constitution

> **Document role:** Contract specification for every agent in SIGNAL. Defines inputs, outputs, responsibilities, cost classification, and version-binding rules. Required reading before adding or modifying any agent.
>
> Requires: `00_project_context.md ≥ 0.2`, `01_signal_constitution.md ≥ 0.1`.

---

## 1. What an Agent Is

An **agent** in SIGNAL is a named, versioned software component that performs **one** well-defined transformation. It is the only place where LLM calls, regex extraction, or external API integrations are permitted.

```
Agent := {
  name           : string,
  version        : semver,
  description    : string,
  input_schema   : <ref to 04>,
  output_schema  : <ref to 04>,
  preconditions  : [predicate, ...],
  postconditions : [predicate, ...],
  cost_class     : {free | cheap | moderate | expensive},
  determinism    : {deterministic | stochastic | mixed},
  side_effects   : [write_target, ...],
  failure_modes  : [FailureMode, ...],
  prompts        : { name : PromptRef },        // if LLM-based
  model_versions : { task : ModelVersion },     // if LLM-based
}
```

### Why a Constitution

Without a constitution, agents proliferate without contracts and the pipeline becomes undebuggable. This document enforces:
- **Single responsibility** — one transformation per agent
- **Versioned interface** — input/output schemas pinned
- **Declared cost** — operators can budget before deploy
- **Declared determinism** — replay reproducibility is enforceable

---

## 2. Agent Inventory

SIGNAL has **eight** first-class agents. Each is mandatory in v1.x.

| # | Agent | Layer | Purpose |
|---|---|---|---|
| A1 | `harvester` | 0 — Ingestion | Acquire raw data from sources |
| A2 | `detector` | 1 — Detection | Extract candidate Signals from RawDocuments |
| A3 | `verifier` | 1 — Detection | Validate source, quote, entity resolution |
| A4 | `analyst` | 3 — Reasoning | Assess significance, causality, durability |
| A5 | `scorer` | 2 — Scoring | Compute 5-dimension score + composite |
| A6 | `synthesizer` | 4 — Synthesis | Cluster Signals into ThesisDeltas |
| A7 | `reporter` | 5 — Output | Render reports, update watchlist |
| A8 | `curator` | Cross-cutting | Apply human overrides (special, see §11) |

The `curator` agent is non-LLM: it accepts human input via a UI. All others are autonomous.

---

## 3. Agent Catalog

### A1 · harvester

| Field | Value |
|---|---|
| **Purpose** | Pull new items from configured sources into `RawDocument` |
| **Inputs** | Source descriptors (`source_id`, `fetch_url`, `auth`, `parser_hint`) |
| **Outputs** | `RawDocument[]` per cycle (see [04_data_schema.md#raw-document](04_data_schema.md)) |
| **Preconditions** | Source connector enabled; rate-limit budget available |
| **Postconditions** | Each emitted `RawDocument` has `retrieved_at`, `document_hash`, `source_id` |
| **Cost class** | `free` (no LLM calls) |
| **Determinism** | `deterministic` given same source state |
| **Side effects** | Writes to RawStore |
| **Failure modes** | Source 5xx, auth failure, rate-limit, malformed payload |

#### Source Connector Pattern

Every source implements a single interface:

```python
class SourceConnector(Protocol):
    source_id: str
    poll(self, since: datetime) -> Iterable[RawItem]
    healthcheck(self) -> SourceHealth
```

Source-specific quirks (auth headers, pagination, encoding) are confined to the connector. The agent layer is unaware of them.

---

### A2 · detector

| Field | Value |
|---|---|
| **Purpose** | Read a `RawDocument`, emit 0..N candidate `Signal` (status `draft`) |
| **Inputs** | `RawDocument` |
| **Outputs** | `Signal[]` (status `draft`) |
| **Preconditions** | Document has passed dedup (handled by pipeline, not agent) |
| **Postconditions** | Each emitted Signal has ≥1 Evidence, valid `entity_ref`, valid `type` |
| **Cost class** | `expensive` — primary LLM usage point |
| **Determinism** | `stochastic` — depends on model and prompt |
| **Side effects** | Writes to SignalStore |
| **Failure modes** | Model refusal, JSON parse failure, hallucinated entity |

#### Detector Prompt Contract

The detector prompt MUST (full standards: [07_prompt_guidelines.md](07_prompt_guidelines.md)):

1. Receive the raw text + a system prompt with the Signal schema and taxonomy summary
2. Return a JSON array of candidate Signals (or empty)
3. Never invent sources, dates, or entities
4. If no signal is present, return `[]` — do not force one

```jsonc
// detector output example
[
  {
    "type": "capital_action",
    "entity_ref": {"kind": "company", "id": "ACME.US"},
    "claim": "ACME announced a $500M share buyback program.",
    "direction": "bullish",
    "horizon": "short",
    "evidence": [{
      "source_url": "https://www.sec.gov/.../8-k.htm",
      "source_type": "regulatory_filing",
      "quote": "The Board authorized a $500 million share repurchase program.",
      "char_offset": [1204, 1267]
    }],
    "timestamp": "2026-07-16T13:00:00Z"
  }
]
```

#### Cost Optimization Rules

- If a `RawDocument` is < 200 chars, skip LLM (likely a duplicate or noise)
- If a `RawDocument` matches a known boilerplate regex (e.g., standard SEC header), skip LLM
- Use `claude-haiku-4-5-20251001` for first pass; promote to `claude-opus-4-8` only if `confidence < 0.6`
- Model selection rationale and full task→model map: [07 §8](07_prompt_guidelines.md)

---

### A3 · verifier

| Field | Value |
|---|---|
| **Purpose** | Independently confirm the Signal's claim is real and traceable |
| **Inputs** | `Signal` (status `draft`) |
| **Outputs** | `Signal` (status `verified` \| `rejected`) + `VerificationReport` |
| **Preconditions** | Signal has ≥1 Evidence |
| **Postconditions** | `verified` Signal has reachable source, matching quote, resolved entity |
| **Cost class** | `cheap` — small LLM call + HTTP fetch |
| **Determinism** | `mixed` (HTTP fetch is deterministic; quote-match LLM call is stochastic) |
| **Side effects** | Updates SignalStore status; writes VerificationReport |
| **Failure modes** | Source unreachable, quote mismatch, entity resolution failure |

#### Verification Pipeline (within the agent)

```
1. HTTP GET evidence.source_url (timeout 30s, max 3 retries)
   ├─ non-2xx → REJECT, reason="source_unreachable"
2. Strip HTML, extract text
3. If evidence.quote present:
   ├─ substring search (50-char window before/after for context)
   ├─ LLM semantic-match check (claude-haiku-4-5)
   └─ both fail → REJECT, reason="quote_mismatch"
4. Resolve entity_ref:
   ├─ exact match in Company table → PASS
   ├─ fuzzy match ≥ 0.85 → PASS, record matched_id
   └─ else → REJECT, reason="entity_unresolved"
5. All gates pass → status=verified
```

A rejected Signal is logged but retained for audit.

---

### A4 · analyst

| Field | Value |
|---|---|
| **Purpose** | Reason about the Signal's significance, causal chain, and durability |
| **Inputs** | `Signal` (status `verified`) + relevant entity context |
| **Outputs** | `Signal` with populated `reasoning` field (see [04_data_schema.md#reasoning](04_data_schema.md)) |
| **Preconditions** | Signal status is `verified` |
| **Postconditions** | Reasoning fields populated; `confidence` may be updated |
| **Cost class** | `expensive` — large context, deep reasoning |
| **Determinism** | `stochastic` |
| **Side effects** | Updates SignalStore |
| **Failure modes** | Insufficient context, ambiguous evidence, reasoning exceeds token budget |

#### Reasoning Tasks

1. **Significance** — How material is the change relative to entity size/industry?
2. **Causality** — What downstream effects can this plausibly cause?
3. **Durability** — Is this a one-time event or a structural shift?
4. **Reversibility** — How easily could this be undone?
5. **Precedent** — Has a similar Signal on a comparable entity played out before?

Reasoning methodology: [05_reasoning_framework.md](05_reasoning_framework.md).

---

### A5 · scorer

| Field | Value |
|---|---|
| **Purpose** | Compute the 5-dimension score and composite |
| **Inputs** | `Signal` with reasoning |
| **Outputs** | `Signal` with populated `score` field |
| **Preconditions** | Reasoning fields populated |
| **Postconditions** | All 5 dimensions + composite present; composite ∈ [0, 1] |
| **Cost class** | `moderate` — structured prompt + arithmetic |
| **Determinism** | `mixed` (LLM judgment + deterministic math) |
| **Side effects** | Updates SignalStore |
| **Failure modes** | Missing dimension input, out-of-range value, divide-by-zero in composite |

The scorer uses a **deterministic** composite formula over LLM-assigned dimension values:

```
composite = 0.30 * magnitude
         + 0.25 * confidence
         + 0.20 * timeliness
         + 0.15 * novelty
         + 0.10 * actionability
```

Full formula and rationale: [06_scoring_framework.md](06_scoring_framework.md).

---

### A6 · synthesizer

| Field | Value |
|---|---|
| **Purpose** | Cluster multiple Signals into a `ThesisDelta` for entity-level view |
| **Inputs** | Active Signals for one entity within a window |
| **Outputs** | `ThesisDelta` (see [04_data_schema.md#thesis-delta](04_data_schema.md)) |
| **Preconditions** | ≥ 3 active Signals on same entity within 24h (configurable) |
| **Postconditions** | Each Signal gets a `cluster_id`; ThesisDelta lists all contributing Signal IDs |
| **Cost class** | `moderate` — synthesis LLM call |
| **Determinism** | `stochastic` |
| **Side effects** | Writes ThesisDelta to store |
| **Failure modes** | Insufficient cluster size, conflicting directions among Signals |

Clustering logic is **deterministic** (rule-based on time window + entity + type grouping); the LLM only writes the prose summary.

---

### A7 · reporter

| Field | Value |
|---|---|
| **Purpose** | Render Signals + ThesisDeltas into user-facing reports |
| **Inputs** | Filtered Signals, ThesisDeltas, watchlist |
| **Outputs** | Daily report (markdown), per-entity brief (markdown), JSON for UI |
| **Preconditions** | Reporting window defined |
| **Postconditions** | Report conforms to template ([13_report_template.md](13_report_template.md)) |
| **Cost class** | `moderate` — prose generation |
| **Determinism** | `stochastic` |
| **Side effects** | Writes report artifacts |
| **Failure modes** | Template violation, missing required sections, evidence omission |

The reporter never invents content; every fact in the report is grounded by `Signal.id` reference.

---

### A8 · curator (human-in-the-loop)

| Field | Value |
|---|---|
| **Purpose** | Apply human overrides on score, noise status, tier, watchlist membership, industry binding, or notes |
| **Inputs** | Target ID (Signal or Company) + override action from the canonical enum below |
| **Outputs** | `OverrideRecord` appended (see [04 §6](04_data_schema.md)) |
| **Preconditions** | Authenticated curator session |
| **Postconditions** | Both original and override values retained; never destructive |
| **Cost class** | `free` (no LLM) |
| **Determinism** | `deterministic` |
| **Side effects** | Writes `OverrideRecord` to audit log; downstream consumers apply via `metadata.override_active` |
| **Failure modes** | Unauthorized access (auth-gated, not spec-handled) |

#### Canonical Override Actions

The complete list of curator actions lives in [04 §6 OverrideRecord.action](04_data_schema.md). Summary:

| Action | Target | Effect |
|---|---|---|
| `adjust_score` | Signal | Recompute composite from adjusted dimensions |
| `mark_noise` | Signal | Set `status=rejected`; `metadata.override_active=true` |
| `mark_redundant` | Signal | Set `status=superseded`; record prior Signal ID |
| `change_tier` | Company | Move between tiers; preserve `tier_history` |
| `add_entity` | Watchlist | Create `WatchlistEntry` |
| `remove_entity` | Watchlist | Soft-delete; set `WatchlistEntry.status=removed` |
| `bind_industry_position` | Company | Add/change `industry_positions` |
| `update_notes` | Company or Signal | Update notes field |

**Curator adjustment range** (per [06 §8](06_scoring_framework.md)): each dimension may be adjusted by ±0.20 from system value; reason required for adjustments > 0.10.

Overrides do not rewrite the original Signal or Company; they add a layer that downstream consumers may apply. The original values remain in the audit log.

---

## 4. Cost Classification

Per P7, every agent declares its cost class:

| Class | Definition | Typical cost per call |
|---|---|---|
| `free` | No LLM, no paid API | $0.00 |
| `cheap` | Small LLM call OR cheap API (≤ 1k tokens in) | ≤ $0.01 |
| `moderate` | Medium LLM call (1k–10k tokens) | $0.01 – $0.10 |
| `expensive` | Large LLM call (> 10k tokens) OR multi-call | > $0.10 |

Budget per Signal (sum across agents): target **≤ $0.30** (see [00_project_context.md §7.2](00_project_context.md)).

---

## 5. Determinism and Replay

Each agent declares `determinism`:

| Value | Meaning | Replay behavior |
|---|---|---|
| `deterministic` | Same input → same output, always | Trivial replay |
| `stochastic` | Same input may produce different output | Replay requires pinned `model_versions` + `prompt_versions` + `temperature=0` |
| `mixed` | Some paths deterministic, some stochastic | Replay needs to capture sub-paths |

Replay mode (workflow trigger `replay`) MUST pin:
- `model_versions` for every LLM call
- `prompt_versions` for every prompt
- `temperature = 0`
- `seed` if supported by model

Replay divergence > 0.1 on composite score is a **bug** to investigate.

---

## 6. Versioning and Backward Compatibility

### 6.1 Agent Versioning

Each agent follows `MAJOR.MINOR.PATCH`:

- **MAJOR** — input/output schema change, or removal of a field
- **MINOR** — new optional field, new prompt version
- **PATCH** — bug fix, prompt wording tweak, performance

### 6.2 Compatibility Rules

- Pipeline **must** declare the exact `agent.version` it expects.
- Two agents with different MAJOR versions **cannot** coexist in one pipeline run.
- A Signal's `provenance.agent_versions[]` is the auditable record of which agent versions produced it.
- Deprecation window: 90 days. A new MAJOR is announced, old MAJOR continues to run, after 90 days old is removed.

### 6.3 Breaking the Schema

A breaking change to an agent's output requires:
1. Bumping MAJOR
2. Migration code for Signals in flight (transform old → new shape)
3. Note in [09_development_roadmap.md](09_development_roadmap.md)
4. Update of all downstream agent `preconditions`

---

## 7. Prompt Versioning

Per-agent prompts live in `prompts/<agent>/<purpose>/v<X.Y>.<Z>.md`. The `provenance.prompt_versions[]` field records the exact versions used for each Signal.

Rules:
- A prompt change is a MINOR agent version bump at minimum
- A change to **output schema** in the prompt is MAJOR
- Old prompts are never deleted; they remain referenceable for replay

Full prompt engineering standards: [07_prompt_guidelines.md](07_prompt_guidelines.md).

---

## 8. Model Versioning

The `model_versions` map declares which model is used for which sub-task within an agent. Example:

```yaml
agent: detector
version: 1.4.2
model_versions:
  entity_extraction: claude-haiku-4-5-20251001
  claim_composition: claude-opus-4-8
  type_classification: claude-haiku-4-5-20251001
temperature: 0.0
max_tokens: 2048
```

Replay requires this map. A model upgrade is a MINOR bump.

---

## 9. Inter-Agent Communication

Agents **never** call each other directly. All handoffs go through the SignalStore (or a typed message bus for non-Signal artifacts). This is enforced by:
- No agent has a reference to another agent
- No agent imports another agent's module
- All handoffs are typed artifacts in [04_data_schema.md](04_data_schema.md)

Exception: `curator` writes overrides, but only to the audit log + SignalStore, never to other agents.

---

## 10. Adding a New Agent

To add an agent:

1. Propose a name that follows `<verb-er>` or `<noun-er>` convention (matches existing).
2. Fill out one row in the §2 inventory table.
3. Write the full §3 catalog entry.
4. Define or reference input/output schemas in [04_data_schema.md](04_data_schema.md).
5. Declare cost class and determinism.
6. Update [03_workflow_constitution.md](03_workflow_constitution.md) to show where the agent fits.
7. Add a phase in [09_development_roadmap.md](09_development_roadmap.md).
8. Bump this document to a new MINOR.

Skipping any step is a documentation defect.

---

## 11. The Curator Special Case

`curator` is the only agent that accepts **non-deterministic, human-generated** input. It is treated specially:

- It never blocks the pipeline
- It cannot be invoked by automated workflows
- Its outputs are append-only `OverrideRecord`s, never in-place edits
- Original Signal values remain in the audit log
- Override values are clearly marked in all downstream consumers

---

## 12. Failure Mode Catalog (Common)

| Code | Meaning | Action |
|---|---|---|
| `source_unreachable` | HTTP non-2xx after retries | Mark source degraded; retry next cycle |
| `auth_failure` | 401/403 from source | Disable source; page Operator |
| `rate_limited` | 429 from source | Backoff exponentially |
| `parse_failure` | Document cannot be parsed | Log raw, skip; flag source for review |
| `entity_unresolved` | Entity not in Company table | Route to resolution queue; no Signal emitted |
| `quote_mismatch` | Quoted text not in source | REJECT Signal |
| `model_refusal` | LLM returns safety refusal | Lower temperature; re-attempt once; else route to manual |
| `json_parse_failure` | LLM output not valid JSON | Retry with explicit JSON-instruction prompt |
| `hallucinated_source` | Source URL not in input | REJECT Signal, log for review |
| `timeout` | Agent exceeds time budget | Abort; partial result discarded |
| `cost_overrun` | Per-Signal cost > $1.00 | Pause Signal; emit to manual review |

All failure events are persisted to the operational log with the same schema as Signals (`FailureEvent` type — see [04_data_schema.md](04_data_schema.md)).

---

## 13. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold |

Schema changes to the Agent type (top of §1) are MAJOR. New agents in §2/§3 are MINOR. New failure codes in §12 are MINOR.