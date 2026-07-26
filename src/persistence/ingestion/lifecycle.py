"""Persistence-neutral durable WorkItem lifecycle contracts.

This module defines immutable values and policy evaluation only. It contains no
storage adapter, worker, scheduler, clock access, or token generation.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Protocol, TypeAlias

from src.core.ids import ID
from src.ingestion.work import (
    CollectionWorkItem,
    DocumentProcessingWorkItem,
    ResearchWorkItem,
)
from src.persistence.ingestion.models import IngestionWorkItem

_WORKER_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_POLICY_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{43,}$")
_MAX_ERROR_MESSAGE_CODEPOINTS = 1_024
_RETRYABLE_CATEGORIES: frozenset[WorkErrorCategory]


class WorkItemStatus(str, Enum):
    """The complete durable lifecycle state set."""

    PENDING = "pending"
    RUNNING = "running"
    RETRYING = "retrying"
    COMPLETED = "completed"
    DEAD_LETTER = "dead_letter"


class WorkItemKind(str, Enum):
    """The complete Phase 7 durable WorkItem kind set."""

    COLLECTION = "collection"
    DOCUMENT_PROCESSING = "document_processing"
    RESEARCH = "research"


class WorkErrorCategory(str, Enum):
    """Stable persistence-neutral execution failure categories."""

    CONNECTOR_TRANSIENT = "connector_transient"
    RATE_LIMITED = "rate_limited"
    PERSISTENCE_OPERATIONAL = "persistence_operational"
    CHECKPOINT_CONFLICT = "checkpoint_conflict"
    DOWNSTREAM_TRANSIENT = "downstream_transient"
    UNEXPECTED = "unexpected"
    UNSUPPORTED_KIND = "unsupported_kind"
    PAYLOAD_INCOMPATIBLE = "payload_incompatible"
    PAYLOAD_INVALID = "payload_invalid"
    DEPENDENCY_MISSING = "dependency_missing"
    BINDING_MISMATCH = "binding_mismatch"
    AUTHORITATIVE_CONFLICT = "authoritative_conflict"
    HANDLER_CONTRACT_VIOLATION = "handler_contract_violation"
    DOMAIN_INVARIANT = "domain_invariant"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"


_RETRYABLE_CATEGORIES = frozenset(
    {
        WorkErrorCategory.CONNECTOR_TRANSIENT,
        WorkErrorCategory.RATE_LIMITED,
        WorkErrorCategory.PERSISTENCE_OPERATIONAL,
        WorkErrorCategory.CHECKPOINT_CONFLICT,
        WorkErrorCategory.DOWNSTREAM_TRANSIENT,
        WorkErrorCategory.UNEXPECTED,
    }
)


class UtcClock(Protocol):
    """Supply explicit canonical UTC timestamps to runtime callers."""

    def now(self) -> str:
        """Return one timezone-aware UTC ISO-8601 value."""
        ...


class ClaimTokenSource(Protocol):
    """Supply opaque claim tokens to a concrete lifecycle adapter."""

    def new_token(self) -> str:
        """Return a fresh unpredictable production token."""
        ...


@dataclass(frozen=True, slots=True)
class WorkError:
    """Bounded, sanitized failure metadata safe for durable persistence."""

    category: WorkErrorCategory
    message: str
    retryable: bool

    def __post_init__(self) -> None:
        if not isinstance(self.category, WorkErrorCategory):
            raise TypeError("category must be a WorkErrorCategory")
        if not isinstance(self.message, str):
            raise TypeError("message must be a string")
        if not isinstance(self.retryable, bool):
            raise TypeError("retryable must be a boolean")
        if not self.message:
            raise ValueError("message is required")
        if len(self.message) > _MAX_ERROR_MESSAGE_CODEPOINTS:
            raise ValueError("message must not exceed 1024 Unicode code points")
        if self.message != sanitize_work_error_message(self.message):
            raise ValueError("message must already be sanitized")
        expected = self.category in _RETRYABLE_CATEGORIES
        if self.retryable is not expected:
            raise ValueError("retryable must agree with the error category")


@dataclass(frozen=True, slots=True)
class WorkKindPolicy:
    """Validated lifecycle policy for one frozen WorkItem kind."""

    kind: WorkItemKind
    maximum_attempts: int
    lease_duration_seconds: int
    renewal_interval_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, WorkItemKind):
            raise TypeError("kind must be a WorkItemKind")
        _require_positive_integer(self.maximum_attempts, "maximum_attempts")
        _require_positive_integer(
            self.lease_duration_seconds,
            "lease_duration_seconds",
        )
        _require_positive_integer(
            self.renewal_interval_seconds,
            "renewal_interval_seconds",
        )
        if self.renewal_interval_seconds >= self.lease_duration_seconds:
            raise ValueError(
                "renewal_interval_seconds must be less than lease_duration_seconds"
            )


@dataclass(frozen=True, slots=True)
class WorkLifecyclePolicy:
    """Immutable, versioned retry and lease configuration."""

    policy_version: str
    kinds: tuple[WorkKindPolicy, ...]
    initial_retry_delay_seconds: int
    maximum_retry_delay_seconds: int
    backoff_multiplier_basis_points: int
    jitter_ratio_basis_points: int

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str):
            raise TypeError("policy_version must be a string")
        if _POLICY_VERSION_PATTERN.fullmatch(self.policy_version) is None:
            raise ValueError("policy_version has an invalid format")
        if not isinstance(self.kinds, tuple):
            raise TypeError("kinds must be a tuple")
        if any(not isinstance(item, WorkKindPolicy) for item in self.kinds):
            raise TypeError("kinds must contain WorkKindPolicy values")
        configured = tuple(item.kind for item in self.kinds)
        if len(configured) != len(set(configured)):
            raise ValueError("kinds must not contain duplicates")
        if set(configured) != set(WorkItemKind):
            raise ValueError("kinds must configure every WorkItemKind exactly once")
        _require_positive_integer(
            self.initial_retry_delay_seconds,
            "initial_retry_delay_seconds",
        )
        _require_positive_integer(
            self.maximum_retry_delay_seconds,
            "maximum_retry_delay_seconds",
        )
        if self.maximum_retry_delay_seconds < self.initial_retry_delay_seconds:
            raise ValueError(
                "maximum_retry_delay_seconds must be at least the initial delay"
            )
        _require_integer(
            self.backoff_multiplier_basis_points,
            "backoff_multiplier_basis_points",
        )
        if self.backoff_multiplier_basis_points < 10_000:
            raise ValueError(
                "backoff_multiplier_basis_points must be at least 10000"
            )
        _require_integer(
            self.jitter_ratio_basis_points,
            "jitter_ratio_basis_points",
        )
        if not 0 <= self.jitter_ratio_basis_points < 10_000:
            raise ValueError(
                "jitter_ratio_basis_points must be between 0 and 9999"
            )

    def for_kind(self, kind: WorkItemKind) -> WorkKindPolicy:
        """Return the unique configured policy for ``kind``."""
        if not isinstance(kind, WorkItemKind):
            raise TypeError("kind must be a WorkItemKind")
        return next(item for item in self.kinds if item.kind is kind)


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Runtime-policy result supplied to retryable persistence transitions."""

    policy_version: str
    maximum_attempts: int
    attempt_count: int
    exhausted: bool
    available_at: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.policy_version, str):
            raise TypeError("policy_version must be a string")
        if _POLICY_VERSION_PATTERN.fullmatch(self.policy_version) is None:
            raise ValueError("policy_version has an invalid format")
        _require_positive_integer(self.maximum_attempts, "maximum_attempts")
        _require_positive_integer(self.attempt_count, "attempt_count")
        if not isinstance(self.exhausted, bool):
            raise TypeError("exhausted must be a boolean")
        expected_exhaustion = self.attempt_count >= self.maximum_attempts
        if self.exhausted is not expected_exhaustion:
            raise ValueError("exhausted must match the attempt budget")
        if self.exhausted:
            if self.available_at is not None:
                raise ValueError("exhausted retry decision cannot be available")
        else:
            if self.available_at is None:
                raise ValueError("non-exhausted retry decision requires available_at")
            _parse_utc(self.available_at, "available_at")


@dataclass(frozen=True, slots=True)
class WorkClaimRequest:
    """Request at most one due or expired WorkItem claim."""

    worker_id: str
    allowed_kinds: tuple[WorkItemKind, ...]
    claimed_at: str
    policy: WorkLifecyclePolicy

    def __post_init__(self) -> None:
        _validate_worker_id(self.worker_id)
        if not isinstance(self.allowed_kinds, tuple):
            raise TypeError("allowed_kinds must be a tuple")
        if not self.allowed_kinds:
            raise ValueError("allowed_kinds must not be empty")
        if any(not isinstance(kind, WorkItemKind) for kind in self.allowed_kinds):
            raise TypeError("allowed_kinds must contain WorkItemKind values")
        if len(self.allowed_kinds) != len(set(self.allowed_kinds)):
            raise ValueError("allowed_kinds must not contain duplicates")
        _parse_utc(self.claimed_at, "claimed_at")
        if not isinstance(self.policy, WorkLifecyclePolicy):
            raise TypeError("policy must be a WorkLifecyclePolicy")


@dataclass(frozen=True, slots=True)
class WorkClaim:
    """Canonical post-transition authority for one running WorkItem."""

    work_item: IngestionWorkItem
    kind: WorkItemKind
    worker_id: str
    claim_token: str
    claimed_at: str
    lease_expires_at: str
    attempt_count: int
    revision: int
    reclaimed: bool
    prior_worker_id: str | None

    def __post_init__(self) -> None:
        expected_kind = work_item_kind(self.work_item)
        if not isinstance(self.kind, WorkItemKind):
            raise TypeError("kind must be a WorkItemKind")
        if self.kind is not expected_kind:
            raise ValueError("kind does not match the typed WorkItem")
        _validate_worker_id(self.worker_id)
        _validate_claim_token(self.claim_token)
        claimed = _parse_utc(self.claimed_at, "claimed_at")
        expires = _parse_utc(self.lease_expires_at, "lease_expires_at")
        if expires <= claimed:
            raise ValueError("lease_expires_at must be later than claimed_at")
        _require_positive_integer(self.attempt_count, "attempt_count")
        _require_positive_integer(self.revision, "revision")
        if not isinstance(self.reclaimed, bool):
            raise TypeError("reclaimed must be a boolean")
        if self.reclaimed:
            if self.prior_worker_id is None:
                raise ValueError("reclaimed claim requires prior_worker_id")
            _validate_worker_id(self.prior_worker_id)
        elif self.prior_worker_id is not None:
            raise ValueError("ordinary claim cannot have prior_worker_id")


@dataclass(frozen=True, slots=True)
class ClaimAuthority:
    """Complete owner/token/revision authority for one claimed WorkItem."""

    work_item_id: ID
    worker_id: str
    claim_token: str
    expected_revision: int

    def __post_init__(self) -> None:
        _validate_id(self.work_item_id, "work_item_id")
        _validate_worker_id(self.worker_id)
        _validate_claim_token(self.claim_token)
        _require_non_negative_integer(
            self.expected_revision,
            "expected_revision",
        )


@dataclass(frozen=True, slots=True)
class RenewLeaseCommand:
    """Owner-conditional request to extend one unexpired lease."""

    authority: ClaimAuthority
    renewed_at: str
    lease_duration_seconds: int

    def __post_init__(self) -> None:
        _require_type(self.authority, ClaimAuthority, "authority")
        _parse_utc(self.renewed_at, "renewed_at")
        _require_positive_integer(
            self.lease_duration_seconds,
            "lease_duration_seconds",
        )


@dataclass(frozen=True, slots=True)
class CompleteWorkCommand:
    """Owner-conditional request to complete one running WorkItem."""

    authority: ClaimAuthority
    completed_at: str

    def __post_init__(self) -> None:
        _require_type(self.authority, ClaimAuthority, "authority")
        _parse_utc(self.completed_at, "completed_at")


@dataclass(frozen=True, slots=True)
class RetryWorkCommand:
    """Owner-conditional retry or exhaustion transition request."""

    authority: ClaimAuthority
    failed_at: str
    decision: RetryDecision
    error: WorkError

    def __post_init__(self) -> None:
        _require_type(self.authority, ClaimAuthority, "authority")
        failed = _parse_utc(self.failed_at, "failed_at")
        _require_type(self.decision, RetryDecision, "decision")
        _require_type(self.error, WorkError, "error")
        if not self.error.retryable:
            raise ValueError("retry command requires a retryable WorkError")
        if (
            self.decision.available_at is not None
            and _parse_utc(self.decision.available_at, "available_at") <= failed
        ):
            raise ValueError("available_at must be later than failed_at")
        if self.authority.claim_token in self.error.message:
            raise ValueError("failure message must not contain the claim token")


@dataclass(frozen=True, slots=True)
class FailTerminalWorkCommand:
    """Owner-conditional intrinsically terminal transition request."""

    authority: ClaimAuthority
    failed_at: str
    error: WorkError

    def __post_init__(self) -> None:
        _require_type(self.authority, ClaimAuthority, "authority")
        _parse_utc(self.failed_at, "failed_at")
        _require_type(self.error, WorkError, "error")
        if self.error.retryable:
            raise ValueError("terminal command requires a terminal WorkError")
        if self.authority.claim_token in self.error.message:
            raise ValueError("failure message must not contain the claim token")


@dataclass(frozen=True, slots=True)
class WorkTransitionResult:
    """Canonical committed result of one lifecycle mutation."""

    work_item_id: ID
    kind: WorkItemKind
    from_status: WorkItemStatus
    to_status: WorkItemStatus
    occurred_at: str
    attempt_count: int
    revision: int
    available_at: str | None
    lease_expires_at: str | None
    error: WorkError | None
    exhausted: bool

    def __post_init__(self) -> None:
        _validate_id(self.work_item_id, "work_item_id")
        _require_type(self.kind, WorkItemKind, "kind")
        _require_type(self.from_status, WorkItemStatus, "from_status")
        _require_type(self.to_status, WorkItemStatus, "to_status")
        _parse_utc(self.occurred_at, "occurred_at")
        _require_positive_integer(self.attempt_count, "attempt_count")
        _require_positive_integer(self.revision, "revision")
        if self.revision < 2:
            raise ValueError("transition result revision must be at least 2")
        if self.available_at is not None:
            _parse_utc(self.available_at, "available_at")
        if self.lease_expires_at is not None:
            _parse_utc(self.lease_expires_at, "lease_expires_at")
        if self.error is not None and not isinstance(self.error, WorkError):
            raise TypeError("error must be a WorkError or None")
        if not isinstance(self.exhausted, bool):
            raise TypeError("exhausted must be a boolean")
        _validate_transition_result(self)


WorkClaimOutcome: TypeAlias = WorkClaim | WorkTransitionResult


@dataclass(frozen=True, slots=True)
class WorkItemLifecycleRecord:
    """Canonical adapter-neutral view used to verify durable state invariants."""

    work_item: IngestionWorkItem
    kind: WorkItemKind
    status: WorkItemStatus
    priority: int
    available_at: str | None
    attempt_count: int
    revision: int
    lease_owner: str | None
    claim_token: str | None
    lease_expires_at: str | None
    claimed_at: str | None
    completed_at: str | None
    dead_lettered_at: str | None
    failure: WorkError | None
    updated_at: str

    def __post_init__(self) -> None:
        _require_type(self.kind, WorkItemKind, "kind")
        if work_item_kind(self.work_item) is not self.kind:
            raise ValueError("kind does not match the typed WorkItem")
        _require_type(self.status, WorkItemStatus, "status")
        _require_integer(self.priority, "priority")
        _require_non_negative_integer(self.attempt_count, "attempt_count")
        _require_non_negative_integer(self.revision, "revision")
        _validate_optional_timestamp(self.available_at, "available_at")
        _validate_optional_timestamp(self.lease_expires_at, "lease_expires_at")
        _validate_optional_timestamp(self.claimed_at, "claimed_at")
        _validate_optional_timestamp(self.completed_at, "completed_at")
        _validate_optional_timestamp(self.dead_lettered_at, "dead_lettered_at")
        _parse_utc(self.updated_at, "updated_at")
        if self.lease_owner is not None:
            _validate_worker_id(self.lease_owner)
        if self.claim_token is not None:
            _validate_claim_token(self.claim_token)
        if self.failure is not None and not isinstance(self.failure, WorkError):
            raise TypeError("failure must be a WorkError or None")
        _validate_record_state(self)


def sanitize_work_error_message(message: str) -> str:
    """Normalize caller-reviewed error text to the ADR-010 durable form."""
    if not isinstance(message, str):
        raise TypeError("message must be a string")
    normalized = "".join(
        " " if character in "\r\n\t" else character
        for character in message
        if character in "\r\n\t" or 32 <= ord(character) < 127 or ord(character) > 159
    )
    normalized = " ".join(normalized.split())
    if not normalized:
        return ""
    return normalized[:_MAX_ERROR_MESSAGE_CODEPOINTS]


def evaluate_retry(
    *,
    policy: WorkLifecyclePolicy,
    kind: WorkItemKind,
    work_item_id: ID,
    attempt_count: int,
    failed_at: str,
    retry_after_seconds: object = None,
) -> RetryDecision:
    """Evaluate exhaustion and deterministic retry timing outside persistence."""
    _require_type(policy, WorkLifecyclePolicy, "policy")
    _require_type(kind, WorkItemKind, "kind")
    _validate_id(work_item_id, "work_item_id")
    _require_positive_integer(attempt_count, "attempt_count")
    failed = _parse_utc(failed_at, "failed_at")
    kind_policy = policy.for_kind(kind)
    exhausted = attempt_count >= kind_policy.maximum_attempts
    if exhausted:
        return RetryDecision(
            policy_version=policy.policy_version,
            maximum_attempts=kind_policy.maximum_attempts,
            attempt_count=attempt_count,
            exhausted=True,
            available_at=None,
        )

    exponent = attempt_count - 1
    numerator = (
        policy.initial_retry_delay_seconds
        * pow(policy.backoff_multiplier_basis_points, exponent)
    )
    denominator = pow(10_000, exponent)
    base = min(policy.maximum_retry_delay_seconds, numerator // denominator)
    digest = hashlib.sha256(
        f"{policy.policy_version}:{work_item_id}:{attempt_count}".encode()
    ).digest()
    value = int.from_bytes(digest[:8], byteorder="big", signed=False)
    jitter = policy.jitter_ratio_basis_points
    jitter_offset = ((2 * jitter * value) // (2**64 - 1)) - jitter
    calculated = max(
        1,
        min(
            policy.maximum_retry_delay_seconds,
            (base * (10_000 + jitter_offset)) // 10_000,
        ),
    )
    hint = _validated_retry_hint(retry_after_seconds)
    delay = calculated
    if hint is not None:
        delay = min(
            policy.maximum_retry_delay_seconds,
            max(calculated, math.ceil(hint)),
        )
    available = failed + timedelta(seconds=delay)
    return RetryDecision(
        policy_version=policy.policy_version,
        maximum_attempts=kind_policy.maximum_attempts,
        attempt_count=attempt_count,
        exhausted=False,
        available_at=available.astimezone(timezone.utc).isoformat(),
    )


def work_item_kind(work_item: IngestionWorkItem) -> WorkItemKind:
    """Map the frozen typed WorkItem union exhaustively to lifecycle kind."""
    if isinstance(work_item, CollectionWorkItem):
        return WorkItemKind.COLLECTION
    if isinstance(work_item, DocumentProcessingWorkItem):
        return WorkItemKind.DOCUMENT_PROCESSING
    if isinstance(work_item, ResearchWorkItem):
        return WorkItemKind.RESEARCH
    raise TypeError("work_item must be a Phase 7.1 typed WorkItem")


def _validate_transition_result(result: WorkTransitionResult) -> None:
    transition = (result.from_status, result.to_status)
    if transition == (WorkItemStatus.RUNNING, WorkItemStatus.RUNNING):
        if (
            result.lease_expires_at is None
            or result.available_at is not None
            or result.error is not None
            or result.exhausted
        ):
            raise ValueError("renewal result fields are inconsistent")
        if _parse_utc(result.lease_expires_at, "lease_expires_at") <= _parse_utc(
            result.occurred_at,
            "occurred_at",
        ):
            raise ValueError("renewal expiry must be later than occurred_at")
        return
    if transition == (WorkItemStatus.RUNNING, WorkItemStatus.COMPLETED):
        if (
            result.lease_expires_at is not None
            or result.available_at is not None
            or result.error is not None
            or result.exhausted
        ):
            raise ValueError("completion result fields are inconsistent")
        return
    if transition == (WorkItemStatus.RUNNING, WorkItemStatus.RETRYING):
        if (
            result.available_at is None
            or result.lease_expires_at is not None
            or result.error is None
            or not result.error.retryable
            or result.exhausted
        ):
            raise ValueError("retry result fields are inconsistent")
        if _parse_utc(result.available_at, "available_at") <= _parse_utc(
            result.occurred_at,
            "occurred_at",
        ):
            raise ValueError("retry availability must be later than occurred_at")
        return
    if transition == (WorkItemStatus.RUNNING, WorkItemStatus.DEAD_LETTER):
        if (
            result.available_at is not None
            or result.lease_expires_at is not None
            or result.error is None
        ):
            raise ValueError("dead-letter result fields are inconsistent")
        if result.exhausted:
            if (
                not result.error.retryable
                and result.error.category is not WorkErrorCategory.ATTEMPTS_EXHAUSTED
            ):
                raise ValueError("exhausted result has an invalid error category")
        elif result.error.retryable:
            raise ValueError("terminal result requires a terminal error")
        return
    raise ValueError("transition result uses an unsupported lifecycle transition")


def _validate_record_state(record: WorkItemLifecycleRecord) -> None:
    lease_values = (
        record.lease_owner,
        record.claim_token,
        record.lease_expires_at,
    )
    lease_present = tuple(value is not None for value in lease_values)
    if any(lease_present) and not all(lease_present):
        raise ValueError("lease authority fields must be all present or all absent")

    if record.status is WorkItemStatus.PENDING:
        _require_record(
            record,
            available=True,
            attempts=0,
            revision=0,
            lease=False,
            claimed=False,
            completed=False,
            dead_lettered=False,
            failure=False,
        )
    elif record.status is WorkItemStatus.RUNNING:
        _require_record(
            record,
            available=False,
            minimum_attempts=1,
            minimum_revision=1,
            lease=True,
            claimed=True,
            completed=False,
            dead_lettered=False,
            failure=False,
        )
        if record.lease_expires_at is not None and _parse_utc(
            record.lease_expires_at,
            "lease_expires_at",
        ) <= _parse_utc(record.updated_at, "updated_at"):
            raise ValueError("running lease must expire after updated_at")
        if record.claimed_at is not None and _parse_utc(
            record.claimed_at,
            "claimed_at",
        ) > _parse_utc(record.updated_at, "updated_at"):
            raise ValueError("running claimed_at cannot follow updated_at")
    elif record.status is WorkItemStatus.RETRYING:
        _require_record(
            record,
            available=True,
            minimum_attempts=1,
            minimum_revision=2,
            lease=False,
            claimed=True,
            completed=False,
            dead_lettered=False,
            failure=True,
        )
        if record.failure is not None and not record.failure.retryable:
            raise ValueError("retrying record requires retryable failure metadata")
        if record.available_at is not None and _parse_utc(
            record.available_at,
            "available_at",
        ) <= _parse_utc(record.updated_at, "updated_at"):
            raise ValueError("retrying availability must be later than updated_at")
    elif record.status is WorkItemStatus.COMPLETED:
        _require_record(
            record,
            available=False,
            minimum_attempts=1,
            minimum_revision=2,
            lease=False,
            claimed=True,
            completed=True,
            dead_lettered=False,
            failure=False,
        )
        if record.completed_at != record.updated_at:
            raise ValueError("completed_at must equal updated_at")
    else:
        _require_record(
            record,
            available=False,
            minimum_attempts=1,
            minimum_revision=2,
            lease=False,
            claimed=True,
            completed=False,
            dead_lettered=True,
            failure=True,
        )
        if record.dead_lettered_at != record.updated_at:
            raise ValueError("dead_lettered_at must equal updated_at")


def _require_record(
    record: WorkItemLifecycleRecord,
    *,
    available: bool,
    lease: bool,
    claimed: bool,
    completed: bool,
    dead_lettered: bool,
    failure: bool,
    attempts: int | None = None,
    revision: int | None = None,
    minimum_attempts: int | None = None,
    minimum_revision: int | None = None,
) -> None:
    actual = {
        "available_at": record.available_at is not None,
        "lease": record.lease_owner is not None,
        "claimed_at": record.claimed_at is not None,
        "completed_at": record.completed_at is not None,
        "dead_lettered_at": record.dead_lettered_at is not None,
        "failure": record.failure is not None,
    }
    expected = {
        "available_at": available,
        "lease": lease,
        "claimed_at": claimed,
        "completed_at": completed,
        "dead_lettered_at": dead_lettered,
        "failure": failure,
    }
    if actual != expected:
        raise ValueError(f"{record.status.value} record fields are inconsistent")
    if attempts is not None and record.attempt_count != attempts:
        raise ValueError(f"{record.status.value} attempt_count is inconsistent")
    if revision is not None and record.revision != revision:
        raise ValueError(f"{record.status.value} revision is inconsistent")
    if (
        minimum_attempts is not None
        and record.attempt_count < minimum_attempts
    ):
        raise ValueError(f"{record.status.value} attempt_count is inconsistent")
    if minimum_revision is not None and record.revision < minimum_revision:
        raise ValueError(f"{record.status.value} revision is inconsistent")


def _parse_utc(value: str, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value:
        raise ValueError(f"{field_name} is required")
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    if parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must use UTC")
    return parsed.astimezone(timezone.utc)


def _validate_optional_timestamp(value: str | None, field_name: str) -> None:
    if value is not None:
        _parse_utc(value, field_name)


def _validate_worker_id(worker_id: str) -> None:
    if not isinstance(worker_id, str):
        raise TypeError("worker_id must be a string")
    if _WORKER_ID_PATTERN.fullmatch(worker_id) is None:
        raise ValueError("worker_id has an invalid format")


def _validate_claim_token(token: str) -> None:
    if not isinstance(token, str):
        raise TypeError("claim_token must be a string")
    if _TOKEN_PATTERN.fullmatch(token) is None:
        raise ValueError("claim_token must be an opaque URL-safe 256-bit token")


def _validate_id(value: ID, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string ID")
    if not value:
        raise ValueError(f"{field_name} is required")


def _require_type(value: object, expected: type[object], field_name: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{field_name} must be a {expected.__name__}")


def _require_integer(value: int, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be an integer")


def _require_positive_integer(value: int, field_name: str) -> None:
    _require_integer(value, field_name)
    if value < 1:
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative_integer(value: int, field_name: str) -> None:
    _require_integer(value, field_name)
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _validated_retry_hint(value: object) -> float | None:
    if (
        not isinstance(value, int | float)
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        return None
    return float(value)


__all__ = [
    "ClaimAuthority",
    "ClaimTokenSource",
    "CompleteWorkCommand",
    "FailTerminalWorkCommand",
    "RenewLeaseCommand",
    "RetryDecision",
    "RetryWorkCommand",
    "UtcClock",
    "WorkClaim",
    "WorkClaimOutcome",
    "WorkClaimRequest",
    "WorkError",
    "WorkErrorCategory",
    "WorkItemKind",
    "WorkItemLifecycleRecord",
    "WorkItemStatus",
    "WorkKindPolicy",
    "WorkLifecyclePolicy",
    "WorkTransitionResult",
    "evaluate_retry",
    "sanitize_work_error_message",
    "work_item_kind",
]
