# Architecture Review — SIGNAL Project

> **Document role:** Independent architecture review. No implementation changes proposed. Identifies mission alignment, ownership gaps, and scope concerns. Read alongside [00_project_context.md](00_project_context.md).
>
> Review date: 2026-07-17.
> Scope: project-level architecture (mission, boundaries, components, ownership). Implementation details (concurrency, technology choice, deployment) are deliberately out of scope.

---

## 1. Executive Summary

SIGNAL is a **research data pipeline** that ingests public information about companies and industries, extracts structured *Signals*, scores them, and renders human-readable reports. The architecture is **layered** (6 layers) and **agent-based** (8 first-class agents + 1 background worker).

The project is **well-bounded at the value layer** (Signals are crisp; reports are crisp; non-goals are explicit). However, **ownership boundaries are blurry in three places**:

1. The **curator agent** spans three owner documents (Signal, Company, Watchlist) without a single authoritative scope statement.
2. The **industry chain graph** ([11](11_industry_mapping.md)) is referenced by Reasoning, Taxonomy, and Curation but has no formal owning role.
3. The **decay worker** is described in three places (01, 03, ADR-006) but is not cataloged as a first-class component.

A small number of components appear to **exceed the research mission**, primarily in the operational/governance layer. None are blocking, but two suggest the project is conflating *research system* with *engineering infrastructure*.

---

## 2. Mission Statement (Consolidated)

Stated across [00 §1](00_project_context.md), the mission is:

> SIGNAL is an AI Research Operating System for systematic investment research. It continuously ingests public information about companies, industries, and macro variables, extracts structured **Signals**, evaluates their significance using a uniform framework, and produces ranked outputs that support — but never replace — human investment judgment.

Three implicit mission boundaries follow from this statement:

| Boundary | Implication |
|---|---|
| **Type of value** | The system produces *research artifacts* (Signals, reports, watchlists), not decisions. |
| **Source domain** | Public, citable information only. Insider/alternative data is excluded. |
| **Time scale** | Research-grade (minutes to hours), not real-time / not HFT. |

The mission is **value-oriented** (what the user receives), not **process-oriented** (how the system operates). This is appropriate.

---

## 3. System Responsibilities

Derived from the spec, the system has **five primary responsibilities**:

| # | Responsibility | Owner doc | Notes |
|---|---|---|---|
| R1 | Acquire public information from configured sources | [02 §A1](02_agent_constitution.md) | `harvester` agent |
| R2 | Extract structured Signals from raw documents | [02 §A2](02_agent_constitution.md) | `detector` agent |
| R3 | Validate Signals against evidence and entity resolution | [02 §A3](02_agent_constitution.md) | `verifier` agent |
| R4 | Reason about significance, causality, durability | [02 §A4](02_agent_constitution.md) + [05](05_reasoning_framework.md) | `analyst` agent |
| R5 | Score Signals and gate publication | [02 §A5](02_agent_constitution.md) + [06](06_scoring_framework.md) | `scorer` agent + `gate()` function |

Two secondary responsibilities support the primary ones:

| # | Responsibility | Owner doc | Notes |
|---|---|---|---|
| R6 | Cluster multiple Signals into ThesisDeltas | [02 §A6](02_agent_constitution.md) + [03 §9](03_workflow_constitution.md) | `synthesizer` agent + W3 |
| R7 | Render Signals into human-readable reports | [02 §A7](02_agent_constitution.md) + [13](13_report_template.md) | `reporter` agent + W4 |

One cross-cutting responsibility:

| # | Responsibility | Owner doc | Notes |
|---|---|---|---|
| R8 | Allow human curation (override, tier, noise) | [02 §A8](02_agent_constitution.md) + [14](14_watchlist.md) | `curator` agent (human-in-the-loop) |

The **decay worker** (background job) supports the lifecycle but is not listed as a responsibility in [02 §2](02_agent_constitution.md) — see Finding 5.

**Assessment**: The eight first-class responsibilities map cleanly to the eight agents. The decomposition is sound.

---

## 4. Inputs and Outputs

### 4.1 Inputs

| Input type | Source | Consumed by | Spec |
|---|---|---|---|
| Public information (news, filings, press releases) | External sources via `SourceConnector` | `harvester` | [02 §A1](02_agent_constitution.md) |
| Source registry (URLs, auth, parser hints) | Operator configuration | `harvester` | implicit — not formally specified |
| Watchlist (entity list + tier) | `curator` action | Pipeline (filtering) | [14](14_watchlist.md) |
| Company master | Operator / Curator | entity resolution, context | [12](12_company_schema.md) |
| Industry chain graph | Curator | `analyst` causal reasoning | [11](11_industry_mapping.md) |
| Curator overrides (human input) | `curator` UI | Signal / Company / Watchlist | [02 §A8](02_agent_constitution.md) |
| Replay window | Auditor / Operator | W5 workflow | [03 §9](03_workflow_constitution.md) |

### 4.2 Outputs

| Output type | Consumer | Spec |
|---|---|---|
| Active Signals | Internal / Reports | [01](01_signal_constitution.md), [04 §4](04_data_schema.md) |
| ThesisDelta clusters | Internal / Reports | [04 §10.2](04_data_schema.md) |
| Daily Brief | Reader | [13 §3](13_report_template.md) |
| Weekly Review | Reader + Curator | [13 §4](13_report_template.md) |
| Per-Entity Brief | Reader | [13 §5](13_report_template.md) |
| Watchlist state changes | Internal / UI | [14](14_watchlist.md) |
| Staleness alerts | Curator | [00 §9.3](00_project_context.md) |
| JSON sidecars (machine-readable) | UI / downstream systems | [13 §6](13_report_template.md) |
| CycleReports (operational) | Operator | [04 §10.5](04_data_schema.md) |
| FailureEvents (operational) | Operator | [04 §10.4](04_data_schema.md) |

**Observation**: The system produces **one class of human-visible artifact** (research reports) and **three classes of operational artifacts** (alerts, cycle reports, failure events). The research/operational split is clean.

### 4.3 What the System Does NOT Produce

Per [00 §1.2](00_project_context.md) and [00 §8](00_project_context.md):

- Buy/sell/hold recommendations
- Position sizing
- Trade orders
- Forward earnings predictions (primary output)
- Compliance filings
- Mobile UI

**Assessment**: Non-goals are explicit and reasonable.

---

## 5. System Boundary

The system has a clear boundary at the **value layer** but a fuzzy one at the **infrastructure layer**.

### 5.1 Boundary (Value Layer) — Clear

```
┌─────────────────────────────────────────────────────────────┐
│ EXTERNAL                                                     │
│                                                              │
│  Sources ──public info──► ┌──────────────┐                   │
│                           │              │                   │
│  Curator UI ──human ────► │   SIGNAL     │ ──►  Reports      │
│                           │              │                   │
│  Operator ──config ─────► │  (research   │ ──►  Watchlist    │
│                           │   pipeline)  │                   │
│  Auditor ──replay ──────► │              │ ──►  Alerts       │
│                           └──────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

Inputs: public info + curator/operator/auditor input.
Outputs: reports + watchlist + alerts.
**Nothing goes out that resembles a recommendation or trade.**

### 5.2 Boundary (Infrastructure Layer) — Implied, Not Drawn

The system touches:
- LLM provider (Anthropic API) — via LLM Gateway ([08 §5](08_architecture.md))
- Object storage (S3 / GCS) — for raw documents and reports
- PostgreSQL — for Signal/Company/Industry/Override storage
- Redis — for hot caches
- Optional: vector DB (mentioned as future in [00 §10.1](00_project_context.md))

These are all **engineering infrastructure**, not part of the research mission. They are listed as implementation details, which is appropriate. **However**, the spec does not explicitly state "infrastructure components are NOT part of SIGNAL" — there is a small risk that future contributors will add features (e.g., UI styling, observability dashboards, alert routing) under the SIGNAL banner when they belong in surrounding infrastructure.

---

## 6. Component Inventory

Eight first-class agents per [02 §2](02_agent_constitution.md), plus one background worker (per ADR-006), plus infrastructure components in [08](08_architecture.md).

| Component | Type | Mission role | Owner doc | Status |
|---|---|---|---|---|
| `harvester` | Agent | R1 — acquire data | [02 §A1](02_agent_constitution.md) | Clearly owned |
| `detector` | Agent | R2 — extract Signals | [02 §A2](02_agent_constitution.md) | Clearly owned |
| `verifier` | Agent | R3 — validate Signals | [02 §A3](02_agent_constitution.md) | Clearly owned |
| `analyst` | Agent | R4 — reason | [02 §A4](02_agent_constitution.md) | Clearly owned |
| `scorer` | Agent | R5 — score | [02 §A5](02_agent_constitution.md) | Clearly owned |
| `synthesizer` | Agent | R6 — cluster | [02 §A6](02_agent_constitution.md) | Clearly owned |
| `reporter` | Agent | R7 — render reports | [02 §A7](02_agent_constitution.md) | Clearly owned |
| `curator` | Agent (HITL) | R8 — human curation | [02 §A8](02_agent_constitution.md) | **Cross-cutting scope** — see Finding 1 |
| Decay worker | Background job | Lifecycle management | None formally; ADR-006 + [01 §3](01_signal_constitution.md) | **Unowned** — see Finding 2 |
| IndustryChain graph | Data model | Reasoning context | [11](11_industry_mapping.md) | **Boundary unclear** — see Finding 3 |
| Watchlist | Data model + curation state | Pipeline filtering | [14](14_watchlist.md) | Owned, but overlaps with curator and Company — see Finding 4 |
| Company master | Data model | Entity resolution | [12](12_company_schema.md) | Clearly owned |
| LLM Gateway | Infrastructure | Mediates all LLM calls | [08 §5](08_architecture.md) | Owned, but cross-cuts every agent's cost — see Finding 6 |
| Hot/Warm/Cold storage | Infrastructure | Persistence | [08 §3](08_architecture.md) | Owned |
| API Gateway / Read API / Query Service | Infrastructure | Delivery mechanism | [08 §2.1](08_architecture.md) | Owned |
| Source registry | Configuration | Pipeline config | Implicit | **Not specified** — see Finding 7 |
| Governance docs (INVARIANTS, GOVERNANCE, GLOSSARY, SPEC_VERSION, SCHEMA_EVOLUTION) | Engineering practice | Spec integrity | Multiple | Owned (engineering scope) — see Finding 8 |
| Spec linter (`scripts/lint_spec.py`) | Engineering tool | Consistency check | n/a (tool) | Owned |

**Assessment**: 14 of 18 components have clear ownership. Four have ownership gaps (curator scope, decay worker, industry chain, source registry).

---

## 7. Findings — Components With Unclear Ownership

### Finding 1 — Curator Agent Spans Three Owner Documents

**Symptom**: The `curator` agent in [02 §2](02_agent_constitution.md) is labeled "Cross-cutting" and its actions target:
- **Signals** (per [02 §A8](02_agent_constitution.md) and [04 §6 OverrideRecord](04_data_schema.md)): `adjust_score`, `mark_noise`, `mark_redundant`
- **Companies** (per [12 §12](12_company_schema.md) and [04 §6 OverrideRecord](04_data_schema.md)): `change_tier`, `bind_industry_position`, `update_notes`
- **Watchlist** (per [14](14_watchlist.md)): `add_entity`, `remove_entity`, `change_tier`, `bind_industry_position`, `update_notes`

The 8 OverrideRecord actions in [04 §6](04_data_schema.md) span all three. The curator itself is described in [02](02_agent_constitution.md), but its actions on Companies are described in [12](12_company_schema.md), and its actions on Watchlist are described in [14](14_watchlist.md).

**Question**: Is the curator **a single agent with a wide scope**, or **three specialized roles** (Signal curator, Company curator, Watchlist curator) that share an authentication model?

**Risk**:
- Permission model is unclear. Does a curator of tier_1 watchlist entries also have permission to mark Tier 3 Signals as noise?
- The `bind_industry_position` action lives in [11 §8.3](11_industry_mapping.md) curator authority but is recorded in [12 §9](12_company_schema.md). The curator effectively maintains a graph data structure but is described as a research-data actor.

### Finding 2 — Decay Worker Is Not Cataloged

**Symptom**: The decay worker:
- Sets Signal status to `decayed` (referenced in [01 §3](01_signal_constitution.md), lifecycle table)
- Is described in [03 §3](03_workflow_constitution.md) only by inference (S9 persist may be related)
- Is the actor behind [01 §4](01_signal_constitution.md) rule 2 and [05 §3.2](05_reasoning_framework.md) precedent outcome recording
- Has its own ADR ([ADR-006](ADR/ADR-006-decay-worker.md)) explaining it is **deliberately not an agent**

**Question**: If the decay worker is a first-class operational component, where is its catalog entry?

**Risk**:
- It mutates SignalStore and writes PrecedentOutcome records — these are not trivial operations.
- Its failure modes (running late, crashing, missing outcomes) are not documented anywhere except ADR-006.
- New operators may not realize it exists as a separate process.

### Finding 3 — Industry Chain Graph Has No Owning Role

**Symptom**: The industry chain graph ([11](11_industry_mapping.md)) is **read** by:
- `analyst` agent for CausalLink traversal ([05 §2.2](05_reasoning_framework.md))
- `reporter` for "Industry / Macro" report sections ([13 §3 §4](13_report_template.md))

It is **written** by:
- `curator` via `bind_industry_position` action ([11 §8.3](11_industry_mapping.md), [04 §6](04_data_schema.md))
- Initial build by unspecified operators ([11 §8.1](11_industry_mapping.md))

**Question**: The graph has a chain schema ([11 §6](11_industry_mapping.md)) and lives in `industry_db` ([08 §3.2](08_architecture.md)), but **who is responsible for its quality, freshness, and coverage**?

**Risk**:
- The graph is critical reasoning infrastructure (cross-portfolio contagion depends on it per [00 §10.3](00_project_context.md)).
- No component is named "IndustryCurationAgent" or equivalent; the curator's `bind_industry_position` action implies the curator maintains this graph alongside other duties.
- Chain edits are described as a curator authority, but the curator's primary role (per [02 §A8](02_agent_constitution.md)) is overriding Signal scores. Conflating these responsibilities is a future risk.

### Finding 4 — Watchlist Overlaps Company Master and Curator Scope

**Symptom**: `WatchlistRef` is a field on `Company` ([12 §10](12_company_schema.md)) AND a separate spec ([14](14_watchlist.md)) AND managed by curator ([02 §A8](02_agent_constitution.md)).

The watchlist is **read** by:
- Pipeline (per-tier stage skipping per [14 §3.1](14_watchlist.md))
- Burst trigger ([14 §11.2](14_watchlist.md))

The watchlist is **written** by:
- Curator (tier changes, add/remove)
- System (staleness alerts per [00 §9.3](00_project_context.md))

**Question**: Is the watchlist **a query over Company master** (companies where `watchlist != null`) or **a separate first-class entity**?

**Risk**:
- If it's a query, then [14](14_watchlist.md) is a *view spec* and should not have its own lifecycle (add/remove should mutate `Company.watchlist`, not a separate entity).
- If it's a first-class entity, then [12](12_company_schema.md)'s `WatchlistRef` should be a foreign key, not an embedded object.
- Currently it's a hybrid: `WatchlistEntry` is a separate type in [14 §1](14_watchlist.md) but `WatchlistRef` is embedded in `Company`. The two representations may diverge.

### Finding 5 — Source Registry Has No Specification

**Symptom**: The `harvester` agent takes "Source descriptors" as input ([02 §A1](02_agent_constitution.md)) but no document specifies the source registry schema, list of supported sources, authentication patterns, or health check protocol.

The closest things:
- `SourceConnector` interface ([02 §A1](02_agent_constitution.md), Python Protocol)
- `healthcheck()` returning `SourceHealth` ([02 §A1](02_agent_constitution.md))
- A config file `config/sources.yaml` referenced in [03 §12](03_workflow_constitution.md)

**Question**: What is the source-of-truth for "what sources exist, how are they configured, who manages them"?

**Risk**:
- New sources are added per [P8 locality](00_project_context.md) (≤ 3 docs), but without a registry doc, contributors may scatter source config across code.
- No documented authority for "is this source trustworthy enough to ingest?" — only the curator can disable sources after the fact.

### Finding 6 — LLM Gateway Cross-Cuts Agent Cost Without Own Scope

**Symptom**: Every LLM-using agent ([02 §A2–§A7](02_agent_constitution.md)) has a cost class. The LLM Gateway ([08 §5](08_architecture.md)) mediates all calls. Cost budgets are defined in [03 §7](03_workflow_constitution.md). Cost tracking is a runtime concern.

**Question**: Is "cost control" an agent concern, a workflow concern, or an infrastructure concern?

**Risk**:
- A cost regression could be caused by (a) agent prompt changes, (b) workflow stage skipping rule changes, (c) gateway caching changes, or (d) external model pricing changes. Four possible owners, no clear escalation path.
- The current spec treats cost as a budget ([03 §7](03_workflow_constitution.md)) rather than a quality metric. If a budget is exceeded, the cycle degrades rather than the agent prompts being improved.

### Finding 7 — Cost Authority Fragmented

**Symptom**: Cost-related rules live in three places:
- [02 §4](02_agent_constitution.md) — cost classes per agent (`free`/`cheap`/`moderate`/`expensive`)
- [03 §7](03_workflow_constitution.md) — workflow-level budgets
- [08 §5.3](08_architecture.md) — LLM Gateway runtime tracking

**Question**: If someone wants to change the cost budget for `burst_cycle`, where is the authoritative number?

**Observation**: There is no clear single authority. A future change to cost semantics requires touching three documents.

---

## 8. Findings — Components That Exceed Mission

### Finding 8 — Governance Documentation Is Engineering Overhead, Not Research Output

**Symptom**: The following documents serve spec integrity, not research value:
- `INVARIANTS.md` — system-wide rules
- `SPEC_VERSION.md` — versioning policy
- `GLOSSARY.md` — terminology
- `GOVERNANCE.md` — change process
- `SCHEMA_EVOLUTION.md` — schema upgrade rules
- `REVIEW_NOTES.md` — audit log
- `ADR/` — decision records
- `RFC/` — proposal templates
- `scripts/lint_spec.py` — automated checks

**Assessment**: These are **necessary** for a production-quality research system per [00 §1.4](00_project_context.md). They do not exceed the mission; they enable the mission. The mission says "production-grade" — these docs make that possible.

**However**, they should be **explicitly framed as engineering scaffolding**, not research artifacts. The current [00 §11.2](00_project_context.md) lists them in the "Document Map" but doesn't label them as engineering overhead. A future contributor might add a research-feature spec in this style by mistake.

### Finding 9 — Real-Time Push Tier Crosses Latency Boundary

**Symptom**: [00 §10.3](00_project_context.md) lists "Real-time push — Sub-minute latency tier for breaking-news mode only" as a v2.0 future extension.

**Assessment**: This **does exceed the stated latency boundary** ("research-grade, not HFT-grade") if implemented as a system-wide tier. If implemented as a narrow "breaking-news alert only" mode that bypasses some quality gates, it conflicts with [P3](00_project_context.md) (Evidence Before Opinion) and may produce low-quality outputs.

**Recommendation framing** (for the team, not implementation): if v2.0 includes real-time push, the spec should clearly mark it as **breaking-news tier only** with separate quality thresholds, not as a general latency improvement.

### Finding 10 — Curator Industry-Position Editing Is Outside Curation Mission

**Symptom**: The `curator` agent's actions include `bind_industry_position` ([04 §6 OverrideRecord.action](04_data_schema.md), [11 §8.3](11_industry_mapping.md)). This action maintains a graph data structure ([11](11_industry_mapping.md)).

**Assessment**: Industry-chain binding is **data curation**, not signal curation. The curator's name suggests "curator of Signal quality"; binding industry positions is "curator of Company graph data". These are different jobs with different expertise requirements (industry knowledge vs analytical reasoning).

**Risk**: An analyst-typed curator may not be qualified to maintain industry mappings; an industry-data curator may not have Signal context. The current single curator role conflates these.

---

## 9. Findings — Mission Alignment Summary

| Component | Mission alignment | Concern |
|---|---|---|
| 8 research agents | Direct | None |
| Decay worker | Direct (lifecycle) | Unowned formally |
| Industry chain graph | Direct (reasoning input) | Unowned formally |
| Watchlist | Direct (pipeline input) | Overlaps Company master |
| Company master | Direct (entity resolution) | Watchlist field embedded |
| LLM Gateway | Infrastructure | Cost authority fragmented |
| Storage tiers | Infrastructure | None |
| API Gateway / Read API / Query Service | Delivery mechanism | Slightly outside mission, justified |
| Source registry | Configuration | **Unspecified** |
| Governance docs (5+) | Engineering practice | Necessary but should be labeled as such |
| Linter script | Engineering tool | None |
| ADR/RFC | Engineering process | None |
| Real-time push tier (future) | **Exceeds latency boundary** if general | Mark as breaking-news-only if implemented |
| Curator `bind_industry_position` | **Conflates curation roles** | Consider separating industry-data curation |

---

## 10. Top-Level Observations

1. **The system is well-designed for its stated mission.** Signal extraction, scoring, and reporting are crisp. Non-goals are explicit. Architecture is layered.

2. **Ownership gaps are local and fixable.** The decay worker and source registry can be added to existing documents (or get small dedicated docs) without restructuring.

3. **The curator role is the most architecturally suspicious element.** Its cross-cutting nature and the inclusion of `bind_industry_position` suggest it should be split into (a) Signal curator and (b) Watchlist/Company curator.

4. **The industry chain graph has no dedicated maintainer.** It is critical reasoning infrastructure but maintained by whoever happens to be a curator.

5. **Cost control is fragmented.** Three documents own cost rules; one place should.

6. **Governance docs are healthy engineering scaffolding** — not exceeding mission, but should be explicitly labeled as such.

7. **Real-time push in v2.0 is a boundary risk** — should be designed as a separate tier with quality gate, not a general latency improvement.

---

## 11. Recommendations (No Implementation)

This is a **review only**. The following recommendations are framings for the team to consider, not action items.

| # | Recommendation | Type | Effort |
|---|---|---|---|
| R1 | Decide whether curator is one role or two; if two, split the spec | Ownership | Medium |
| R2 | Add decay worker to a small "Background Jobs" section in [02](02_agent_constitution.md) or create `BACKGROUND_JOBS.md` | Ownership | Low |
| R3 | Decide whether watchlist is a view over Company or a first-class entity; align [12](12_company_schema.md) and [14](14_watchlist.md) accordingly | Boundary | Medium |
| R4 | Create `SOURCES.md` (or extend [02](02_agent_constitution.md)) with source registry schema, authority, and onboarding flow | Ownership | Low |
| R5 | Consolidate cost rules into one section (likely [02 §4](02_agent_constitution.md)) and have other docs reference it | Authority | Low |
| R6 | Label engineering scaffolding docs explicitly in [00 §11.2](00_project_context.md) as "Engineering practice (not research output)" | Clarity | Low |
| R7 | If v2.0 real-time push is pursued, design it as a breaking-news-only tier with documented quality gates | Boundary | High |
| R8 | Consider whether `bind_industry_position` belongs to the curator or to a separate industry-data role | Mission | Medium |

None of these recommendations block v1.x. They are pre-emptive clarifications for v1.1–v1.5.

---

## 12. Reviewer Notes

- This review reads only spec documents, not implementation. Findings are based on what is *documented*, not what is *built*. Implementation may have resolved some gaps already.
- "Mission" is interpreted as the *value-delivering* purpose of SIGNAL. Engineering practice is in scope for review but is evaluated separately from research value.
- "Component" is used loosely to mean any named entity in the spec (agent, schema, document, infra piece). A stricter taxonomy might call some of these "concerns" rather than components.
- No recommendation in §11 has been implemented. This document is for the team to consider.

---

## 13. Version History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-17 | Initial architecture review |