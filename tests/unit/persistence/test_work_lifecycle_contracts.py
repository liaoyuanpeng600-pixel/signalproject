from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone

import pytest

import src.persistence.ingestion as persistence_contracts
from src.ingestion.work import DocumentProcessingWorkItem
from src.persistence.ingestion import (
    ClaimTokenSource,
    ClaimAuthority,
    CompleteWorkCommand,
    FailTerminalWorkCommand,
    RenewLeaseCommand,
    RetryDecision,
    RetryWorkCommand,
    UtcClock,
    WorkClaim,
    WorkClaimRequest,
    WorkError,
    WorkErrorCategory,
    WorkItemKind,
    WorkItemLifecycleRecord,
    WorkItemStatus,
    WorkKindPolicy,
    WorkLifecyclePolicy,
    WorkTransitionResult,
    evaluate_retry,
    sanitize_work_error_message,
)

NOW = "2026-07-26T10:00:00+00:00"
LATER = "2026-07-26T10:05:00+00:00"
TOKEN = "A" * 43


def _work() -> DocumentProcessingWorkItem:
    return DocumentProcessingWorkItem(
        id="work-1",
        raw_document_id="raw-1",
        idempotency_key="document:raw-1",
        created_at=NOW,
    )


def _policy(
    *,
    maximum_attempts: int = 3,
    initial_delay: int = 10,
    maximum_delay: int = 100,
    multiplier: int = 20_000,
    jitter: int = 0,
) -> WorkLifecyclePolicy:
    return WorkLifecyclePolicy(
        policy_version="phase7-test-v1",
        kinds=tuple(
            WorkKindPolicy(
                kind=kind,
                maximum_attempts=maximum_attempts,
                lease_duration_seconds=300,
                renewal_interval_seconds=60,
            )
            for kind in WorkItemKind
        ),
        initial_retry_delay_seconds=initial_delay,
        maximum_retry_delay_seconds=maximum_delay,
        backoff_multiplier_basis_points=multiplier,
        jitter_ratio_basis_points=jitter,
    )


def _authority(*, revision: int = 1, token: str = TOKEN) -> ClaimAuthority:
    return ClaimAuthority(
        work_item_id="work-1",
        worker_id="worker:1",
        claim_token=token,
        expected_revision=revision,
    )


def _retryable_error(message: str = "temporary provider failure") -> WorkError:
    return WorkError(
        category=WorkErrorCategory.CONNECTOR_TRANSIENT,
        message=message,
        retryable=True,
    )


def _terminal_error() -> WorkError:
    return WorkError(
        category=WorkErrorCategory.PAYLOAD_INVALID,
        message="payload failed validation",
        retryable=False,
    )


def test_lifecycle_enums_are_exact() -> None:
    assert {status.value for status in WorkItemStatus} == {
        "pending",
        "running",
        "retrying",
        "completed",
        "dead_letter",
    }


def test_lifecycle_contracts_have_stable_public_exports_and_protocols() -> None:
    required = {
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
        "WorkItemLifecyclePort",
        "WorkItemLifecycleRecord",
        "WorkItemStatus",
        "WorkKindPolicy",
        "WorkLifecyclePolicy",
        "WorkTransitionResult",
        "evaluate_retry",
        "sanitize_work_error_message",
        "work_item_kind",
    }

    assert required.issubset(persistence_contracts.__all__)
    assert getattr(UtcClock, "_is_protocol", False)
    assert getattr(ClaimTokenSource, "_is_protocol", False)
    assert {kind.value for kind in WorkItemKind} == {
        "collection",
        "document_processing",
        "research",
    }


def test_policy_is_immutable_and_configures_every_kind() -> None:
    policy = _policy()

    assert policy.for_kind(WorkItemKind.RESEARCH).maximum_attempts == 3
    with pytest.raises(FrozenInstanceError):
        policy.policy_version = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("initial_retry_delay_seconds", 0, "positive"),
        ("maximum_retry_delay_seconds", 0, "positive"),
        ("backoff_multiplier_basis_points", 9_999, "at least 10000"),
        ("jitter_ratio_basis_points", -1, "between 0 and 9999"),
        ("jitter_ratio_basis_points", 10_000, "between 0 and 9999"),
    ],
)
def test_policy_rejects_invalid_retry_configuration(
    field: str,
    value: int,
    message: str,
) -> None:
    values = {
        "policy_version": "phase7-test-v1",
        "kinds": _policy().kinds,
        "initial_retry_delay_seconds": 10,
        "maximum_retry_delay_seconds": 100,
        "backoff_multiplier_basis_points": 20_000,
        "jitter_ratio_basis_points": 0,
    }
    values[field] = value

    with pytest.raises(ValueError, match=message):
        WorkLifecyclePolicy(**values)  # type: ignore[arg-type]


def test_policy_rejects_missing_duplicate_and_invalid_kind_configuration() -> None:
    policies = _policy().kinds

    with pytest.raises(ValueError, match="every WorkItemKind"):
        replace(_policy(), kinds=policies[:-1])
    with pytest.raises(ValueError, match="duplicates"):
        replace(_policy(), kinds=(policies[0], policies[0], policies[2]))
    with pytest.raises(ValueError, match="less than"):
        replace(policies[0], renewal_interval_seconds=300)


def test_retry_evaluation_uses_post_claim_attempt_and_exhausts_at_budget() -> None:
    policy = _policy(maximum_attempts=3)

    available = evaluate_retry(
        policy=policy,
        kind=WorkItemKind.DOCUMENT_PROCESSING,
        work_item_id="work-1",
        attempt_count=2,
        failed_at=NOW,
    )
    exhausted = evaluate_retry(
        policy=policy,
        kind=WorkItemKind.DOCUMENT_PROCESSING,
        work_item_id="work-1",
        attempt_count=3,
        failed_at=NOW,
    )

    assert available.exhausted is False
    assert available.available_at == "2026-07-26T10:00:20+00:00"
    assert exhausted.exhausted is True
    assert exhausted.available_at is None
    assert exhausted.attempt_count == 3


def test_retry_evaluation_is_deterministic_and_caps_delay_and_hint() -> None:
    policy = _policy(
        initial_delay=50,
        maximum_delay=60,
        multiplier=30_000,
        jitter=2_000,
    )

    first = evaluate_retry(
        policy=policy,
        kind=WorkItemKind.COLLECTION,
        work_item_id="work-1",
        attempt_count=2,
        failed_at=NOW,
        retry_after_seconds=10_000,
    )
    second = evaluate_retry(
        policy=policy,
        kind=WorkItemKind.COLLECTION,
        work_item_id="work-1",
        attempt_count=2,
        failed_at=NOW,
        retry_after_seconds=10_000,
    )

    assert first == second
    assert first.available_at == "2026-07-26T10:01:00+00:00"


@pytest.mark.parametrize("hint", [-1, float("inf"), float("nan"), "later", True])
def test_retry_evaluation_ignores_invalid_provider_hint(hint: object) -> None:
    expected = evaluate_retry(
        policy=_policy(),
        kind=WorkItemKind.COLLECTION,
        work_item_id="work-1",
        attempt_count=1,
        failed_at=NOW,
    )

    actual = evaluate_retry(
        policy=_policy(),
        kind=WorkItemKind.COLLECTION,
        work_item_id="work-1",
        attempt_count=1,
        failed_at=NOW,
        retry_after_seconds=hint,
    )

    assert actual == expected


def test_retry_decision_rejects_inconsistent_exhaustion() -> None:
    with pytest.raises(ValueError, match="attempt budget"):
        RetryDecision("policy-v1", 3, 3, False, LATER)
    with pytest.raises(ValueError, match="cannot be available"):
        RetryDecision("policy-v1", 3, 3, True, LATER)
    with pytest.raises(ValueError, match="requires available_at"):
        RetryDecision("policy-v1", 3, 2, False, None)


def test_claim_request_rejects_naive_time_and_duplicate_kinds() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        WorkClaimRequest(
            worker_id="worker-1",
            allowed_kinds=(WorkItemKind.COLLECTION,),
            claimed_at="2026-07-26T10:00:00",
            policy=_policy(),
        )
    with pytest.raises(ValueError, match="duplicates"):
        WorkClaimRequest(
            worker_id="worker-1",
            allowed_kinds=(WorkItemKind.COLLECTION, WorkItemKind.COLLECTION),
            claimed_at=NOW,
            policy=_policy(),
        )


def test_timestamps_must_use_utc_not_only_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="must use UTC"):
        CompleteWorkCommand(
            authority=_authority(),
            completed_at="2026-07-26T18:00:00+08:00",
        )


def test_claim_validates_kind_token_and_reclaim_metadata() -> None:
    claim = WorkClaim(
        work_item=_work(),
        kind=WorkItemKind.DOCUMENT_PROCESSING,
        worker_id="worker:1",
        claim_token=TOKEN,
        claimed_at=NOW,
        lease_expires_at=LATER,
        attempt_count=1,
        revision=1,
        reclaimed=False,
        prior_worker_id=None,
    )

    assert claim.claim_token == TOKEN
    with pytest.raises(FrozenInstanceError):
        claim.revision = 2  # type: ignore[misc]
    with pytest.raises(ValueError, match="opaque"):
        replace(claim, claim_token="row-1")
    with pytest.raises(ValueError, match="kind"):
        replace(claim, kind=WorkItemKind.RESEARCH)
    with pytest.raises(ValueError, match="prior_worker_id"):
        replace(claim, reclaimed=True)


def test_claim_authority_requires_owner_token_and_revision() -> None:
    authority = _authority()

    assert authority.worker_id == "worker:1"
    assert authority.expected_revision == 1
    with pytest.raises(ValueError, match="opaque"):
        replace(authority, claim_token="work-1")
    with pytest.raises(ValueError, match="non-negative"):
        replace(authority, expected_revision=-1)


def test_error_metadata_is_bounded_sanitized_and_category_consistent() -> None:
    assert sanitize_work_error_message("  failed\r\n\t now \x00 ") == "failed now"

    with pytest.raises(ValueError, match="sanitized"):
        _retryable_error("failed\nnow")
    with pytest.raises(ValueError, match="1024"):
        _retryable_error("x" * 1_025)
    with pytest.raises(ValueError, match="agree"):
        WorkError(
            category=WorkErrorCategory.PAYLOAD_INVALID,
            message="invalid",
            retryable=True,
        )
    with pytest.raises(TypeError, match="string"):
        WorkError(  # type: ignore[arg-type]
            category=WorkErrorCategory.UNEXPECTED,
            message=RuntimeError("raw"),
            retryable=True,
        )


def test_failure_commands_reject_wrong_classification_and_raw_claim_token() -> None:
    decision = evaluate_retry(
        policy=_policy(),
        kind=WorkItemKind.DOCUMENT_PROCESSING,
        work_item_id="work-1",
        attempt_count=1,
        failed_at=NOW,
    )

    with pytest.raises(ValueError, match="retryable WorkError"):
        RetryWorkCommand(_authority(), NOW, decision, _terminal_error())
    with pytest.raises(ValueError, match="terminal WorkError"):
        FailTerminalWorkCommand(_authority(), NOW, _retryable_error())
    with pytest.raises(ValueError, match="claim token"):
        RetryWorkCommand(
            _authority(),
            NOW,
            decision,
            _retryable_error(f"failure token {TOKEN}"),
        )


def test_renewal_and_completion_commands_are_immutable() -> None:
    renewal = RenewLeaseCommand(_authority(), NOW, 300)
    completion = CompleteWorkCommand(_authority(), NOW)

    with pytest.raises(FrozenInstanceError):
        renewal.lease_duration_seconds = 1  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        completion.completed_at = LATER  # type: ignore[misc]


def test_transition_results_accept_only_frozen_lifecycle_shapes() -> None:
    renewal = WorkTransitionResult(
        work_item_id="work-1",
        kind=WorkItemKind.DOCUMENT_PROCESSING,
        from_status=WorkItemStatus.RUNNING,
        to_status=WorkItemStatus.RUNNING,
        occurred_at=NOW,
        attempt_count=1,
        revision=2,
        available_at=None,
        lease_expires_at=LATER,
        error=None,
        exhausted=False,
    )

    assert renewal.attempt_count == 1
    with pytest.raises(ValueError, match="renewal"):
        replace(renewal, lease_expires_at=None)
    with pytest.raises(ValueError, match="unsupported"):
        replace(renewal, from_status=WorkItemStatus.PENDING)


def test_pending_record_is_v0001_compatible() -> None:
    record = WorkItemLifecycleRecord(
        work_item=_work(),
        kind=WorkItemKind.DOCUMENT_PROCESSING,
        status=WorkItemStatus.PENDING,
        priority=50,
        available_at=NOW,
        attempt_count=0,
        revision=0,
        lease_owner=None,
        claim_token=None,
        lease_expires_at=None,
        claimed_at=None,
        completed_at=None,
        dead_lettered_at=None,
        failure=None,
        updated_at=NOW,
    )

    assert record.revision == 0
    with pytest.raises(ValueError, match="pending"):
        replace(record, attempt_count=1)


def test_running_record_requires_complete_lease_authority() -> None:
    pending = WorkItemLifecycleRecord(
        work_item=_work(),
        kind=WorkItemKind.DOCUMENT_PROCESSING,
        status=WorkItemStatus.PENDING,
        priority=50,
        available_at=NOW,
        attempt_count=0,
        revision=0,
        lease_owner=None,
        claim_token=None,
        lease_expires_at=None,
        claimed_at=None,
        completed_at=None,
        dead_lettered_at=None,
        failure=None,
        updated_at=NOW,
    )

    running = replace(
        pending,
        status=WorkItemStatus.RUNNING,
        available_at=None,
        attempt_count=1,
        revision=1,
        lease_owner="worker-1",
        claim_token=TOKEN,
        lease_expires_at=LATER,
        claimed_at=NOW,
    )

    assert running.status is WorkItemStatus.RUNNING
    with pytest.raises(ValueError, match="all present"):
        replace(running, claim_token=None)


def test_retrying_completed_and_dead_letter_record_invariants() -> None:
    running = WorkItemLifecycleRecord(
        work_item=_work(),
        kind=WorkItemKind.DOCUMENT_PROCESSING,
        status=WorkItemStatus.RUNNING,
        priority=50,
        available_at=None,
        attempt_count=1,
        revision=1,
        lease_owner="worker-1",
        claim_token=TOKEN,
        lease_expires_at=LATER,
        claimed_at=NOW,
        completed_at=None,
        dead_lettered_at=None,
        failure=None,
        updated_at=NOW,
    )
    retrying = replace(
        running,
        status=WorkItemStatus.RETRYING,
        available_at=LATER,
        revision=2,
        lease_owner=None,
        claim_token=None,
        lease_expires_at=None,
        failure=_retryable_error(),
    )
    completed = replace(
        running,
        status=WorkItemStatus.COMPLETED,
        revision=2,
        lease_owner=None,
        claim_token=None,
        lease_expires_at=None,
        completed_at=LATER,
        updated_at=LATER,
    )
    dead = replace(
        running,
        status=WorkItemStatus.DEAD_LETTER,
        revision=2,
        lease_owner=None,
        claim_token=None,
        lease_expires_at=None,
        dead_lettered_at=LATER,
        failure=_terminal_error(),
        updated_at=LATER,
    )

    assert retrying.failure is not None and retrying.failure.retryable
    assert completed.completed_at == LATER
    assert dead.dead_lettered_at == LATER


def test_utc_values_round_trip_without_implicit_clock_access() -> None:
    decision = evaluate_retry(
        policy=_policy(),
        kind=WorkItemKind.DOCUMENT_PROCESSING,
        work_item_id="work-1",
        attempt_count=1,
        failed_at=NOW,
    )

    parsed = datetime.fromisoformat(decision.available_at or "")
    assert parsed.tzinfo is timezone.utc
