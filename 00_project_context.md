# 00 · Project Context — SIGNAL

> **Document role:** Project charter + engineering reference. Defines the problem, system boundary, design principles, architecture, workflows, edge cases, and future extensions. This is the root document; every other spec must remain consistent with the contracts established here.

---

## Table of Contents

1. [Purpose](#1-purpose)
2. [Design Principles](#2-design-principles)
3. [The Core Concept: Signal](#3-the-core-concept-signal)
4. [System Architecture](#4-system-architecture)
5. [Workflow](#5-workflow)
6. [Users and Roles](#6-users-and-roles)
7. [Success Criteria](#7-success-criteria)
8. [Non-Goals](#8-non-goals)
9. [Edge Cases and Failure Modes](#9-edge-cases-and-failure-modes)
10. [Future Extensions](#10-future-extensions)
11. [Document Map](#11-document-map)
12. [Versioning](#12-versioning)

---

## 1. Purpose

### 1.1 What SIGNAL Is

SIGNAL is an **AI Research Operating System** for systematic investment research. It continuously ingests public information about companies, industries, and macro variables, extracts structured **Signals** (see [01_signal_constitution.md](01_signal_constitution.md)), evaluates their significance using a uniform framework ([05_reasoning_framework.md](05_reasoning_framework.md), [06_scoring_framework.md](06_scoring_framework.md)), and produces ranked outputs that support — but never replace — human investment judgment.

### 1.2 What SIGNAL Is Not

| Misconception | Reality |
|---|---|
| "An LLM that reads news" | SIGNAL is a **pipeline of specialized agents** ([02_agent_constitution.md](02_agent_constitution.md)) with deterministic glue between them |
| "A trading bot" | SIGNAL emits **research outputs only**. No orders, no position sizing |
| "A recommendation engine" | SIGNAL **does not say buy/sell**. It surfaces evidence and lets humans decide |
| "A forecasting model" | SIGNAL is backward-looking on observed changes. Forward estimates are **not** a primary deliverable |
| "A real-time HFT system" | SIGNAL targets research-grade latency (minutes-to-hours), not sub-second |

### 1.3 Why It Exists

Modern equity research has three structural problems that SIGNAL addresses:

1. **Information asymmetry by latency** — Public information is published continuously; analyst attention is not. SIGNALS collapse this latency gap to hours.
2. **Framework inconsistency** — Two analysts looking at the same earnings call may produce divergent theses. SIGNAL enforces one framework per signal type.
3. **Coverage scarcity** — A senior analyst can deeply cover 30–50 names. SIGNAL's automation extends effective coverage to 200–500 names per tier with uniform quality.

### 1.4 What "Production-Quality" Means Here

A feature is production-grade when **all** hold:

- Documented spec exists before code is written.
- Failure modes have explicit handling (see §9).
- Output is reproducible given the same inputs and agent versions.
- Every claim is traceable to a primary source.
- A new operator can debug it within one hour using only the specs in this folder.

---

## 2. Design Principles

These nine principles are non-negotiable. When a design choice conflicts with a principle, the principle wins and the design is reconsidered.

### P1 — Signals Are the Only First-Class Object
Everything else (reports, alerts, watchlists) **derives from** Signals. If a feature cannot be expressed as a transformation over Signals, it does not belong.

### P2 — Single Source of Truth per Concept
A schema lives in exactly one document. Examples:
- Signal schema → [01_signal_constitution.md](01_signal_constitution.md) §1
- Score dimensions → [06_scoring_framework.md](06_scoring_framework.md) §2
- Signal categories → [10_signal_taxonomy.md](10_signal_taxonomy.md)

Other documents reference, never redefine.

### P3 — Evidence Before Opinion
No claim reaches a user without a retrievable primary source. Agents are forbidden from "filling in" missing data.

### P4 — Deterministic Glue, Probabilistic Brain
Inter-agent handoffs, dedup, scoring math, lifecycle transitions: **deterministic code**.
LLMs: used only where genuine interpretation is required (claim extraction, significance reasoning, prose generation).

### P5 — Every Output Is Reproducible
Given `(input, agent_versions, model_versions, prompt_versions)`, the system must produce the same output. Provenance records these four keys for every Signal.

### P6 — Fail Loud, Fail Traceable
Errors never silently drop. Every failure produces (a) a structured error event in the operational log, (b) a clear human-readable explanation, (c) the input that caused it.

### P7 — Cost-Aware by Default
LLM calls are the dominant cost. Specs must specify **when** an LLM is required vs. when a rule/lookup suffices. See [02_agent_constitution.md#cost-classification](02_agent_constitution.md).

### P8 — Locality of Change
Adding a new signal type or new data source requires changes in **at most three documents** (taxonomy, schema, agent). If it requires more, the abstraction is wrong.

### P9 — Humans Override, Never Veto
Curator overrides adjust scores, not facts. Audit log retains both the system score and the override.

---

## 3. The Core Concept: Signal

### 3.1 Definition (recap, see 01 for full spec)

A **Signal** is a structured, evidence-backed claim that an observable change has occurred and may materially affect a forward-looking investment thesis.

```
Signal := (entity_ref, type, claim, evidence, timestamp, score, provenance)
```

### 3.2 Why Signals (Not Events, Not Stories)

| Abstraction | Problem | Signal's advantage |
|---|---|---|
| Raw event ("Apple announced Q3 earnings") | No interpretation of impact | Adds a falsifiable claim + impact score |
| Story ("Apple is doing great") | Unstructured, not auditable | Structured, single sentence, evidence-linked |
| News headline | Ambiguous entity, no direction | Entity-resolved, direction-tagged, horizon-tagged |

### 3.3 Signal Anatomy (visual)

```
                    ┌──────────────────────┐
                    │       Signal          │
                    ├──────────────────────┤
                    │ id  (ULID)            │
   Entity ─────────►│ entity_ref ───────┐  │
   Taxonomy ───────►│ type             │  │
                    │ claim            │  │──► Score (5 dims)
   Evidence ───────►│ evidence[]       │  │──► Status (lifecycle)
   Time ───────────►│ timestamp        │  │
                    │ detected_at      │  │
                    │ direction        │  │
                    │ horizon          │  │
                    │ provenance       │  │
                    └──────────────────┘  │
                              │           │
                              ▼           ▼
                          Reports      Watchlist
```

---

## 4. System Architecture

### 4.1 Layered View

```
┌──────────────────────────────────────────────────────────────────────┐
│  Layer 5 · OUTPUT          Reports, Alerts, Watchlist Updates        │
├──────────────────────────────────────────────────────────────────────┤
│  Layer 4 · SYNTHESIS       Multi-Signal thesis construction           │
├──────────────────────────────────────────────────────────────────────┤
│  Layer 3 · REASONING       Significance, causality, durability        │
├──────────────────────────────────────────────────────────────────────┤
│  Layer 2 · SCORING         Quantitative evaluation (5 dimensions)     │
├──────────────────────────────────────────────────────────────────────┤
│  Layer 1 · DETECTION       Candidate Signal extraction from raw data  │
├──────────────────────────────────────────────────────────────────────┤
│  Layer 0 · INGESTION       Raw data acquisition + normalization       │
└──────────────────────────────────────────────────────────────────────┘
```

Each layer consumes artifacts produced by the layer below. Each artifact has a schema in [04_data_schema.md](04_data_schema.md).

### 4.2 Data Flow (End-to-End)

```
 ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
 │  Source   │───►│ Harvester│───►│  Raw     │    │          │
 │  (RSS,    │    │ (agent)  │    │  Store   │    │          │
 │   SEC,    │    └──────────┘    └────┬─────┘    │          │
 │   etc.)   │                         │          │          │
 └──────────┘                         ▼          │          │
                                   ┌──────────┐  │          │
                                   │ Detector │  │  Signal  │
                                   │ (agent)  │──►  Store   │
                                   └────┬─────┘  │          │
                                        │        │          │
                                        ▼        │          │
                                   ┌──────────┐  │          │
                                   │ Verifier │  │          │
                                   │ (agent)  │──►          │
                                   └────┬─────┘  │          │
                                        │        │          │
                                        ▼        │          │
                                   ┌──────────┐  │          │
                                   │ Analyst  │  │          │
                                   │ (agent)  │──►          │
                                   └────┬─────┘  │          │
                                        │        │          │
                                        ▼        │          │
                                   ┌──────────┐  │          │
                                   │  Scorer  │  │          │
                                   │ (agent)  │──►          │
                                   └────┬─────┘  │          │
                                        │        │          │
                              ┌─────────┴──────┐ │          │
                              ▼                ▼ ▼          │
                        ┌──────────┐    ┌──────────────┐     │
                        │ Synthesiz│    │   Reporter   │◄────┘
                        │ er (agnt)│    │   (agent)    │
                        └────┬─────┘    └──────┬───────┘
                             │                 │
                             ▼                 ▼
                       Watchlist Δ         Daily Report
```

(Detailed agent contracts: [02_agent_constitution.md](02_agent_constitution.md). Workflow sequencing: [03_workflow_constitution.md](03_workflow_constitution.md).)

### 4.3 Storage Tiers

| Tier | Contents | Access pattern | Tech target |
|---|---|---|---|
| **Hot** | Active Signals (last 7 days), today's raw docs | Sub-second read | In-memory + Redis |
| **Warm** | Signals (last 90 days), scored entities | < 1s read | PostgreSQL / SQLite |
| **Cold** | Full Signal history, raw documents | Seconds, audit-only | Object storage + search index |

### 4.4 Deployment Topology

A minimal production deployment:

```
                ┌────────────────────┐
                │   Scheduler / Cron │
                └─────────┬──────────┘
                          │ triggers
                          ▼
   ┌──────────────────────────────────────────────┐
   │              Pipeline Runner                  │
   │  ┌────┐  ┌────┐  ┌────┐  ┌────┐  ┌────┐     │
   │  │Hrv │→ │Det │→ │Vrf │→ │Ana │→ │Scr │→…   │
   │  └────┘  └────┘  └────┘  └────┘  └────┘     │
   └─────────────────┬────────────────────────────┘
                     │
        ┌────────────┼────────────┐
        ▼            ▼            ▼
    Raw Store   Signal Store   Output Bucket
    (object)    (SQL)          (markdown/json)
```

Scaling concerns and cloud patterns: [08_architecture.md](08_architecture.md).

---

## 5. Workflow

### 5.1 Canonical Pipeline (per ingestion cycle)

A "cycle" runs every N minutes during market hours (N = 15 by default) and every 4 hours off-hours. The canonical workflow `ingest_cycle` (W1) has **9 stages**, mapped to agents where applicable:

| # | Stage | Type | Agent / Function | Output status |
|---|---|---|---|---|
| S1 | Harvest | agent | `harvester` | RawItem[] |
| S2 | Normalize | function | `normalize()` | RawDocument[] |
| S3 | Dedup | function | `dedup()` | RawDocument[] (filtered) |
| S4 | Detect | agent | `detector` | Signal[] (status=`draft`) |
| S5 | Verify | agent | `verifier` | Signal[] (status=`verified`/`rejected`) |
| S6 | Reason | agent | `analyst` | Signal[] (reasoning populated; `reasoning_skipped` for tier_3/4) |
| S7 | Score | agent + function | `scorer` + `compute_composite()` | Signal[] (score populated) |
| S8 | Gating | function | `gate()` | Signal[] (status=`active`/`held`/`rejected`) |
| S9 | Persist | function | `persist()` | SignalStore writes |

Stages S2, S3, S8, S9 are deterministic (P4). The Synthesis and Report stages happen in **separate workflows** (W3 `synthesis_cycle`, W4 `report_cycle`), not in the ingest cycle. See [03 §3 and §9](03_workflow_constitution.md) for the full stage catalog and other workflows.

Per-tier stage skipping rules (tier_3 / tier_4 do not invoke S6, etc.) are in [14 §3.1](14_watchlist.md).

### 5.2 Sequence Diagram (happy path)

```
Harvester   Detector   Verifier   Analyst    Scorer   Reporter
   │            │          │          │          │          │
   │ raw[]      │          │          │          │          │
   ├───────────►│          │          │          │          │
   │            │ cand[]   │          │          │          │
   │            ├─────────►│          │          │          │
   │            │          │ checked  │          │          │
   │            │          ├─────────►│          │          │
   │            │          │          │ reasoned │          │
   │            │          │          ├─────────►│          │
   │            │          │          │          │ scored   │
   │            │          │          │          ├─────────►│
   │            │          │          │          │          │
   │            │          │          │          │   report │
```

### 5.3 Trigger Modes

| Mode | When | Cadence | Notes |
|---|---|---|---|
| `scheduled` | Default | Every 15 min market hours, 4h off-hours | Drives steady coverage |
| `burst` | Breaking-news heuristic (volume spike, keyword match) | Within 60s of trigger | Skips non-critical dedup |
| `manual` | Curator request | On-demand | Used for deep-dive re-runs |
| `replay` | Audit / backtest | Time-range driven | Read-only, no scoring writes |

---

## 6. Users and Roles

### 6.1 Role Matrix

| Role | Primary tasks | Read access | Write access |
|---|---|---|---|
| **Reader** (PM / analyst) | Read daily/weekly reports; act on alerts | Signals (active), reports, watchlist | — |
| **Curator** (senior analyst) | Override scores, adjust tiers, mark noise | Everything | Signals (override flag), watchlist |
| **Operator** (engineer) | Monitor pipeline, tune agents, fix failures | Everything including operational logs | Agent configs, prompt versions |
| **Auditor** (risk / compliance) | Trace provenance, regenerate Signals from logs | Everything (read-only) | Audit annotations only |

### 6.2 Permission Model

Permissions are enforced at the API layer, not in the spec. The spec only defines **what each role is allowed to do**, not how it is gated.

---

## 7. Success Criteria

### 7.1 Per-Signal Quality Metrics

| Metric | Target | Measurement |
|---|---|---|
| Provenance completeness | 100% | `provenance.agent_chain` non-empty for every `active` Signal |
| Source reachability | ≥ 99% | `source_url` returns 2xx within 30s of fetch (daily sample) |
| Calibration (high-confidence) | ≥ 70% corroboration within 7d | Manual + automated backtest on holdout set |
| Composite-score calibration (Brier) | ≤ 0.20 | Backtest on holdout |
| Decay correctness | ≥ 95% | Signals decayed within 24h of expected window |

### 7.2 System-Level Metrics

| Metric | Target |
|---|---|
| Median latency, source→Signal | ≤ 4h (market hours), ≤ 18h (off-hours) |
| Coverage, Tier 1 weekly Signal rate | ≥ 95% of entities ≥ 1 Signal/week |
| Pipeline uptime | ≥ 99.5% during market hours |
| Cost per active Signal | ≤ $0.30 (LLM + storage amortized) |
| Reproducibility | 100% of Signals regeneratable from provenance inputs |

### 7.3 Failure Response

| Condition | Action |
|---|---|
| Calibration < 60% for 1 week | Page Curator; freeze new Signals; manual review |
| Calibration < 50% for 2 weeks | Suspend `active` publication; return to `verified` queue |
| Latency p95 > 8h for 1 day | Operator investigates; scaling change within 24h |
| Cost per Signal > $1.00 for 1 week | Cost review; prompt optimization mandate |

---

## 8. Non-Goals

The following are **explicitly out of scope** for v1.x:

- Buy/sell/hold recommendations with position sizing
- Automated trade execution of any kind
- Insider or non-public information processing (all sources must be **public and citable**)
- Real-time sub-second or tick-level responsiveness
- Forward earnings/price prediction as a primary output
- Compliance reporting (FILING, KYC, etc.)
- Mobile application

Each non-goal is a candidate v2.0 feature with its own RFC.

---

## 9. Edge Cases and Failure Modes

The system must handle the following explicitly. "Unhandled" is **not** acceptable — see P6.

### 9.1 Data Edge Cases

| Case | Expected behavior |
|---|---|
| Source returns 5xx | Retry with exponential backoff (max 3); if persistent, mark source as `degraded` for 1h |
| Source returns HTML with malformed encoding | Fall back to `<title>` + first 1KB; mark `extraction_confidence: low` |
| Two sources report the same event with conflicting facts | Keep both Signals; mark lower-confidence one `contested`; require analyst review within 24h |
| Raw document references a non-existent entity | Emit no Signal; log a `resolution_failure` event with the candidate entity string |
| Source publishes a retraction | Emit a `correction` Signal that supersedes any prior Signals citing the original |

### 9.2 Reasoning Edge Cases

| Case | Expected behavior |
|---|---|
| Detector cannot determine direction | Default to `neutral`; the detector's prompt lowers `confidence` by 0.1 (per [10 §4](10_signal_taxonomy.md) prior-dissent rule); require curator review if `confidence` drops below 0.5 |
| Two analyst runs reach different significance verdicts | Average the verdicts; if spread > 0.4, route to curator |
| Score composite lands in borderline zone (0.45–0.65) | Apply tie-breaker per [06 §5.3](06_scoring_framework.md): prefer higher `novelty`, then `timeliness`, then `confidence` |
| Signal contradicts a prior verified Signal on same entity | Both retained; newer wins by default unless `confidence` gap < 0.1 |

### 9.3 Operational Edge Cases

| Case | Expected behavior |
|---|---|
| LLM provider rate-limit | Queue with 60s backoff; never drop silently |
| LLM provider outage > 30 min | Page Operator; degraded mode uses regex-only detection |
| Storage backend unreachable | Pipeline halts at last successful checkpoint; resumes on recovery |
| Prompt version mismatch in provenance | Refuse to emit Signal; require operator re-publish of prompt version |
| Watchlist entity has 0 Signals for 30 days | Auto-emit a `staleness` alert to Curator (do not synthesize a Signal) |

### 9.4 Adversarial / Abuse Cases

| Case | Expected behavior |
|---|---|
| Source known to publish misinformation | Source disabled via Curator action; retroactive Signals marked `source_retracted` |
| Coordinated pumping (multiple sources same wording) | Cluster detected; if `novelty` drops below 0.2, all Signals downgraded |
| Quote splicing to alter meaning | `verifier` performs quote-context window check (50 chars before/after) |

---

## 10. Future Extensions

The following are **planned** or **considered** for v2.x. They are intentionally not in v1.x scope.

### 10.1 Near-term (v1.1–v1.3)

- **Entity-aware dedup** — merge Signals that share a causal chain (e.g., a CFO resignation that triggers guidance revision)
- **Multi-language sources** — first-class support for Chinese, Japanese, German filings
- **Embedding-based novelty** — replace string-similarity novelty with semantic embedding distance
- **Watchlist auto-suggestion** — system proposes new Tier 3 entities based on industry chain deltas

### 10.2 Medium-term (v1.4–v1.9)

- **Counterfactual scoring** — "what would this Signal look like if contradicted?"
- **User feedback loop** — Reader thumbs up/down on Signals feeds back into scorer training set
- **Sector-level Signals** — Signals whose `entity_ref.kind = sector` for macro/regulatory events

### 10.3 Long-term (v2.0+)

- **Signal explainer UI** — Interactive walk-through of every Signal's chain of reasoning
- **Cross-portfolio contagion** — Detect when Signals on one entity cascade to its supply chain
- **Personalized report cadence** — Per-reader digest based on what they actually act on
- **Real-time push** — Sub-minute latency tier for breaking-news mode only

### 10.4 Explicit Non-Future

These are **not** on any roadmap:
- Trade execution integration (would make SIGNAL a regulated trading system)
- Insider / alternative data ingestion (legal and reputational risk)

---

## 11. Document Map

### 11.1 Core Documents (Numbered)

| # | File | Purpose | Read when |
|---|---|---|---|
| 00 | `00_project_context.md` | This file — project charter + engineering reference | First |
| 01 | `01_signal_constitution.md` | What a Signal is and is not | Defining/extending signals |
| 02 | `02_agent_constitution.md` | Agent roles and contracts | Adding/changing agents |
| 03 | `03_workflow_constitution.md` | How agents are orchestrated | Changing pipelines |
| 04 | `04_data_schema.md` | All canonical schemas | Touching data structures |
| 05 | `05_reasoning_framework.md` | How significance is judged | Tuning reasoning |
| 06 | `06_scoring_framework.md` | How scores are computed | Changing scoring logic |
| 07 | `07_prompt_guidelines.md` | Prompt engineering standards | Writing prompts |
| 08 | `08_architecture.md` | Technical architecture | Deploying / scaling |
| 09 | `09_development_roadmap.md` | Phased delivery plan | Planning work |
| 10 | `10_signal_taxonomy.md` | Signal categories | Classifying signals |
| 11 | `11_industry_mapping.md` | Industry chain model | Mapping companies to chains |
| 12 | `12_company_schema.md` | Company entity schema | Adding/editing companies |
| 13 | `13_report_template.md` | Report output format | Generating reports |
| 14 | `14_watchlist.md` | Watchlist spec | Managing watchlist |

### 11.2 Governance & Auxiliary Documents (Unnumbered)

| File | Purpose | Read when |
|---|---|---|
| `INVARIANTS.md` | System-wide immutable constraints | Auditing / writing agents |
| `SPEC_VERSION.md` | Global version policy and bump rules | Cutting a release |
| `GLOSSARY.md` | Canonical term dictionary | Checking term usage |
| `GOVERNANCE.md` | RFC + ADR + Release Checklist processes | Proposing a change |
| `SCHEMA_EVOLUTION.md` | Schema MAJOR/MINOR/PATCH rules | Changing a schema |
| `REVIEW_NOTES.md` | Cross-document consistency audit log | Auditing spec consistency |
| `ADR/` | Architecture Decision Records | Understanding why a decision was made |
| `RFC/` | Proposals for spec changes | Proposing a change |
| `scripts/lint_spec.py` | Automated consistency checker | Pre-commit / pre-merge |

---

## 12. Versioning

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold |
| 0.2 | 2026-07-16 | Expanded to engineering reference (architecture, edge cases, future extensions) |

**Versioning policy:**
- **Major (X.0)** — Breaking: any invariant in §1, §2 principles, or schema contracts in 04/01. Requires migration note in `09_development_roadmap.md`.
- **Minor (0.X)** — Additive: new section, new edge case, new future-extension entry. Backward-compatible.
- **Patch (0.0.X)** — Typos, clarifications, example fixes.

Cross-document version dependency: documents MUST declare their required version of `00_project_context.md` in their own header. Mismatch is an integrator bug.