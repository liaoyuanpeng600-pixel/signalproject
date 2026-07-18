# SIGNAL — Research Operating System

> **A Research Operating System that transforms external information into continuously evolving research understanding through evidence.**

This repository contains the specification and implementation of SIGNAL.

## Status

| Layer | Status | Document |
|---|---|---|
| Architecture Principles | Frozen v1.0 | [docs/00_ARCHITECTURE_PRINCIPLES.md](docs/00_ARCHITECTURE_PRINCIPLES.md) |
| Object Model | Frozen v1.0 | [docs/01_OBJECT_MODEL.md](docs/01_OBJECT_MODEL.md) |
| Workflow Model | Frozen v1.0 | [docs/02_WORKFLOW_MODEL.md](docs/02_WORKFLOW_MODEL.md) |
| Runtime Model | Frozen v1.0 | [docs/03_RUNTIME_MODEL.md](docs/03_RUNTIME_MODEL.md) |
| Implementation Roadmap | Draft for review | [docs/IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md) |
| **Phase 1 Core Objects** | **Complete — 185 tests, 98% coverage** | `src/core/` |
| **Phase 2 Workflow Engine** | **Complete — 346 tests, 90% coverage** | `src/workflow/` |

## Architecture (frozen)

```
Architecture Principles   (constitutional root)
        ↓
Object Model             (7 core types + refinements)
        ↓
Workflow Model           (6 stages, 23 gates)
        ↓
Runtime Model            (7 components)
        ↓
Implementation           (this code)
```

See [docs/IMPLEMENTATION_ROADMAP.md](docs/IMPLEMENTATION_ROADMAP.md) for the phased delivery plan.

## What This Codebase Implements

### Phase 1 — Core Objects (Complete)

The `src/core/` module defines the 7 Object types from the Object Model:

1. **Entity** — anything research can attach to (companies, industries, sectors, macro variables)
2. **Source** — origin of information
3. **Evidence** — retrievable information with provenance (immutable)
4. **Signal** — discrete, evidenced observation about an Entity
5. **Research** — organized investigation
6. **Thesis** — living research object (central organizing unit)
7. **Knowledge** — accumulated corpus

Plus shared primitives: `ids`, `timestamps`, `lifecycle`, `invariants`.

### Phase 2 — Workflow Engine (Complete)

The `src/workflow/` module implements the 6-stage pipeline with 23 gates per the Workflow Model:

- **`types.py`** — StageStatus, FailurePath, GateResult, StageResult, CandidateObservation
- **`events.py`** — StageStarted, GateEvaluated, StageCompleted, ObjectRouted, WorkflowCompleted, WorkflowAborted
- **`context.py`** — PipelineContext (in-flight state)
- **`gates.py`** — 22 effective gates organized by stage (S1, S2, S3, S4, S5, S6)
- **`stages.py`** — 6 stages with Protocol interfaces (SourceObserver, EvidenceProducer, SignalExtractor, ResearchSynthesizer, ThesisCrystallizer, KnowledgeIntegrator)
- **`pipeline.py`** — Pipeline orchestrator
- **`update_rules.py`** — Rules 1-4 (Signal handling, Thesis update, Conflicting Research, Knowledge Accumulation)
- **`cardinality.py`** — Cardinality verification per stage
- **`persistence.py`** — Persistence interface + InMemoryPersistence (MVP)

Per the user constraints:
- Workflow orchestrates only; business rules remain in domain objects.
- All state transitions go through the lifecycle module.
- No direct persistence logic inside the workflow layer.
- Prefer events and interfaces over tight coupling.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=src/core --cov=src/workflow --cov-report=term-missing

# Type check
mypy src/

# Lint
ruff check src/ tests/
```

## Test Status

```
346 passed in ~0.5s
- Phase 1: 185 tests (98% coverage on src/core/)
- Phase 2: 161 tests (90% coverage on src/workflow/)
```

## Project Layout

```
src/
├── core/                  # Phase 1: Core Object types (COMPLETE)
│   ├── ids.py             # ID generation (UUID-based, ULID-migration-ready)
│   ├── timestamps.py      # ISO8601 UTC timestamp utilities
│   ├── lifecycle.py       # Shared lifecycle state machines
│   ├── invariants.py      # 12 system-wide invariant checks
│   ├── entities/          # Entity type
│   ├── sources/           # Source type
│   ├── evidence/          # Evidence type (immutable)
│   ├── signals/           # Signal type with lifecycle
│   ├── research/          # Research type
│   ├── theses/            # Thesis type with evolution
│   └── knowledge/         # Knowledge accumulation interface
└── workflow/              # Phase 2: Workflow Engine (COMPLETE)
    ├── types.py           # StageStatus, FailurePath, GateResult, StageResult
    ├── events.py          # Decoupling events
    ├── context.py         # PipelineContext
    ├── gates.py           # 22 effective gates across 6 stages
    ├── stages.py          # 6 stages with Protocol interfaces
    ├── pipeline.py        # Pipeline orchestrator
    ├── update_rules.py    # Rules 1-4
    ├── cardinality.py     # Cardinality verification
    └── persistence.py     # Persistence interface

tests/
└── unit/
    ├── test_*.py          # Phase 1 tests
    └── workflow/
        └── test_*.py      # Phase 2 tests
```

## Phase Status

| Phase | Status |
|---|---|
| 1 Core Objects | **Complete** — 185 tests, 98% coverage |
| 2 Workflow Engine | **Complete** — 161 tests, 90% coverage |
| 3 Runtime Engine | Not started |
| 4 Persistence | Not started (InMemoryPersistence in Phase 2 as placeholder) |
| 5 Research Layer | Not started (partial in MVP) |
| 6 Reports | Not started (Per-Entity Brief in MVP) |

## License

Proprietary. See the Signal Project for terms.
