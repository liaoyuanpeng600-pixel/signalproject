"""
SIGNAL Research Layer — Phase 5.

This package implements the synthesis, theme evolution, knowledge
accumulation, curator actions, and conflict surfacing that consume Runtime
outputs.

Phase 5 Checkpoint 1 scope:
- synthesis: Multi-Signal → Research aggregation
- themes: Thesis Path A/B/C evolution (per Workflow Model)
- promotion: Signal VERIFIED→ACTIVE→DECAYED state transitions
- knowledge: Top-level orchestration consuming Runtime outputs

Phase 5 Checkpoint 2 scope (this checkpoint):
- curator: 8 canonical curator actions (override_score, mark_noise,
  mark_redundant, change_tier, add_entity, remove_entity,
  bind_industry_position, update_notes)
- conflicts: ConflictEvent surfacing (DUPLICATE_OVERRIDE,
  CONFLICTING_OVERRIDE, STALE_OVERRIDE)

Phase 5 Checkpoint 3 scope (this checkpoint):
- calibration: Calibration data emission (score deltas, action
  distribution, conflict distribution, theme-path distribution).

Deferred to subsequent phases:
- Reports (Phase 6).

Dependency rules:
- Research depends on Runtime OUTPUTS only (CycleReport, ValidationReport).
- Research MUST NOT depend on Runtime internals (executor, scheduler, retry).
- Research depends ONLY on `persistence.store.Store` (abstract).
- All lifecycle transitions go through `persistence.lifecycle` helpers.
"""

from __future__ import annotations

from src.research.calibration import (
    CalibrationData,
    CalibrationEmitter,
    ScoreDelta,
)
from src.research.conflicts import ConflictDetector, ConflictEvent, ConflictKind
from src.research.curator import (
    Curator,
    CuratorError,
    InvalidPayloadError,
    TargetNotFoundError,
)
from src.research.knowledge import KnowledgeUpdateReport, KnowledgeUpdater
from src.research.promotion import (
    PromotionDecision,
    PromotionPolicy,
    SignalPromoter,
)
from src.research.synthesis import ResearchSynthesizer, SynthesisReport
from src.research.themes import ThemeEvolver, ThemeEvolutionReport, ThemePath

__all__ = [
    "CalibrationData",
    "CalibrationEmitter",
    "ConflictDetector",
    "ConflictEvent",
    "ConflictKind",
    "Curator",
    "CuratorError",
    "InvalidPayloadError",
    "KnowledgeUpdateReport",
    "KnowledgeUpdater",
    "PromotionDecision",
    "PromotionPolicy",
    "ScoreDelta",
    "SignalPromoter",
    "SynthesisReport",
    "ResearchSynthesizer",
    "TargetNotFoundError",
    "ThemeEvolutionReport",
    "ThemeEvolver",
    "ThemePath",
]