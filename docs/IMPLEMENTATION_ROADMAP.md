# Implementation Roadmap

> **Document role:** Defines the repository structure, module decomposition, and phased implementation plan for SIGNAL. Optimizes for delivering a working MVP before pursuing completeness.
>
> This document does not produce code. It describes what will be built, in what order, and how to know when each phase is done.
>
> Read alongside: [00_ARCHITECTURE_PRINCIPLES.md](../00_ARCHITECTURE_PRINCIPLES.md) (frozen), [01_OBJECT_MODEL.md](../01_OBJECT_MODEL.md) (frozen), [02_WORKFLOW_MODEL.md](../02_WORKFLOW_MODEL.md) (frozen), [03_RUNTIME_MODEL.md](../03_RUNTIME_MODEL.md) (frozen).
>
> **Implementation begins only after this roadmap is accepted.**

---

## Document Metadata

| Field | Value |
|---|---|
| **Status** | Draft for review |
| **Version** | 1.0 |
| **Effective Date** | TBD on acceptance |
| **Owner** | Architecture |

---

## Purpose

The Implementation Roadmap translates the frozen architecture into a buildable plan.

It answers four questions:

- **What does the repository look like?** — the directory structure.
- **What are the buildable units?** — the module decomposition.
- **In what order are they built?** — the phases.
- **How do we know when each phase is done?** — the exit criteria.

The roadmap optimizes for **MVP-first**: each phase produces a usable artifact. No phase exists purely as preparation for a later phase.

---

## Guiding Principle

**MVP before completeness.** A working end-to-end pipeline at 60% coverage is more valuable than a complete but unproven architecture. Each phase produces something that runs.

This is consistent with the [Architecture Principles](../00_ARCHITECTURE_PRINCIPLES.md) P3 (Evolution First) and P10 (Incremental Evolution): build, observe, refine.

---

## Repository Structure

```
SIGNAL/
├── docs/                          # frozen architecture
│   ├── 00_ARCHITECTURE_PRINCIPLES.md
│   ├── ARCHITECTURE_GOVERNANCE.md
│   ├── 01_OBJECT_MODEL.md
│   ├── 01_OBJECT_MODEL_ALIGNMENT_REPORT.md
│   ├── 02_WORKFLOW_MODEL.md
│   ├── 03_RUNTIME_MODEL.md
│   └── IMPLEMENTATION_ROADMAP.md   ← this document
├── ADR/                            # existing
├── RFC/                            # existing
├── scripts/                        # spec linter (existing)
├── src/                            # implementation
│   ├── core/                       # Phase 1
│   ├── workflow/                   # Phase 2
│   ├── runtime/                    # Phase 3
│   ├── persistence/                # Phase 4
│   ├── research/                   # Phase 5
│   └── reports/                    # Phase 6
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
└── deployment/                     # deferred (post-MVP)
```

**Top-level invariants:**
- `docs/` is read-only after freeze. Implementation does not modify architecture.
- `src/` and `tests/` mirror each other in structure.
- No code under `deployment/` until MVP is operational.

---

## Module Decomposition

Six implementation modules. Each has a single, well-defined responsibility and clear interfaces.

### Module 1 — `core/` (Phase 1)

**Responsibility.** Object Model types and lifecycle.

**Defines.**
- 7 core types: `Entity`, `Source`, `Evidence`, `Signal`, `Research`, `Thesis`, `Knowledge`
- Operational concepts: `Score`, `OverrideRecord`, `Cluster`, `ThesisDelta`, `CycleReport`
- Lifecycle operations: create, transition, retire, supersede
- Invariant enforcement (INV-1 through INV-12)

**Imports.** None (zero dependencies on other modules).

**Imported by.** All other modules.

### Module 2 — `workflow/` (Phase 2)

**Responsibility.** Workflow Model execution logic.

**Defines.**
- 6 stage implementations (Source Observation through Knowledge Update)
- 23 gate evaluators (per Workflow Model gate table)
- Cardinality rules
- Update rules (Path A/B/C, conflict handling, knowledge accumulation)
- Transition table

**Imports.** `core/`.

**Imported by.** `runtime/`, `research/`.

### Module 3 — `runtime/` (Phase 3)

**Responsibility.** Runtime Model components.

**Defines.**
- 7 runtime components: `Scheduler`, `Queue`, `Executor`, `Validator`, `Persistence` interface, `RetryManager`, `AuditLogger`
- Cycle orchestration
- Component integration
- Audit event schema

**Imports.** `core/`, `workflow/`, `persistence/` (interface only).

**Imported by.** `research/`, `reports/`.

### Module 4 — `persistence/` (Phase 4)

**Responsibility.** Object persistence per Object Model lifecycle rules.

**Defines.**
- Storage backend interface
- Lifecycle transitions: persist, retrieve, update, supersede
- Immutability enforcement (Evidence)
- Append-only enforcement (OverrideRecord)
- Checkpoint and restore

**Imports.** `core/`.

**Imported by.** `runtime/`, `research/`.

### Module 5 — `research/` (Phase 5)

**Responsibility.** Synthesis, curation, and calibration.

**Defines.**
- Synthesis logic (multi-Signal → Research; multi-Research → Thesis)
- Curator interface: override, mark_noise, mark_redundant, change_tier, etc.
- Calibration data emission
- Conflict surfacing (per Runtime Model OQ-7 resolution)

**Imports.** `core/`, `workflow/`, `runtime/`, `persistence/`.

**Imported by.** `reports/`.

### Module 6 — `reports/` (Phase 6)

**Responsibility.** Report generation and delivery.

**Defines.**
- 3 report templates: Daily Brief, Weekly Review, Per-Entity Brief
- Render engine
- Export formats (markdown, JSON)
- Scheduled report generation

**Imports.** `core/`, `runtime/`, `research/`.

**Imported by.** None (top-level consumer).

### Module Independence Rules

1. **Acyclic dependencies.** No module imports from a module that imports it (transitively).
2. **`core/` is the foundation.** All other modules import from `core/`; `core/` imports nothing.
3. **`persistence/` is interface-first.** Other modules depend on the `Persistence` interface, not on a concrete backend.
4. **`workflow/` is stateless.** Stages are pure functions of (input, persistence read); they hold no state themselves.
5. **`runtime/` orchestrates.** It depends on `workflow/`, `core/`, and `persistence/` interface. It does not duplicate their logic.

---

## Phases

Six phases. Sequential by default; parallelism noted where possible.

Each phase produces:
- A runnable artifact
- Unit and integration tests
- Updated `docs/` cross-references if needed (no architecture changes)

---

### Phase 1 — Core Objects

**Objective.** Implement the 7 Object types from the Object Model with full lifecycle support.

**Deliverables.**
- `src/core/entities/` — `Entity` and refinement support (Company, Industry as Entity subtypes)
- `src/core/sources/` — `Source` type with reachability tracking
- `src/core/evidence/` — `Evidence` type with immutability enforcement
- `src/core/signals/` — `Signal` type with lifecycle (draft → verified → active → ...)
- `src/core/research/` — `Research` type
- `src/core/theses/` — `Thesis` type with evolution history
- `src/core/knowledge/` — `Knowledge` accumulation interface
- `src/core/lifecycle/` — shared lifecycle operations
- Invariant checks (INV-1 through INV-12)
- Unit tests for each type
- Integration tests for lifecycle transitions

**Dependencies.** None. This is the foundation.

**Exit Criteria.**
- All 7 Object types defined per Object Model §"Core Objects"
- Lifecycle transitions enforce valid state graphs
- Invariants enforced (e.g., Evidence immutable, OverrideRecord append-only)
- All types testable in isolation
- Test coverage ≥ 90% for `core/` module

---

### Phase 2 — Workflow Engine

**Objective.** Implement the 6-stage pipeline with all 23 gates per the Workflow Model.

**Deliverables.**
- `src/workflow/stages/` — 6 stage implementations:
  - `source_observation.py` (Stage 1)
  - `evidence_production.py` (Stage 2)
  - `signal_extraction.py` (Stage 3)
  - `research_synthesis.py` (Stage 4)
  - `thesis_update.py` (Stage 5)
  - `knowledge_update.py` (Stage 6)
- `src/workflow/gates/` — 23 gate evaluators per Workflow Model gate table
- `src/workflow/cardinality/` — Cardinality enforcement (per Phase 2 cardinality section)
- `src/workflow/pipeline/` — Pipeline orchestrator (chains stages, manages transitions)
- Update rules implementation (Path A/B/C, conflict handling, knowledge accumulation)
- Unit tests for each stage and gate
- Integration tests for end-to-end pipeline execution (in-memory, no Runtime yet)

**Dependencies.** Phase 1 (`core/`).

**Exit Criteria.**
- All 6 stages implement their responsibilities per Workflow Model
- All 23 gates evaluable independently
- Cardinality rules enforced
- Failure paths correctly routed per Workflow Model
- End-to-end pipeline test: one Source → one Knowledge update, with assertions at each stage
- Test coverage ≥ 85% for `workflow/` module

**Parallelization note.** Stages 1, 2, 3, 4, 5, 6 can be implemented in parallel by separate contributors after the gate-evaluator interface is agreed. Stage 5 (Thesis Update) has the most complexity and should be sequenced last.

---

### Phase 3 — Runtime Engine

**Objective.** Implement the 7 runtime components per the Runtime Model.

**Deliverables.**
- `src/runtime/scheduler.py` — Cycle triggers (scheduled, burst, manual, replay)
- `src/runtime/queue.py` — Work item queue with bounded capacity
- `src/runtime/executor.py` — Stage execution dispatcher
- `src/runtime/validator.py` — Gate evaluation orchestrator (delegates to `workflow/gates/`)
- `src/runtime/persistence.py` — Persistence interface (delegates to `persistence/` module)
- `src/runtime/retry.py` — Retry Manager implementing Workflow retry paths
- `src/runtime/audit.py` — Audit Logger with append-only log
- Cycle orchestration
- 8 resolved Open Questions implemented (OQ-4, OQ-6, OQ-7, OQ-8, OQ-9, OQ-10, OQ-11, OQ-12)
- Unit tests for each component
- Integration tests for cycle execution

**Dependencies.** Phase 1 (`core/`), Phase 2 (`workflow/`), Phase 4 interface (`persistence/` interface).

**Exit Criteria.**
- All 7 components implemented per Runtime Model
- Cycle can be triggered (scheduled, manual)
- Stages execute in correct order
- Gate evaluations flow through Validator
- Retry paths implemented per Workflow Model
- Audit log captures all events
- Resolved Open Questions implemented
- Test coverage ≥ 85% for `runtime/` module

**Parallelization note.** The 7 components are mostly independent and can be developed in parallel after the interface contracts are agreed.

---

### Phase 4 — Persistence

**Objective.** Implement Object persistence per Object Model lifecycle rules.

**Deliverables.**
- `src/persistence/store.py` — Storage backend interface
- `src/persistence/in_memory.py` — In-memory backend (MVP)
- `src/persistence/lifecycle.py` — Lifecycle transition handlers
- `src/persistence/checkpoint.py` — Checkpoint and restore
- Immutability enforcement for Evidence
- Append-only enforcement for OverrideRecord
- Object identity preservation (ULIDs)
- Unit tests for each backend
- Integration tests with `core/` and `runtime/`

**Dependencies.** Phase 1 (`core/`).

**Exit Criteria.**
- In-memory backend fully functional
- All Object types persist correctly
- Evidence immutability enforced (write-once semantics)
- OverrideRecord append-only enforced
- Lifecycle transitions work (retire, supersede)
- Checkpoint/restore cycle works
- Interface stable enough for Runtime to depend on
- Test coverage ≥ 90% for `persistence/` module

**MVP scope.** In-memory backend only. Production backend (database) is post-MVP.

**Parallelization note.** This phase can run in parallel with Phase 2 (Workflow) and Phase 3 (Runtime) once the `core/` types are stable, since Persistence depends only on `core/`.

---

### Phase 5 — Research Layer

**Objective.** Implement synthesis, curator actions, and calibration.

**Deliverables.**
- `src/research/synthesis.py` — Multi-Signal → Research; multi-Research → Thesis (Path A/B/C logic)
- `src/research/curator.py` — Curator interface (8 actions: add_entity, remove_entity, change_tier, adjust_score, mark_noise, mark_redundant, bind_industry_position, update_notes)
- `src/research/calibration.py` — Calibration data emission
- `src/research/conflicts.py` — Conflict surfacing events
- Per-Thesis serialization (per Runtime Model OQ-8)
- Unit tests for each component
- Integration tests with curator workflow

**Dependencies.** Phases 1–4 (full pipeline required).

**Exit Criteria.**
- Synthesis produces Research from Signals per Workflow Model Stage 4
- Synthesis produces Thesis (Path A/B/C) from Research per Workflow Model Stage 5
- Curator can perform all 8 actions
- OverrideRecord appended (not overwritten) for each curator action
- Calibration data emitted per cycle
- Conflict surfacing events emitted
- Concurrent Thesis updates serialized correctly
- Test coverage ≥ 85% for `research/` module

---

### Phase 6 — Reports

**Objective.** Implement Report generation per the existing report template (preserved in legacy docs).

**Deliverables.**
- `src/reports/templates/` — 3 report templates (Daily Brief, Weekly Review, Per-Entity Brief)
- `src/reports/render.py` — Render engine
- `src/reports/export.py` — Export formats (markdown, JSON)
- `src/reports/schedule.py` — Scheduled report generation
- Banned-word enforcement
- Citation format enforcement
- Length caps per section
- Unit tests for each template
- Integration tests for end-to-end report generation

**Dependencies.** Phases 1–5 (need Signals, ThesisDeltas, Knowledge as input).

**Exit Criteria.**
- All 3 templates render correctly
- Banned words rejected
- Citations formatted correctly
- Length caps enforced
- Export to markdown and JSON works
- Scheduled generation works (e.g., daily at configured time)
- Test coverage ≥ 80% for `reports/` module

---

## MVP Definition

The MVP is the state where **a single end-to-end cycle produces a single Signal from a single Source, persisted, with a basic report**.

### MVP Scope

| Component | MVP Status |
|---|---|
| **Phase 1 Core Objects** | Full (all 7 types, all invariants) |
| **Phase 2 Workflow Engine** | Full (all 6 stages, all 23 gates) |
| **Phase 3 Runtime Engine** | Full (all 7 components) |
| **Phase 4 Persistence** | In-memory backend only |
| **Phase 5 Research Layer** | Synthesis only; curator actions deferred |
| **Phase 6 Reports** | Per-Entity Brief only; Daily/Weekly deferred |

### MVP Out of Scope

| Feature | Reason |
|---|---|
| Curator actions (override, etc.) | Phase 5 deferred |
| Production persistence (database) | Phase 4 in-memory only |
| Retry with backoff | Phase 3 basic; full retry post-MVP |
| Multi-source scaling | Post-MVP |
| Calibration dashboards | Post-MVP |
| Real-time streaming | Post-MVP |
| Distributed execution | Post-MVP |
| Authentication / authorization | Post-MVP |
| Multi-tenancy | Out of scope |

### MVP Acceptance Criteria

The MVP is accepted when:

1. A single cycle can be triggered manually.
2. The cycle produces a Signal from a real Source (e.g., a news feed or SEC filing).
3. The Signal is grounded by Evidence and persisted.
4. A Per-Entity Brief is generated from the Signal.
5. All 23 gates are evaluated; failure paths are correct.
6. The audit log captures the cycle.
7. Unit and integration tests pass with ≥ 85% coverage in `core/`, `workflow/`, `runtime/`.

---

## Phase Dependencies (Summary)

```
Phase 1 (Core)
   ↓
Phase 2 (Workflow)          ─┐
   ↓                         │ (parallel after Phase 1)
Phase 4 (Persistence)       ─┤
   ↓                         │
Phase 3 (Runtime) ← ─ ─ ─ ─ ─┘
   ↓
Phase 5 (Research)
   ↓
Phase 6 (Reports)
```

Phases 2, 3, 4 all depend on Phase 1. Phases 3 and 4 can proceed in parallel after Phase 1's interface is stable.

---

## Critical Path

The **critical path** to MVP is:

**Phase 1 → Phase 2 → Phase 4 (in-memory) → Phase 3 → Phase 6 (Per-Entity Brief)**

Phase 5 (Research Layer) is partially deferred for MVP (synthesis only, no curator). Full Phase 5 completes the system but is not on the MVP critical path.

---

## Risk Register

| Risk | Mitigation |
|---|---|
| Phase 1 interface churn breaking downstream phases | Freeze `core/` interface after Phase 1; changes require explicit migration |
| Workflow gate ambiguity | Cross-reference each gate to Workflow Model §"Gates" during implementation |
| Persistence interface instability | Define `Persistence` interface in Phase 3; concrete backends in Phase 4 |
| Runtime/Workflow coupling | Runtime depends on Workflow interface only; no direct stage calls |
| Curator complexity creep | Curator interface is simple (8 actions); no complex logic in MVP |
| Scope creep into implementation details | Roadmap defines MVP scope explicitly; post-MVP features listed |

---

## Post-MVP Roadmap (Preview)

Features explicitly deferred to post-MVP:

1. **Production persistence.** Database backend (PostgreSQL or similar); migration from in-memory.
2. **Distributed execution.** Multi-node runtime; queue-based work distribution.
3. **Real-time streaming.** Burst mode with streaming updates.
4. **Calibration dashboards.** Operator-facing dashboards with calibration metrics.
5. **Replay mode.** Deterministic backtest with pinned versions.
6. **Curator UI.** Human-facing interface for curator actions.
7. **Report scheduling.** Automated report generation at configured times.
8. **Multi-source scaling.** Performance optimization for 100+ Sources.
9. **Authentication and authorization.** Role-based access control (Reader, Curator, Operator, Auditor).
10. **Schema migration tooling.** For Object Model version evolution.

These are tracked but not scheduled. The MVP must be operational before any post-MVP work begins.

---

## Repository Conventions

Code-level conventions to establish before Phase 1:

1. **Language and runtime.** To be decided at Phase 1 start. Candidate: Python 3.12+ (matches existing `scripts/lint_spec.py`).
2. **Testing framework.** Standard unit/integration split.
3. **Linting.** Type checking (mypy or pyright); formatting (black or ruff).
4. **Commit message format.** Reference phase and module: `[Phase 1][core] Add Entity type`.
5. **Branch strategy.** Phase-based feature branches; main branch always builds.
6. **Documentation.** Docstrings on all public types; module-level README per `src/` subdirectory.

These conventions are set during Phase 1 setup, not before.

---

## Version History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-18 | Initial Implementation Roadmap: 6 phases, 6 modules, MVP-first scope |
