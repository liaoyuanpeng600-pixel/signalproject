# Ownership Matrix — Single Primary Owner per Component

> **Document role:** Define a **single primary owner** for every major component in the SIGNAL spec set. Resolves the ownership ambiguities identified in [ARCHITECTURE_REVIEW.md §7](ARCHITECTURE_REVIEW.md). No implementation; this is a clarification of authority.
>
> Read alongside: [00_project_context.md](00_project_context.md), [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md).
>
> Status: **draft for review**. Does not modify any agent, schema, or workflow yet. Once accepted, ownership becomes a binding principle that future PRs must respect.

---

## 1. Purpose

The architecture review surfaced four ownership gaps:

1. The **curator** role spans three owner documents.
2. The **decay worker** is not cataloged.
3. The **industry chain graph** has no formal maintainer.
4. The **source registry** is implicit, not specified.

This document declares **a single primary owner for every component**, by name and by document. The principle is:

> **For every component, exactly one document is the authoritative source of its definition. Other documents reference, never redefine.**

This matches principle [P2 in 00 §2](00_project_context.md). The matrix below makes it operational.

---

## 2. Reading Guide

Each entry in the matrix has four fields:

| Field | Meaning |
|---|---|
| **Component** | The named thing being owned |
| **Type** | What kind of thing it is (Agent / Schema / Workflow / Doc / Infra / Process) |
| **Primary Owner** | The single document that defines this component |
| **Secondary Stakeholders** | Documents that **read or trigger** this component but do not define it |

The matrix is split into:

- §3 — Research-data components (Signals, Companies, Watchlist, Industry Graph, Source Registry)
- §4 — Pipeline components (Agents, Workflows, Background Jobs)
- §5 — Output components (Reports, Reporter)
- §6 — Cross-cutting concerns (Reasoning, Scoring, Prompts, LLM Gateway, Cost, Storage, API)
- §7 — Governance components

For each component, §8 provides a one-paragraph ownership statement suitable for quoting in PRs and code-review comments.

---

## 3. Research-Data Components

| Component | Type | Primary Owner | Secondary Stakeholders |
|---|---|---|---|
| **Signal** (concept) | Domain object | [01_signal_constitution.md](01_signal_constitution.md) | [04](04_data_schema.md), [05](05_reasoning_framework.md), [06](06_scoring_framework.md), [02 §A2–A5](02_agent_constitution.md) |
| **Signal** (schema fields) | Schema | [04 §4](04_data_schema.md) | [01](01_signal_constitution.md), [02](02_agent_constitution.md) |
| **Evidence** | Schema | [04 §5](04_data_schema.md) | [01 §1](01_signal_constitution.md), [02 §A3](02_agent_constitution.md) |
| **Provenance** | Schema | [04 §6](04_data_schema.md) | [02](02_agent_constitution.md), [12 §12](12_company_schema.md), [14 §9](14_watchlist.md) |
| **OverrideRecord** | Schema | [04 §6](04_data_schema.md) | [02 §A8](02_agent_constitution.md), [14 §9](14_watchlist.md) |
| **Reasoning** | Schema | [04 §8](04_data_schema.md) | [05_reasoning_framework.md](05_reasoning_framework.md), [02 §A4](02_agent_constitution.md) |
| **Score** | Schema | [04 §7](04_data_schema.md) | [06_scoring_framework.md](06_scoring_framework.md), [02 §A5](02_agent_constitution.md) |
| **Signal lifecycle / status graph** | Rule | [01 §3](01_signal_constitution.md) | [04 §4.1](04_data_schema.md), [03 §S9](03_workflow_constitution.md) |
| **Company** (concept + schema) | Domain object | [12_company_schema.md](12_company_schema.md) | [02 §A3](02_agent_constitution.md), [14](14_watchlist.md), [11 §7](11_industry_mapping.md) |
| **Watchlist** (concept) | Curation state | [14_watchlist.md](14_watchlist.md) | [02 §A8](02_agent_constitution.md), [12 §10](12_company_schema.md), [03 §11.1](03_workflow_constitution.md) |
| **WatchlistRef** (field on Company) | Schema field | [12 §10](12_company_schema.md) | [14 §1](14_watchlist.md) |
| **Industry Graph** (nodes, edges, traversal) | Data model + rules | [11_industry_mapping.md](11_industry_mapping.md) | [05 §2.2](05_reasoning_framework.md), [13 §3 §4](13_report_template.md) |
| **IndustryNode / ChainEdge / IndustryChain** | Schema | [11 §2, §6](11_industry_mapping.md) | [12 §9](12_company_schema.md) (binding) |
| **Source Registry** | Configuration | [02 §A1 (SourceConnector interface)](02_agent_constitution.md) | [03 §5.2](03_workflow_constitution.md) (burst triggers), [08 §2.1](08_architecture.md) (deployment) |
| **RawDocument** | Schema | [04 §10.1](04_data_schema.md) | [02 §A1](02_agent_constitution.md), [03 §S2–S3](03_workflow_constitution.md) |
| **Signal taxonomy** (closed enum of types) | Taxonomy | [10_signal_taxonomy.md](10_signal_taxonomy.md) | [04 §4.1 Signal.type](04_data_schema.md), [02 §A2](02_agent_constitution.md) |
| **ThesisDelta / Cluster** | Schema | [04 §10.2 + §11](04_data_schema.md) | [02 §A6](02_agent_constitution.md), [03 §9 W3](03_workflow_constitution.md) |
| **CycleReport / FailureEvent** | Schema | [04 §10.4–§10.5](04_data_schema.md) | [03 §11](03_workflow_constitution.md), [08 §7](08_architecture.md) |

**Notes**:
- "Signal (concept)" is owned by [01](01_signal_constitution.md) because the *definition* (what counts as a Signal, invariants, lifecycle) lives there. "Signal (schema fields)" is owned by [04 §4](04_data_schema.md) because the *wire format* lives there. These are distinct concerns; both have one owner.
- "Watchlist" and "WatchlistRef" are split because the watchlist has its own lifecycle and policies, while the embedded ref on Company is just a pointer.

---

## 4. Pipeline Components

### 4.1 Agents

| Agent | Primary Owner | Secondary Stakeholders |
|---|---|---|
| `harvester` (A1) | [02 §A1](02_agent_constitution.md) | [03 §S1](03_workflow_constitution.md), [08 §4](08_architecture.md) |
| `detector` (A2) | [02 §A2](02_agent_constitution.md) | [03 §S4](03_workflow_constitution.md), [10 §4](10_signal_taxonomy.md), [07 §3.4](07_prompt_guidelines.md) |
| `verifier` (A3) | [02 §A3](02_agent_constitution.md) | [03 §S5](03_workflow_constitution.md), [12 §4](12_company_schema.md) (entity resolution) |
| `analyst` (A4) | [02 §A4](02_agent_constitution.md) | [03 §S6](03_workflow_constitution.md), [05](05_reasoning_framework.md) |
| `scorer` (A5) | [02 §A5](02_agent_constitution.md) | [03 §S7](03_workflow_constitution.md), [06](06_scoring_framework.md) |
| `synthesizer` (A6) | [02 §A6](02_agent_constitution.md) | [03 §9 W3](03_workflow_constitution.md), [04 §10.2](04_data_schema.md) |
| `reporter` (A7) | [02 §A7](02_agent_constitution.md) | [03 §9 W4](03_workflow_constitution.md), [13](13_report_template.md) |
| `curator` (A8) | [02 §A8](02_agent_constitution.md) | [14 §9](14_watchlist.md), [12 §12](12_company_schema.md), [04 §6](04_data_schema.md) (action enum) |

### 4.2 Background Jobs

| Job | Primary Owner | Secondary Stakeholders |
|---|---|---|
| **Decay worker** | [01 §3](01_signal_constitution.md) (lifecycle enforcement); with a small dedicated catalog entry pending | [03 §S9](03_workflow_constitution.md), [05 §3.2](05_reasoning_framework.md) (PrecedentOutcome), [ADR-006](ADR/ADR-006-decay-worker.md) |

**Resolution of Finding 2**: The decay worker's primary job is to enforce the lifecycle transitions defined in [01 §3](01_signal_constitution.md). Therefore [01](01_signal_constitution.md) owns the *what* (which transitions are valid); [03](03_workflow_constitution.md) owns the *when* (timing/conditions). The decay worker itself, as a named component, is described in ADR-006; future versions should give it a catalog entry analogous to agent §A1–§A8.

### 4.3 Workflows

| Workflow | Primary Owner | Secondary Stakeholders |
|---|---|---|
| W1 `ingest_cycle` | [03 §3–§4](03_workflow_constitution.md) | [00 §5.1](00_project_context.md) |
| W2 `burst_cycle` | [03 §9](03_workflow_constitution.md) | [08 §4](08_architecture.md) |
| W3 `synthesis_cycle` | [03 §9](03_workflow_constitution.md) | [02 §A6](02_agent_constitution.md) |
| W4 `report_cycle` | [03 §9](03_workflow_constitution.md) | [02 §A7](02_agent_constitution.md), [13](13_report_template.md) |
| W5 `replay_cycle` | [03 §9](03_workflow_constitution.md) | [08 §7](08_architecture.md) |
| Workflow stages (S1–S9) | [03 §3](03_workflow_constitution.md) | [02](02_agent_constitution.md) (agent specs) |
| Failure policies | [03 §6](03_workflow_constitution.md) | [02 §12](02_agent_constitution.md) (agent failure modes) |
| Budgets | [03 §7](03_workflow_constitution.md) | [02 §4](02_agent_constitution.md) (cost classes), [08 §5.3](08_architecture.md) (cost tracking) |
| Triggers (`scheduled` / `burst` / `manual` / `replay`) | [03 §5](03_workflow_constitution.md) | [00 §5.3](00_project_context.md), [08 §4.1](08_architecture.md) |

---

## 5. Output Components

| Component | Primary Owner | Secondary Stakeholders |
|---|---|---|
| **Daily Brief** (template + sections) | [13 §3](13_report_template.md) | [02 §A7](02_agent_constitution.md), [03 §9 W4](03_workflow_constitution.md) |
| **Weekly Review** | [13 §4](13_report_template.md) | same as above |
| **Per-Entity Brief** | [13 §5](13_report_template.md) | same as above |
| **JSON companion (machine-readable)** | [13 §6](13_report_template.md) | [00 §1.2](00_project_context.md) (UI consumer) |
| **Banned-word list** (report content policy) | [13 §2.7](13_report_template.md) | [02 §A7](02_agent_constitution.md) |
| **Citation format** | [13 §2.5](13_report_template.md) | [04 §6](04_data_schema.md) (provenance) |
| **Provenance footer in reports** | [13 §2.4](13_report_template.md) | [04 §6](04_data_schema.md) |

---

## 6. Cross-Cutting Concerns

| Concern | Primary Owner | Secondary Stakeholders |
|---|---|---|
| **Reasoning methodology** (significance, causality, durability, precedent) | [05_reasoning_framework.md](05_reasoning_framework.md) | [02 §A4](02_agent_constitution.md), [04 §8](04_data_schema.md) |
| **Scoring methodology** (5 dimensions + composite formula) | [06_scoring_framework.md](06_scoring_framework.md) | [02 §A5](02_agent_constitution.md), [04 §7](04_data_schema.md) |
| **Composite formula weights** (0.30/0.25/0.20/0.15/0.10) | [06 §4](06_scoring_framework.md) | [04 §7](04_data_schema.md), [02 §A5](02_agent_constitution.md) |
| **Gating thresholds** (composite ≥ 0.65 → active) | [03 §S8](03_workflow_constitution.md) (workflow side) ↔ [06 §5.1](06_scoring_framework.md) (scoring side) — **paired authority** | [04 §7](04_data_schema.md) |
| **Prompt engineering standards** | [07_prompt_guidelines.md](07_prompt_guidelines.md) | [02 §A1–A7](02_agent_constitution.md) |
| **Each agent's specific prompt(s)** | [02 §A_N](02_agent_constitution.md) | [07](07_prompt_guidelines.md), [prompt registry](07 §9](07_prompt_guidelines.md)) |
| **Model selection per task** | [07 §8](07_prompt_guidelines.md) | [02 §A_N](02_agent_constitution.md) |
| **Cost classes per agent** (free/cheap/moderate/expensive) | [02 §4](02_agent_constitution.md) | [03 §7](03_workflow_constitution.md), [08 §5.3](08_architecture.md) |
| **Workflow cost budgets** | [03 §7](03_workflow_constitution.md) | [02 §4](02_agent_constitution.md), [08 §5.3](08_architecture.md) |
| **LLM Gateway runtime / tracking** | [08 §5](08_architecture.md) | [02 §4](02_agent_constitution.md) |
| **Storage tiers** (Hot/Warm/Cold) | [08 §3](08_architecture.md) | [04](04_data_schema.md) (what is stored) |
| **Storage technology choices** | [08 §3.4](08_architecture.md) | none (technical detail) |
| **API Gateway / Read API / Query Service** | [08 §2.1](08_architecture.md) | none (technical detail) |
| **Deployment topology** | [08 §8](08_architecture.md) | none (technical detail) |
| **Observability metrics** | [08 §7](08_architecture.md) | [02 §A_N](02_agent_constitution.md), [03 §11](03_workflow_constitution.md) |
| **Security model** | [08 §6](08_architecture.md) | [02 §A2](02_agent_constitution.md) (prompt injection defense) |

**Resolution of Finding 6 / Finding 7 (cost authority fragmentation)**: The three cost-related concerns are now explicitly distinct:
- **Cost classes per agent** ([02 §4](02_agent_constitution.md)) — what each agent's calls cost.
- **Workflow cost budgets** ([03 §7](03_workflow_constitution.md)) — what each workflow may spend.
- **LLM Gateway runtime tracking** ([08 §5](08_architecture.md)) — how cost is measured.

These are not conflicting; they are different scopes. No consolidation needed, but the boundaries are now named.

**Resolution of "paired authority" for gating thresholds**: [03 §S8](03_workflow_constitution.md) and [06 §5.1](06_scoring_framework.md) both reference the same canonical number (0.65). One is the workflow-level *implementation* of the threshold; the other is the *scoring-level definition*. Neither can change without the other. **Changes must be made in both, in the same PR.**

---

## 7. Governance Components

| Component | Primary Owner | Secondary Stakeholders |
|---|---|---|
| **Invariants** (INV-1 through INV-N) | [INVARIANTS.md](INVARIANTS.md) | affected component docs |
| **SPEC_VERSION** (current version) | [SPEC_VERSION.md](SPEC_VERSION.md) | every doc header |
| **Document versioning policy** | [SPEC_VERSION §3](SPEC_VERSION.md) | every doc footer |
| **Schema evolution rules** (MAJOR/MINOR/PATCH) | [SCHEMA_EVOLUTION.md](SCHEMA_EVOLUTION.md) | [04](04_data_schema.md) |
| **Glossary** (canonical term definitions) | [GLOSSARY.md](GLOSSARY.md) | every doc |
| **RFC process** | [GOVERNANCE.md §2](GOVERNANCE.md) | every spec change |
| **ADR process** | [GOVERNANCE.md §3](GOVERNANCE.md) | decisions in `ADR/` |
| **ADR directory contents** | `ADR/README.md` | individual ADRs |
| **Release checklist** | [GOVERNANCE.md §5](GOVERNANCE.md) | [09 §11](09_development_roadmap.md) |
| **Migration log** | [09 §11](09_development_roadmap.md) | [SPEC_VERSION](SPEC_VERSION.md), [04 §13](04_data_schema.md) |
| **Spec linter** (`scripts/lint_spec.py`) | `scripts/lint_spec.py` (self-owned) | none |
| **Review notes** (audit log of consistency passes) | [REVIEW_NOTES.md](REVIEW_NOTES.md) | all docs |
| **Architecture review report** | [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) | this document (OWNERSHIP.md) |

---

## 8. Ownership Statements (Per Component)

These are the binding statements. Each one names exactly one owner.

### 8.1 Research-Data Components

> **Signal (concept) is owned by [01_signal_constitution.md](01_signal_constitution.md).** Any change to what counts as a Signal — invariants, lifecycle transitions, cardinality rules — must be made in [01](01_signal_constitution.md). Other documents reference these rules.

> **Signal (schema fields) is owned by [04 §4](04_data_schema.md).** Any change to a Signal's field names, types, or structure is made in [04](04_data_schema.md). The schema versioning table in [04 §13](04_data_schema.md) tracks every schema-version bump.

> **Company is owned by [12_company_schema.md](12_company_schema.md).** Identity model, classification, financials snapshot, governance, watchlist reference, industry positions, provenance — all defined in [12](12_company_schema.md). Other documents reference Company fields but do not redefine them.

> **Watchlist (as a curation concept) is owned by [14_watchlist.md](14_watchlist.md).** Tiers, lifecycle, policies, curation workflow, system-initiated actions — all defined in [14](14_watchlist.md).

> **WatchlistRef (the embedded field on Company) is owned by [12 §10](12_company_schema.md).** Its schema is part of the Company schema; lifecycle semantics (tier changes, history) belong to [14](14_watchlist.md).

> **The Industry Graph (nodes, edges, traversal rules) is owned by [11_industry_mapping.md](11_industry_mapping.md).** Edits to the graph require changes in [11](11_industry_mapping.md); consumers (analyst, reporter) reference but do not modify.

> **The Source Registry is owned by [02 §A1 (harvester)](02_agent_constitution.md)** via the `SourceConnector` interface. The schema for source descriptors, list of supported sources, authentication patterns, and health-check protocol are defined here. No other document may add a source.

> **The Signal taxonomy (closed enum of types) is owned by [10_signal_taxonomy.md](10_signal_taxonomy.md).** Adding or removing a type is a [10](10_signal_taxonomy.md) change, which (per [10 §6](10_signal_taxonomy.md)) requires a detector prompt bump.

### 8.2 Pipeline Components

> **Each of the 8 agents is owned by [02_agent_constitution.md](02_agent_constitution.md), §A1 through §A8.** No agent may be added, modified, or removed except via a change to [02](02_agent_constitution.md).

> **The decay worker is owned by [01_signal_constitution.md §3](01_signal_constitution.md)** (lifecycle enforcement). Its *what* (which transitions are valid) is defined in [01](01_signal_constitution.md). Its *when* (cadence, triggering conditions) is defined in [03 §S9](03_workflow_constitution.md). Its *how* (process architecture, rationale) is captured in [ADR-006](ADR/ADR-006-decay-worker.md). **A dedicated catalog entry is pending; until then, ADR-006 is the authoritative description.**

> **Each of the 5 workflows (W1–W5) is owned by [03_workflow_constitution.md](03_workflow_constitution.md).** Adding a workflow, changing a stage, or restructuring the workflow graph is a [03](03_workflow_constitution.md) change.

### 8.3 Output Components

> **Each of the 3 report templates (Daily Brief, Weekly Review, Per-Entity Brief) is owned by [13_report_template.md](13_report_template.md).** Format, sections, length caps, banned words, citation format, provenance footer — all defined in [13](13_report_template.md).

### 8.4 Cross-Cutting Concerns

> **Reasoning methodology is owned by [05_reasoning_framework.md](05_reasoning_framework.md).** Significance, causality, durability, reversibility, precedent matching — all defined in [05](05_reasoning_framework.md).

> **Scoring methodology (5 dimensions + composite formula) is owned by [06_scoring_framework.md](06_scoring_framework.md).** The composite formula is canonical in [06 §4](06_scoring_framework.md); [02 §A5](02_agent_constitution.md) quotes the weights but does not redefine them.

> **Gating thresholds are paired-owned by [03 §S8](03_workflow_constitution.md) and [06 §5.1](06_scoring_framework.md).** Any change to the threshold must be made in both documents in the same PR.

> **Prompt engineering standards are owned by [07_prompt_guidelines.md](07_prompt_guidelines.md).** Each agent's specific prompts live in `prompts/<agent>/<purpose>/vX.Y.Z.md`; the prompt registry is owned by [07 §9](07_prompt_guidelines.md).

> **Cost classes per agent are owned by [02 §4](02_agent_constitution.md).** Workflow cost budgets are owned by [03 §7](03_workflow_constitution.md). LLM Gateway runtime tracking is owned by [08 §5](08_architecture.md). These are three distinct scopes; no consolidation.

> **Storage tiers, deployment topology, API surface, observability, and security model are owned by [08_architecture.md](08_architecture.md).**

### 8.5 Governance Components

> **Invariants are owned by [INVARIANTS.md](INVARIANTS.md).** Adding, removing, or modifying an invariant requires an RFC.

> **SPEC_VERSION is owned by [SPEC_VERSION.md](SPEC_VERSION.md).** Version bumps follow the policy in [SPEC_VERSION §3](SPEC_VERSION.md).

> **Schema evolution rules (MAJOR/MINOR/PATCH) are owned by [SCHEMA_EVOLUTION.md](SCHEMA_EVOLUTION.md).**

> **Glossary entries are owned by [GLOSSARY.md](GLOSSARY.md).** Deprecated aliases are listed in [GLOSSARY §7](GLOSSARY.md).

> **RFC process is owned by [GOVERNANCE.md §2](GOVERNANCE.md).** ADR process is owned by [GOVERNANCE.md §3](GOVERNANCE.md).**

---

## 9. Resolving the Four Architecture-Review Findings

This matrix resolves the four findings from [ARCHITECTURE_REVIEW.md §7](ARCHITECTURE_REVIEW.md).

### 9.1 Finding 1 — Curator Agent Spans Three Owner Documents

**Resolution**: The curator *agent itself* is owned by [02 §A8](02_agent_constitution.md) (single primary owner). The actions it can perform are defined in [04 §6 OverrideRecord.action](04_data_schema.md) (single primary owner of the action enum). The *targets* of those actions are owned by the respective data documents:

| Action target | Target owner | Documented target behavior |
|---|---|---|
| Signals | [04 §4](04_data_schema.md) | status transitions |
| Companies | [12](12_company_schema.md) | field edits |
| Watchlist | [14](14_watchlist.md) | tier changes |

The curator is **one agent with multiple authorized targets**. This is consistent: the *what* (action enum) is owned by [04](04_data_schema.md); the *who* (agent definition) is owned by [02](02_agent_constitution.md); the *where* (target semantics) is owned by each target's owning document.

**No split of the curator is required by this matrix.** Whether to split is a future design decision (review recommendation R1); the ownership matrix can accommodate either choice.

### 9.2 Finding 2 — Decay Worker Is Not Cataloged

**Resolution**: The decay worker's *what* (lifecycle transitions) is owned by [01 §3](01_signal_constitution.md). Its *when* (cadence) is owned by [03 §S9](03_workflow_constitution.md). Its *how* is captured in [ADR-006](ADR/ADR-006-decay-worker.md).

A dedicated catalog entry in [02](02_agent_constitution.md) (analogous to §A1–§A8) is recommended in a future PR but is not required by this matrix. Until then, [ADR-006](ADR/ADR-006-decay-worker.md) is the authoritative description of the decay worker as a component.

### 9.3 Finding 3 — Industry Chain Graph Has No Owning Role

**Resolution**: The Industry Graph is owned by [11_industry_mapping.md](11_industry_mapping.md). This is unambiguous: schema, traversal rules, maintenance triggers, curator authority for binding — all defined in [11](11_industry_mapping.md).

The graph **does not require** a separate "industry-data curator" role; the existing curator (per [02 §A8](02_agent_constitution.md)) is authorized to call `bind_industry_position` per [04 §6 OverrideRecord.action](04_data_schema.md). Whether that is the right role assignment is review recommendation R8; the ownership matrix itself is clear.

### 9.4 Finding 5 — Source Registry Has No Specification

**Resolution**: The Source Registry is owned by [02 §A1 (harvester)](02_agent_constitution.md) via the `SourceConnector` interface. Source descriptors (`source_id`, `fetch_url`, `auth`, `parser_hint`) are input parameters to harvester; the interface is the spec.

A future enhancement may extract these to a dedicated `SOURCES.md` document. Until then, [02 §A1](02_agent_constitution.md) is the authoritative owner.

---

## 10. Open Questions (Not Resolved by This Matrix)

These remain ambiguous and should be addressed by separate PRs / RFCs:

| # | Question | Where to decide |
|---|---|---|
| OQ-1 | Should the curator be split into "Signal curator" and "Watchlist/Company curator"? | Future RFC (review R1) |
| OQ-2 | Should the watchlist be a separate first-class entity or a view over Company? | Future RFC (review R3) |
| OQ-3 | Should `bind_industry_position` be curator's job or a separate industry-data role? | Future RFC (review R8) |
| OQ-4 | Should there be a dedicated decay-worker catalog entry in [02](02_agent_constitution.md)? | Small PR, no RFC needed |
| OQ-5 | Should there be a dedicated `SOURCES.md` document? | Small PR, no RFC needed |
| OQ-6 | Should real-time push (v2.0 future) be a separate tier with its own quality gates? | RFC when v2.0 is scoped (review R7) |

**This matrix does not resolve these questions.** It only declares who *would own the decision* when it is made.

---

## 11. Acceptance Checklist (Before This Document Is Adopted)

To adopt this matrix as binding:

- [ ] Reviewer confirms the matrix resolves the four findings.
- [ ] No agent, schema, or workflow doc is modified as part of adoption (matrix is a clarification, not a change).
- [ ] A short note is added to [REVIEW_NOTES.md §7](REVIEW_NOTES.md) (Authority Table) referencing this matrix.
- [ ] [00 §11.2](00_project_context.md) document map links to this matrix.
- [ ] All four findings in [ARCHITECTURE_REVIEW.md §7](ARCHITECTURE_REVIEW.md) are annotated "ownership resolved by OWNERSHIP.md" (still no implementation).
- [ ] Future changes to any component in this matrix require updating the matrix in the same PR if ownership shifts.

---

## 12. What This Document Does NOT Do

To be explicit:

- It does **not** modify any agent, schema, or workflow.
- It does **not** add, remove, or split the curator.
- It does **not** create the `SOURCES.md` or any new document.
- It does **not** add a decay-worker catalog entry.
- It does **not** change any cost, threshold, or runtime behavior.
- It does **not** introduce new terminology.
- It does **not** change any version number.

It **only** declares which existing document owns which existing component.

---

## 13. Version History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-17 | Initial ownership matrix (draft for review) |