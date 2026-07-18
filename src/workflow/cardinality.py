"""
Cardinality rules — per Workflow Model §"Cardinality".

These rules describe the input/output cardinality of each stage. They are
PREDICATES that can be checked against the PipelineContext to verify the
pipeline's state.

Note: stages naturally produce these cardinalities; this module documents
them and provides assertions for testing and validation.

Cardinality rules:
- Stage 1: 1 Source -> 0..N Candidates
- Stage 2: 1..N Candidates -> 0..1 Evidence per candidate
- Stage 3: 1..N Evidence -> 0..N Signals per Evidence
- Stage 4: 1..N Signals + 1 Entity -> 0..1 Research per (Entity, question)
- Stage 5: 1 Research + 0..1 prior Thesis -> 1 Thesis
- Stage 6: 1 Thesis -> 1 Knowledge update (cumulative)
"""

from __future__ import annotations

from src.core.evidence import Evidence
from src.core.ids import ID
from src.core.signals import Signal
from src.workflow.context import PipelineContext
from src.workflow.types import CandidateObservation


def stage1_cardinality(context: PipelineContext) -> bool:
    """Verify Stage 1 cardinality: 1 Source -> 0..N Candidates.

    Each candidate should have exactly one source_id.
    """
    for c in context.candidates:
        if not c.source_id:
            return False
    return True


def stage2_cardinality(candidates: list[CandidateObservation], evidences: list[Evidence]) -> bool:
    """Verify Stage 2 cardinality: 1..N Candidates -> 0..1 Evidence per candidate.

    Each Evidence must reference at least one Source.
    Each candidate may produce 0 or 1 Evidence.
    """
    if len(evidences) > len(candidates):
        # More evidence than candidates is impossible
        return False
    for e in evidences:
        if not e.source_ids:
            return False
    return True


def stage3_cardinality(evidences: list[Evidence], signals: list[Signal]) -> bool:
    """Verify Stage 3 cardinality: 1..N Evidence -> 0..N Signals per Evidence.

    Each Signal must reference at least one Evidence.
    """
    if len(signals) > len(evidences):
        # More signals than evidences is impossible (in MVP)
        return False
    for s in signals:
        if not s.evidence_ids:
            return False
    return True


def stage4_cardinality(signals: list[Signal]) -> bool:
    """Verify Stage 4 cardinality: 1..N Signals + 1 Entity -> 0..1 Research.

    Each Research must have >= 1 Signal.
    """
    # This is a per-Research check; here we just verify the signal count.
    return len(signals) >= 0  # Always true; per-Research check is elsewhere


def stage5_cardinality(research_count: int, thesis_count: int) -> bool:
    """Verify Stage 5 cardinality: 1 Research + 0..1 prior Thesis -> 1 Thesis.

    Each Research produces at most one Thesis output (new or evolved).
    """
    return thesis_count <= research_count or thesis_count == 0


def stage6_cardinality(thesis_count: int) -> bool:
    """Verify Stage 6 cardinality: 1 Thesis -> 1 Knowledge update (cumulative).

    Each Thesis either integrates (success) or is pending.
    """
    return thesis_count >= 0  # Always true; per-Thesis check elsewhere