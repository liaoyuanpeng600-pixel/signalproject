# SIGNAL — Research Operating System

SIGNAL is a specification-led research system that turns evidence into
structured signals, research, theses, and deterministic reports.

## Status

Release version: **0.1.0 (alpha)**.

The repository currently implements Phases 1–6:

- core domain objects and lifecycle invariants;
- the six-stage workflow engine;
- in-process runtime scheduling, validation, retry, audit, and dead-letter handling;
- an abstract persistence `Store` with an in-memory backend, lifecycle helpers,
  checkpoints, and append-only overrides;
- research synthesis, theme evolution, curation, conflict detection, and calibration;
- deterministic Daily Brief, Weekly Review, and Per-Entity Brief builders,
  Markdown renderers, and companion JSON export.

The in-memory components are suitable for development and testing, not durable
production deployment. Connectors, a production database, notifications,
HTML/PDF export, UI, and Phase 7 work are not implemented.

Frozen design documents remain authoritative for architecture and semantics:

- [Architecture Principles](docs/00_ARCHITECTURE_PRINCIPLES.md)
- [Object Model](docs/01_OBJECT_MODEL.md)
- [Workflow Model](docs/02_WORKFLOW_MODEL.md)
- [Runtime Model](docs/03_RUNTIME_MODEL.md)
- [Report Specification](docs/REPORT_SPECIFICATION.md)
- [Implementation Roadmap](docs/IMPLEMENTATION_ROADMAP.md)

The specification version (`SPEC_VERSION 1.3.0`) and report JSON schema version
(`1.0`) are independent of the Python package release version.

## Requirements and installation

Python 3.10–3.13 is the declared compatibility range. The release-hardening
checkpoint was executed locally on Python 3.11; the other declared versions are
covered by the CI test matrix and are not claimed as locally verified.

```bash
python -m pip install -e ".[dev]"
```

The project has no runtime third-party dependencies. Development tooling is
declared in the `dev` extra.

## Quick start

The repository currently exposes Python APIs rather than a command-line
interface.

```python
from src.persistence import InMemoryStore
from src.reports import JsonExporter

store = InMemoryStore()
exporter = JsonExporter()
```

Persistence consumers should depend on `src.persistence.Store`; the
`src.workflow.persistence` prototype is retained only as a non-exported legacy
compatibility module and should not be used by new code.

Report builders and renderers are exported from `src.reports`. See
[the report specification](docs/REPORT_SPECIFICATION.md) for report semantics
and the unit tests under `tests/unit/reports/` for executable examples.

## Verification

```bash
# Complete suite
python -m pytest

# Focused package suites
python -m pytest tests/unit/persistence tests/unit/runtime
python -m pytest tests/unit/research tests/unit/reports

# Optional static checks (after installing the dev extra)
python -m mypy src
python -m ruff check src tests
```

The test suite contains 863 tests at this checkpoint. Treat the command result,
not this count, as the source of truth as tests are added.

## Package layout

```text
src/
  core/          Domain objects and invariants
  workflow/      Six-stage workflow engine
  persistence/   Store contract and in-memory implementation
  runtime/       Runtime orchestration and resilience
  research/      Synthesis, curation, themes, and calibration
  reports/       Deterministic builders, renderers, and JSON export
tests/unit/       Unit and integration-style component tests
docs/             Frozen design documents and implementation roadmap
```

## License

Proprietary.
