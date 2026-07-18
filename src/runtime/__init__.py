"""
Runtime Engine — Phase 3.

Implements the runtime layer that wraps the Workflow Engine's Pipeline.

Components (per Runtime Model §"Runtime Components"):
- AuditLogger: append-only event log
- PipelineExecutor: runs a Pipeline with audit instrumentation

Per Runtime Model §"Runtime Boundary":
- Runtime executes the workflow; it does not redefine it.
- All state transitions go through the workflow's domain objects (which
  go through the lifecycle module).
- No direct persistence logic — the workflow uses the Persistence interface.
- Events are emitted for decoupling; consumers (audit, future runtime
  components) subscribe to events.

This checkpoint covers AuditLogger and PipelineExecutor. The remaining
5 components (Scheduler, Queue, Validator, Retry Manager) will be added
in subsequent checkpoints.
"""

from __future__ import annotations

from src.runtime import audit, executor
from src.runtime.audit import AuditLogger, AuditRecord
from src.runtime.executor import PipelineExecutor, Trigger

__all__ = [
    "AuditLogger",
    "AuditRecord",
    "PipelineExecutor",
    "Trigger",
    "audit",
    "executor",
]
