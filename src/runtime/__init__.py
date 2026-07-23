"""
Runtime Engine — Phase 3.

Implements the runtime layer that wraps the Workflow Engine's Pipeline.

Components (per Runtime Model §"Runtime Components"):
- AuditLogger: append-only event log (Checkpoint 1)
- PipelineExecutor: runs a Pipeline with audit instrumentation (Checkpoint 1)
- WorkQueue: priority queue of WorkItems with state transitions (Checkpoint 2)
- Scheduler: produces WorkItems; ManualTrigger, ScheduledTrigger, BurstTrigger
  (Checkpoint 2)
- CycleDispatcher: consumes WorkItems and runs them through the Executor
  (Checkpoint 2)
- Validator: gate evaluation orchestrator (Checkpoint 3)
- RuntimeCycle: top-level cycle orchestrator — loads inputs from Store,
  constructs PipelineContext, runs Pipeline+Validator, persists outputs
  through lifecycle helpers (Checkpoint 3)
- RetryPolicy / RetryDecision: configurable retry contract (Checkpoint 4)
- DeadLetterQueue: MVP abstraction for failed WorkItems (Checkpoint 4)
- RetryManager: evaluates RetryPolicy against Validator outputs (Checkpoint 4)
- RetryOrchestrator: executes RetryDecisions against queue + DLQ
  (Checkpoint 4)

Dependency rules:
- Runtime components depend ONLY on `persistence.store.Store` (interface).
- Runtime MUST NOT import `persistence.in_memory.InMemoryStore`.
- All entity lifecycle changes go through `persistence.lifecycle` helpers.
"""

from __future__ import annotations

from src.runtime import (
    audit,
    cycle,
    dead_letter,
    executor,
    queue,
    retry,
    retry_manager,
    retry_orchestrator,
    scheduler,
    validator,
)
from src.runtime.audit import AuditLogger, AuditRecord
from src.runtime.cycle import CycleReport, RuntimeCycle
from src.runtime.dead_letter import DeadLetterEntry, DeadLetterQueue
from src.runtime.executor import ManualTrigger, PipelineExecutor, Trigger, TriggerResult
from src.runtime.queue import (
    InvalidQueueTransition,
    QueueEmptyError,
    QueueFullError,
    QueueStats,
    WorkItem,
    WorkItemPriority,
    WorkItemStatus,
    WorkQueue,
)
from src.runtime.retry import RetryDecision, RetryPolicy, RetryPolicyKind
from src.runtime.retry_manager import RetryContext, RetryManager
from src.runtime.retry_orchestrator import RetryOrchestrator, RetryOutcome
from src.runtime.scheduler import (
    BurstEvent,
    CycleDispatcher,
    DefaultScheduler,
    ScheduleConfig,
    Scheduler,
)
from src.runtime.validator import StageValidation, ValidationReport, Validator

__all__ = [
    "AuditLogger",
    "AuditRecord",
    "BurstEvent",
    "CycleDispatcher",
    "CycleReport",
    "DeadLetterEntry",
    "DeadLetterQueue",
    "DefaultScheduler",
    "InvalidQueueTransition",
    "ManualTrigger",
    "PipelineExecutor",
    "QueueEmptyError",
    "QueueFullError",
    "QueueStats",
    "RetryContext",
    "RetryDecision",
    "RetryManager",
    "RetryOrchestrator",
    "RetryOutcome",
    "RetryPolicy",
    "RetryPolicyKind",
    "RuntimeCycle",
    "ScheduleConfig",
    "Scheduler",
    "StageValidation",
    "Trigger",
    "TriggerResult",
    "ValidationReport",
    "Validator",
    "WorkItem",
    "WorkItemPriority",
    "WorkItemStatus",
    "WorkQueue",
    "audit",
    "cycle",
    "dead_letter",
    "executor",
    "queue",
    "retry",
    "retry_manager",
    "retry_orchestrator",
    "scheduler",
    "validator",
]