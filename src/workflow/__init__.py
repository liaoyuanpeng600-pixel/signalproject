"""
Workflow Engine — Phase 2.

Implements the 6-stage pipeline (S1–S6) with 23 gates per Workflow Model.

Module structure:
- types.py: StageStatus, FailurePath, GateResult, StageResult, CandidateObservation
- context.py: PipelineContext (state holder for one cycle)
- events.py: Workflow events (decoupling)
- gates.py: Gate base + 23 concrete gates
- stages.py: Stage base + 6 concrete stages
- pipeline.py: Pipeline orchestrator
- update_rules.py: Workflow Model Rules 1–4
- cardinality.py: Cardinality rules

The workflow module orchestrates; domain rules live in src/core/.
All state transitions go through src/core/lifecycle.

The former ``src.workflow.persistence`` prototype is intentionally not
re-exported. New code uses ``src.persistence.Store``.
"""

from __future__ import annotations

from src.workflow import (
    cardinality,
    context,
    events,
    gates,
    pipeline,
    stages,
    types,
    update_rules,
)

__all__ = [
    "cardinality",
    "context",
    "events",
    "gates",
    "pipeline",
    "stages",
    "types",
    "update_rules",
]
