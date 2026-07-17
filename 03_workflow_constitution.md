# 03 · Workflow Constitution

> **Document role:** Pipeline orchestration specification. Defines how agents are sequenced, how data flows between them, how errors are handled at the workflow level, and how workflows are triggered.
>
> Requires: `00_project_context.md ≥ 0.2`, `01_signal_constitution.md ≥ 0.1`, `02_agent_constitution.md ≥ 0.1`.

---

## 1. What a Workflow Is

A **workflow** is a directed acyclic graph of agent invocations and deterministic transformations. It is the executable form of the conceptual pipeline described in [00_project_context.md §5](00_project_context.md).

```
Workflow := {
  name           : string,
  version        : semver,
  trigger        : Trigger,
  stages         : [Stage],
  failure_policy : FailurePolicy,
  budgets        : Budgets,
}
```

### Why a Constitution

Agents alone are useless without orchestration. This document:
- Defines which agents run in which order
- Defines where deterministic logic sits between agents
- Defines failure handling at the workflow level (above the agent level)
- Defines budgets and abort conditions

---

## 2. Workflow Inventory

SIGNAL has **five** workflows in v1.x:

| # | Name | Purpose | Trigger |
|---|---|---|---|
| W1 | `ingest_cycle` | End-to-end: raw data → Signals in store | Scheduled (15min / 4h) |
| W2 | `burst_cycle` | Same as ingest but tighter dedup, faster verifier | Event-driven (volume spike) |
| W3 | `synthesis_cycle` | Cluster Signals into ThesisDeltas | Hourly during market hours |
| W4 | `report_cycle` | Render daily/weekly reports | Scheduled (pre-market, post-close, Friday EOD) |
| W5 | `replay_cycle` | Re-run a historical window with pinned versions | Manual (auditor/operator) |

---

## 3. Stage Catalog (W1 — Ingest Cycle)

`ingest_cycle` is the canonical workflow. All others derive from it.

```
┌────────────────────────────────────────────────────────────────────────────┐
│                       W1 · ingest_cycle                                    │
│                                                                            │
│  S1 Harvest  ──►  S2 Normalize  ──►  S3 Dedup  ──►  S4 Detect             │
│       │              │                  │                │                  │
│       └──────────────┴──────────────────┴────────────────┘                  │
│                                            │                                │
│                                            ▼                                │
│                                     S5 Verify                               │
│                                            │                                │
│                                            ▼                                │
│                                     S6 Reason                               │
│                                            │                                │
│                                            ▼                                │
│                                     S7 Score                                │
│                                            │                                │
│                                            ▼                                │
│                                     S8 Gating                               │
│                                            │                                │
│                                            ▼                                │
│                                     S9 Persist                              │
└────────────────────────────────────────────────────────────────────────────┘
```

| # | Stage | Type | Agent / Function | I/O |
|---|---|---|---|---|
| S1 | Harvest | agent | `harvester` | sources → RawItem[] |
| S2 | Normalize | function | `normalize()` | RawItem[] → RawDocument[] |
| S3 | Dedup | function | `dedup()` | RawDocument[] → RawDocument[] (filtered) |
| S4 | Detect | agent | `detector` | RawDocument[] → Signal[] (draft) |
| S5 | Verify | agent | `verifier` | Signal[] (draft) → Signal[] (verified\|rejected) |
| S6 | Reason | agent | `analyst` | Signal[] (verified) → Signal[] (with reasoning) |
| S7 | Score | agent + function | `scorer` + `compute_composite()` | Signal[] → Signal[] (with score) |
| S8 | Gating | function | `gate()` | Signal[] → Signal[] (active\|held) |
| S9 | Persist | function | `persist()` | Signal[] → SignalStore write |

Stages S2, S3, S8, S9 are **deterministic functions**, not agents. This is intentional per P4.

---

## 4. Stage Specifications

### S1 — Harvest

```yaml
stage: harvest
agent: harvester
input: source_registry
output: raw_item[]
parallelism: per-source (max 8 concurrent)
budget:
  wall_time_max: 8m
  retries: 3 per source
failure_policy:
  per_source: skip-and-continue
  global: if > 50% sources fail, abort workflow
```

Per-source isolation ensures one misbehaving connector does not block the cycle.

### S2 — Normalize

```yaml
stage: normalize
type: function
input: raw_item[]
output: raw_document[]
contract:
  - assign document_hash (sha256 of canonical text)
  - parse timestamps to ISO8601 UTC
  - strip tracking params from URLs
  - preserve original_url alongside cleaned_url
deterministic: true
```

### S3 — Dedup

```yaml
stage: dedup
type: function
input: raw_document[]
output: raw_document[]   # filtered
rules:
  - exact_hash: drop if hash seen in last 7d
  - near_dup: drop if minhash similarity ≥ 0.9 with any doc in last 48h
  - url_norm: drop if cleaned_url seen in last 24h
  - skip_if_short: drop if cleaned text < 200 chars AND no ticker mentioned
exception: if trigger == "burst", rules 2 and 4 are relaxed
```

MinHash parameters: 128 permutations, Jaccard threshold 0.9. Implementation lives in `dedup/`.

Note: S3 dedups **raw documents**. Signal-level dedup (which may mark a Signal `superseded`) is a separate step between S4 and S5, governed by the cardinality rules in [01 §4](01_signal_constitution.md).

### S4 — Detect

```yaml
stage: detect
agent: detector
input: raw_document[]
output: signal[]     # all in status=draft
parallelism: per-document (max 16 concurrent)
budget:
  per_call_max: 30s
  per_cycle_max: 12m
failure_policy:
  per_document: log and continue
  per_call: retry once at lower model tier
```

### S5 — Verify

```yaml
stage: verify
agent: verifier
input: signal[]      # status=draft
output: signal[]      # status ∈ {verified, rejected}
parallelism: per-signal (max 16)
budget:
  per_call_max: 45s
  per_cycle_max: 15m
failure_policy:
  per_signal: route to rejected with reason
```

### S6 — Reason

```yaml
stage: reason
agent: analyst
input: signal[]      # status=verified
output: signal[]      # reasoning fields populated
parallelism: per-signal (max 8)
budget:
  per_call_max: 60s
  per_cycle_max: 20m
fallback:
  if context_window_exceeded: split reasoning into sub-questions
```

### S7 — Score

```yaml
stage: score
type: agent + function
agent: scorer
input: signal[]      # with reasoning
output: signal[]      # with score
steps:
  - scorer agent assigns 5 dimensions (LLM)
  - compute_composite() applies weighted sum (deterministic)
parallelism: per-signal (max 16)
```

### S8 — Gating

```yaml
stage: gate
type: function
input: signal[]      # with score
output: signal[]      # status ∈ {active, held, rejected}
rules:
  - composite >= 0.65 → status=active
  - 0.45 <= composite < 0.65 → status=held (queued for curator)
  - composite < 0.45 → status=rejected (auto-rejection, logged)
  - confidence < 0.30 → status=rejected, reason="low_confidence"   # [06 §5.2]
```

Gating thresholds are configurable in `config/gates.yaml`. The thresholds here are the canonical source; [06 §5.1](06_scoring_framework.md) is the matching scoring-side definition.

### S9 — Persist

```yaml
stage: persist
type: function
input: signal[]
output: signal_store_delta
operations:
  - active signals → signal_store (write)
  - verified signals → signal_store (write, status=verified)
  - rejected signals → signal_store (write, status=rejected) — retained for audit
  - held signals → curator_queue (write)
  - superseded signals → signal_store (write, status=superseded) — per [01 §4](01_signal_constitution.md) cardinality rule
deterministic: true
```

---

## 5. Trigger Modes (Cross-Cutting)

### 5.1 Scheduled Trigger

```yaml
trigger:
  type: scheduled
  cron_market_hours: "*/15 9-16 * * 1-5"   # every 15 min during US market
  cron_off_hours: "0 */4 * * *"             # every 4 hours otherwise
  timezone: America/New_York
  jitter_seconds: 30                        # prevent thundering herd
```

### 5.2 Burst Trigger

```yaml
trigger:
  type: burst
  detector: spike_monitor
  conditions:
    - 3+ sources publish same headline within 10 min
    - keyword match: ["fda approval", "merger", "bankruptcy", "guidance cut"]
    - price move > 5% in 5 min for any watchlist Tier 1 entity
  cooldown: 60s
  max_per_day: 50
```

### 5.3 Manual Trigger

```yaml
trigger:
  type: manual
  actor: curator | operator
  required_params:
    - workflow_name
    - input_window   # for replay-style runs
  audit: required
```

---

## 6. Failure Handling at Workflow Level

Workflow-level failure handling is **distinct** from agent-level failure handling (see [02 §12](02_agent_constitution.md)). Workflow failure handling decides: *what does the cycle do when something goes wrong?*

### 6.1 Failure Policies

| Policy | Behavior | When used |
|---|---|---|
| `skip-and-continue` | Skip the failed item, continue with next | Per-item failures |
| `retry-with-backoff` | Retry up to N times with exponential backoff | Transient errors |
| `abort-workflow` | Stop the entire cycle, log, alert | Global budget exceeded |
| `degrade-mode` | Continue with reduced functionality | LLM provider outage |

### 6.2 Per-Stage Failure Matrix

| Stage | On failure of one item | On failure of many items |
|---|---|---|
| S1 harvest | skip source, continue | if >50% sources fail → abort |
| S2 normalize | log, drop item | abort (deterministic, should never fail) |
| S3 dedup | log, drop item | abort (deterministic) |
| S4 detect | retry once at lower tier | if >30% fail → degrade mode |
| S5 verify | mark rejected | continue |
| S6 reason | mark `reasoning_skipped: true` | if >30% fail → degrade mode |
| S7 score | mark `score_partial: true` | abort (composite must compute) |
| S8 gate | abort (deterministic) | abort |
| S9 persist | abort; queue for retry | abort |

### 6.3 Degrade Mode

```yaml
degrade_mode:
  trigger: llm_provider_outage > 30 min
  effects:
    - S4 detect: use regex-only extractor (lower recall, higher precision)
    - S6 reason: skip; mark `reasoning_skipped: true`
    - S7 score: use only timeliness + magnitude (LLM-free fallback)
  exit: when provider health restored for 5 min
  audit: all degrade-mode Signals flagged in reports
```

### 6.4 Checkpoint and Resume

The workflow persists a **checkpoint** after each stage. On restart:
- If failure was at S5 or later → resume from S5 with input from checkpoint
- If failure was at S1–S4 → re-run from S1 (cheap, idempotent)
- Checkpoint TTL: 24h

---

## 7. Budgets

Each workflow declares budgets. Budget overrun → abort + alert.

```yaml
budgets:
  wall_time_max: 60m        # total cycle
  llm_cost_max: $50         # total per cycle
  signals_emitted_max: 500  # hard cap; throttling if exceeded
  storage_write_max: 1GB
```

Per-stage budgets in §4 are subsets of these.

### Budget Telemetry

Every cycle emits a `CycleBudgetReport` with actual vs budgeted values. If actual > budgeted, the report includes a `breach_reason` field.

---

## 8. State and Idempotency

### 8.1 Idempotency Keys

Every Signal carries a `content_hash = sha256(entity_id | claim | evidence[0].url | date)`. The pipeline guarantees:

> **A given content_hash will be processed exactly once per cycle.**

If the same content_hash appears twice in one cycle (e.g., from two sources), the second is dropped as a duplicate.

### 8.2 Cycle Identity

Each cycle run has a `cycle_id` (ULID). Every artifact produced in that run references it. This is the unit of audit and replay.

### 8.3 Partial Restart

If a workflow crashes mid-cycle, the next scheduled run starts a **new** cycle_id. The crashed cycle's partial artifacts are marked `cycle_state: partial` and excluded from reports until manually reconciled.

---

## 9. The Other Workflows (Brief)

### W2 — burst_cycle

Same structure as W1, with these changes:
- S3 dedup: relaxed (skip near_dup)
- S5 verify: tight (HTTP only, no LLM re-quote)
- Overall budget: 5 min wall time

### W3 — synthesis_cycle

```
S1 Pull active Signals per entity (24h window)
S2 Cluster (deterministic, by entity + type grouping)
S3 If cluster ≥ 3:
    S3a synthesizer agent writes prose
    S3b persist ThesisDelta
S4 If cluster < 3: skip entity
```

### W4 — report_cycle

```
S1 Determine report type (daily | weekly | entity_brief)
S2 Pull relevant Signals + ThesisDeltas
S3 reporter agent renders per 13_report_template.md
S4 Persist report artifact
S5 Notify (email | webhook | file drop)
```

### W5 — replay_cycle

```
S1 Load provenance for historical Signal IDs (input)
S2 Pin all agent versions, prompts, models
S3 Re-run S4-S7 with same inputs
S4 Diff output vs original; report divergence
```

Replay divergence > 0.1 on composite score is a **bug**. Divergence < 0.05 is expected (minor temperature noise). 0.05–0.1 is **investigate**.

---

## 10. Workflow Versioning

Workflows are versioned independently of agents.

- **MAJOR** — stage graph changes (add/remove/reorder stages)
- **MINOR** — new failure policy, new budget field
- **PATCH** — config tuning

A workflow's MAJOR bump does **not** require an agent MAJOR bump, but does require re-validation of all agent contracts.

---

## 11. Observability

Every workflow run emits:

| Artifact | Contents |
|---|---|
| `cycle_id` | ULID |
| `cycle_started_at`, `cycle_ended_at` | ISO8601 |
| `stage_durations[]` | per-stage wall time |
| `stage_outcomes[]` | per-stage success/fail counts |
| `signals_emitted` | count by status |
| `llm_cost_actual` | dollars |
| `breach_reasons[]` | any budget overruns |
| `degrade_mode_active` | bool |
| `errors[]` | structured error list |

These are emitted to the operational log + a metrics endpoint.

---

## 12. Workflow Configuration Files

| File | Purpose |
|---|---|
| `config/workflows/w1.yaml` | ingest_cycle definition |
| `config/workflows/w2.yaml` | burst_cycle |
| `config/workflows/w3.yaml` | synthesis_cycle |
| `config/workflows/w4.yaml` | report_cycle |
| `config/workflows/w5.yaml` | replay_cycle |
| config/sources.yaml` | Source registry |
| `config/gates.yaml` | Composite thresholds |
| `config/budgets.yaml` | Per-environment budgets |

---

## 13. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold |

Changes to workflow graph topology (§3) or failure policies (§6) are MAJOR. New workflows in §9 are MINOR. New failure codes are MINOR.