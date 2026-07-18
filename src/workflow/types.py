"""
Workflow types and enums.

Defines the common types used across the workflow module:
- StageStatus: outcome of a stage execution
- FailurePath: where an Object is routed on gate failure
- GateResult: outcome of a single gate evaluation
- StageResult: outcome of a stage execution
- CandidateObservation: pre-Evidence raw information unit
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from src.core.ids import ID


# ---------------------------------------------------------------------------
# Stage Status
# ---------------------------------------------------------------------------


class StageStatus(str, Enum):
    """Status of a stage execution (Workflow Model §"Failure Paths").

    Each gate failure maps to a status. The pipeline uses this to decide
    how to handle the failure (route to failure path, retry, etc.).
    """

    ADVANCE = "advance"  # All gates passed; advance to next stage
    FAIL_REJECT = "fail_reject"  # Object is rejected (Stages 2-5)
    FAIL_HOLD = "fail_hold"  # Object is held awaiting better conditions (Stages 4-5)
    FAIL_PENDING = "fail_pending"  # Object is pending integration (Stage 6)
    FAIL_DEGRADED = "fail_degraded"  # Source is degraded (Stage 1)
    FAIL_FLAG = "fail_flag"  # Candidate flagged for review (Stage 1)


class FailurePath(str, Enum):
    """Failure path destination for an Object.

    Per Workflow Model §"Failure Paths":
    - REJECT: Stages 2-5; Object is not promoted
    - HOLD: Stages 4-5; Object preserved, awaits better conditions
    - PENDING: Stage 6; Thesis awaiting integration
    - DEGRADED: Stage 1; Source marked unhealthy
    - FLAG: Stage 1; Candidate flagged for review
    - NONE: No failure occurred
    """

    REJECT = "reject"
    HOLD = "hold"
    PENDING = "pending"
    DEGRADED = "degraded"
    FLAG = "flag"
    NONE = "none"


# ---------------------------------------------------------------------------
# Gate and Stage Results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateResult:
    """Result of a single gate evaluation."""

    passed: bool
    reason: str | None = None

    @classmethod
    def pass_(cls) -> "GateResult":
        """Factory for a passing gate result."""
        return cls(passed=True, reason=None)

    @classmethod
    def fail(cls, reason: str) -> "GateResult":
        """Factory for a failing gate result."""
        return cls(passed=False, reason=reason)


@dataclass(frozen=True)
class StageResult:
    """Result of a stage execution."""

    status: StageStatus
    failure_path: FailurePath = FailurePath.NONE
    failure_reason: str | None = None
    retryable: bool = False
    output: dict[str, object] = field(default_factory=dict)

    @property
    def advanced(self) -> bool:
        """True if the stage succeeded and the pipeline should advance."""
        return self.status == StageStatus.ADVANCE

    @property
    def failed(self) -> bool:
        """True if the stage failed (any FAIL_* status)."""
        return self.status != StageStatus.ADVANCE


# ---------------------------------------------------------------------------
# Candidate Observation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateObservation:
    """A raw information unit extracted from a Source (Stage 1 output).

    Pre-Evidence. Not yet validated against Evidence rules. If validation
    passes in Stage 2, an Evidence is produced from this Candidate.

    Per Workflow Model §"Stage 1 — Source Observation":
    - Input: 1 Source
    - Output: 0..N Candidate observations
    """

    source_id: ID
    content: str
    source_timestamp: str  # ISO8601 UTC; when the source claims this happened
    retrieved_at: str  # ISO8601 UTC; when we retrieved it
    url: str

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("CandidateObservation.content is required")
        if not self.source_id:
            raise ValueError("CandidateObservation.source_id is required")