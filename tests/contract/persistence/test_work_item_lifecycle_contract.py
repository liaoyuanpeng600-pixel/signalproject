"""Reusable durable WorkItem lifecycle contract for future concrete adapters.

The class intentionally does not start with ``Test``. A future lifecycle
adapter binds it by inheritance and supplies the fixture hooks below.
"""

from __future__ import annotations

from dataclasses import replace
from threading import Barrier

import pytest

from src.ingestion.work import DocumentProcessingWorkItem
from src.persistence.ingestion import (
    ClaimAuthority,
    CompleteWorkCommand,
    FailTerminalWorkCommand,
    RenewLeaseCommand,
    RetryWorkCommand,
    WorkClaim,
    WorkClaimLostError,
    WorkClaimRequest,
    WorkError,
    WorkErrorCategory,
    WorkInvalidTransitionError,
    WorkItemKind,
    WorkItemLifecyclePort,
    WorkItemLifecycleRecord,
    WorkItemStatus,
    WorkKindPolicy,
    WorkLifecyclePolicy,
    WorkTransitionResult,
    evaluate_retry,
)

NOW = "2026-07-26T10:00:00+00:00"
BEFORE_NOW = "2026-07-26T09:59:00+00:00"
AFTER_NOW = "2026-07-26T10:01:00+00:00"
LATER = "2026-07-26T10:05:00+00:00"
TOKEN_1 = "A" * 43
TOKEN_2 = "B" * 43


def _work(work_id: str = "work-1") -> DocumentProcessingWorkItem:
    return DocumentProcessingWorkItem(
        id=work_id,
        raw_document_id=f"raw-{work_id}",
        idempotency_key=f"document:{work_id}",
        created_at=BEFORE_NOW,
    )


def _error(*, retryable: bool) -> WorkError:
    return WorkError(
        category=(
            WorkErrorCategory.CONNECTOR_TRANSIENT
            if retryable
            else WorkErrorCategory.PAYLOAD_INVALID
        ),
        message="bounded safe failure",
        retryable=retryable,
    )


def lifecycle_contract_policy(maximum_attempts: int = 3) -> WorkLifecyclePolicy:
    """Return explicit contract-test policy without production defaults."""
    return WorkLifecyclePolicy(
        policy_version="contract-v1",
        kinds=tuple(
            WorkKindPolicy(
                kind=kind,
                maximum_attempts=maximum_attempts,
                lease_duration_seconds=300,
                renewal_interval_seconds=60,
            )
            for kind in WorkItemKind
        ),
        initial_retry_delay_seconds=10,
        maximum_retry_delay_seconds=100,
        backoff_multiplier_basis_points=20_000,
        jitter_ratio_basis_points=0,
    )


def pending_record(
    work_id: str = "work-1",
    *,
    available_at: str = BEFORE_NOW,
    priority: int = 50,
) -> WorkItemLifecycleRecord:
    """Build one v0001-compatible pending seed record."""
    return WorkItemLifecycleRecord(
        work_item=_work(work_id),
        kind=WorkItemKind.DOCUMENT_PROCESSING,
        status=WorkItemStatus.PENDING,
        priority=priority,
        available_at=available_at,
        attempt_count=0,
        revision=0,
        lease_owner=None,
        claim_token=None,
        lease_expires_at=None,
        claimed_at=None,
        completed_at=None,
        dead_lettered_at=None,
        failure=None,
        updated_at=BEFORE_NOW,
    )


class WorkItemLifecycleContract:
    """Adapter-neutral behavior required of every lifecycle port adapter."""

    def create_lifecycle_port(
        self,
        *,
        policy: WorkLifecyclePolicy,
        tokens: tuple[str, ...],
    ) -> WorkItemLifecyclePort:
        raise NotImplementedError

    def seed_lifecycle_record(self, record: WorkItemLifecycleRecord) -> None:
        raise NotImplementedError

    def read_lifecycle_record(self, work_item_id: str) -> WorkItemLifecycleRecord:
        raise NotImplementedError

    def reopen_lifecycle_port(
        self,
        *,
        policy: WorkLifecyclePolicy,
        tokens: tuple[str, ...],
    ) -> WorkItemLifecyclePort:
        raise NotImplementedError

    def claim_concurrently(
        self,
        *,
        request_one: WorkClaimRequest,
        request_two: WorkClaimRequest,
        barrier: Barrier,
    ) -> tuple[WorkClaim | WorkTransitionResult | None, ...]:
        raise NotImplementedError

    def _port(
        self,
        *,
        policy: WorkLifecyclePolicy | None = None,
        tokens: tuple[str, ...] = (TOKEN_1, TOKEN_2),
    ) -> WorkItemLifecyclePort:
        return self.create_lifecycle_port(
            policy=policy or lifecycle_contract_policy(),
            tokens=tokens,
        )

    @staticmethod
    def _request(
        policy: WorkLifecyclePolicy,
        *,
        worker_id: str = "worker-1",
        claimed_at: str = NOW,
    ) -> WorkClaimRequest:
        return WorkClaimRequest(
            worker_id=worker_id,
            allowed_kinds=(WorkItemKind.DOCUMENT_PROCESSING,),
            claimed_at=claimed_at,
            policy=policy,
        )

    @staticmethod
    def _authority(claim: WorkClaim) -> ClaimAuthority:
        return ClaimAuthority(
            work_item_id=claim.work_item.id,
            worker_id=claim.worker_id,
            claim_token=claim.claim_token,
            expected_revision=claim.revision,
        )

    def _claim_seed(
        self,
        record: WorkItemLifecycleRecord | None = None,
        *,
        policy: WorkLifecyclePolicy | None = None,
        token: str = TOKEN_1,
    ) -> tuple[WorkItemLifecyclePort, WorkClaim, WorkLifecyclePolicy]:
        selected_policy = policy or lifecycle_contract_policy()
        selected_record = record or pending_record()
        self.seed_lifecycle_record(selected_record)
        port = self._port(policy=selected_policy, tokens=(token, TOKEN_2))
        outcome = port.claim_next(self._request(selected_policy))
        assert isinstance(outcome, WorkClaim)
        return port, outcome, selected_policy

    def test_pending_due_claim_returns_canonical_running_authority(self) -> None:
        port, claim, _ = self._claim_seed()
        stored = self.read_lifecycle_record(claim.work_item.id)

        assert claim.attempt_count == 1
        assert claim.revision == 1
        assert claim.claim_token == TOKEN_1
        assert claim.reclaimed is False
        assert stored.status is WorkItemStatus.RUNNING
        assert stored.attempt_count == 1
        assert stored.revision == 1
        assert stored.lease_owner == claim.worker_id
        assert stored.claim_token == claim.claim_token
        assert stored.claimed_at == NOW
        assert stored.available_at is None
        assert port is not None

    def test_due_retrying_claim_increments_attempt_and_revision_once(self) -> None:
        record = replace(
            pending_record(),
            status=WorkItemStatus.RETRYING,
            available_at=NOW,
            attempt_count=1,
            revision=2,
            claimed_at=BEFORE_NOW,
            failure=_error(retryable=True),
        )

        _, claim, _ = self._claim_seed(record)

        assert claim.attempt_count == 2
        assert claim.revision == 3
        assert self.read_lifecycle_record("work-1").failure is None

    def test_not_due_pending_or_retrying_is_excluded(self) -> None:
        policy = lifecycle_contract_policy()
        self.seed_lifecycle_record(pending_record(available_at=AFTER_NOW))
        self.seed_lifecycle_record(
            replace(
                pending_record("work-retrying", available_at=AFTER_NOW),
                status=WorkItemStatus.RETRYING,
                attempt_count=1,
                revision=2,
                claimed_at=BEFORE_NOW,
                failure=_error(retryable=True),
            )
        )
        port = self._port(policy=policy)

        assert port.claim_next(self._request(policy)) is None
        assert self.read_lifecycle_record("work-1") == pending_record(
            available_at=AFTER_NOW
        )

    def test_expired_running_is_directly_reclaimed(self) -> None:
        record = replace(
            pending_record(),
            status=WorkItemStatus.RUNNING,
            available_at=None,
            attempt_count=1,
            revision=1,
            lease_owner="old-worker",
            claim_token=TOKEN_1,
            lease_expires_at=NOW,
            claimed_at=BEFORE_NOW,
        )

        _, claim, _ = self._claim_seed(record, token=TOKEN_2)

        assert claim.reclaimed is True
        assert claim.prior_worker_id == "old-worker"
        assert claim.claim_token == TOKEN_2
        assert claim.attempt_count == 2
        assert claim.revision == 2

    def test_unexpired_running_is_excluded_without_mutation(self) -> None:
        policy = lifecycle_contract_policy()
        record = replace(
            pending_record(),
            status=WorkItemStatus.RUNNING,
            available_at=None,
            attempt_count=1,
            revision=1,
            lease_owner="old-worker",
            claim_token=TOKEN_1,
            lease_expires_at=AFTER_NOW,
            claimed_at=BEFORE_NOW,
        )
        self.seed_lifecycle_record(record)

        assert self._port(policy=policy).claim_next(self._request(policy)) is None
        assert self.read_lifecycle_record("work-1") == record

    def test_no_work_returns_none(self) -> None:
        policy = lifecycle_contract_policy()
        assert self._port(policy=policy).claim_next(self._request(policy)) is None

    def test_ordering_is_expired_then_lower_priority_then_due_then_id(self) -> None:
        policy = lifecycle_contract_policy()
        self.seed_lifecycle_record(pending_record("work-z", priority=10))
        self.seed_lifecycle_record(pending_record("work-a", priority=10))
        expired = replace(
            pending_record("work-expired", priority=99),
            status=WorkItemStatus.RUNNING,
            available_at=None,
            attempt_count=1,
            revision=1,
            lease_owner="old-worker",
            claim_token=TOKEN_1,
            lease_expires_at=NOW,
            claimed_at=BEFORE_NOW,
        )
        self.seed_lifecycle_record(expired)

        outcome = self._port(
            policy=policy,
            tokens=(TOKEN_2,),
        ).claim_next(self._request(policy))

        assert isinstance(outcome, WorkClaim)
        assert outcome.work_item.id == "work-expired"

    def test_due_ordering_uses_priority_availability_and_id_directions(self) -> None:
        policy = lifecycle_contract_policy()
        self.seed_lifecycle_record(
            pending_record(
                "work-priority",
                priority=10,
                available_at=NOW,
            )
        )
        self.seed_lifecycle_record(
            pending_record(
                "work-z",
                priority=20,
                available_at=BEFORE_NOW,
            )
        )
        self.seed_lifecycle_record(
            pending_record(
                "work-a",
                priority=20,
                available_at=BEFORE_NOW,
            )
        )
        self.seed_lifecycle_record(
            replace(
                pending_record(
                    "work-z-old",
                    priority=20,
                    available_at=BEFORE_NOW,
                ),
                work_item=replace(
                    _work("work-z-old"),
                    created_at="2026-07-26T09:00:00+00:00",
                ),
            )
        )
        self.seed_lifecycle_record(
            pending_record(
                "work-later",
                priority=20,
                available_at=NOW,
            )
        )
        port = self._port(
            policy=policy,
            tokens=(TOKEN_1, TOKEN_2, "C" * 43, "D" * 43, "E" * 43),
        )

        outcomes = tuple(
            port.claim_next(self._request(policy))
            for _ in range(5)
        )

        assert tuple(
            outcome.work_item.id
            for outcome in outcomes
            if isinstance(outcome, WorkClaim)
        ) == (
            "work-priority",
            "work-z-old",
            "work-a",
            "work-z",
            "work-later",
        )

    def test_lost_claim_race_returns_one_claim_and_one_none(self) -> None:
        policy = lifecycle_contract_policy()
        self.seed_lifecycle_record(pending_record())
        barrier = Barrier(2)

        outcomes = self.claim_concurrently(
            request_one=self._request(policy, worker_id="worker-1"),
            request_two=self._request(policy, worker_id="worker-2"),
            barrier=barrier,
        )

        assert sum(isinstance(outcome, WorkClaim) for outcome in outcomes) == 1
        assert sum(outcome is None for outcome in outcomes) == 1
        stored = self.read_lifecycle_record("work-1")
        assert stored.attempt_count == 1
        assert stored.revision == 1

    @pytest.mark.parametrize(
        "authority_change",
        [
            {"worker_id": "worker-other"},
            {"claim_token": TOKEN_2},
            {"expected_revision": 0},
            {"work_item_id": "work-other"},
        ],
    )
    def test_authority_mismatch_rejects_without_mutation(
        self,
        authority_change: dict[str, object],
    ) -> None:
        port, claim, _ = self._claim_seed()
        before = self.read_lifecycle_record("work-1")
        authority = replace(self._authority(claim), **authority_change)

        with pytest.raises(WorkClaimLostError):
            port.complete(CompleteWorkCommand(authority, AFTER_NOW))

        assert self.read_lifecycle_record("work-1") == before

    def test_renewal_before_expiry_preserves_attempt_owner_and_token(self) -> None:
        port, claim, _ = self._claim_seed()

        renewed = port.renew_lease(
            RenewLeaseCommand(
                authority=self._authority(claim),
                renewed_at=AFTER_NOW,
                lease_duration_seconds=300,
            )
        )

        assert renewed.worker_id == claim.worker_id
        assert renewed.claim_token == claim.claim_token
        assert renewed.attempt_count == claim.attempt_count
        assert renewed.revision == claim.revision + 1
        assert renewed.lease_expires_at > claim.lease_expires_at

    def test_renewal_at_expiry_is_stale_without_mutation(self) -> None:
        port, claim, _ = self._claim_seed()
        before = self.read_lifecycle_record("work-1")

        with pytest.raises(WorkClaimLostError):
            port.renew_lease(
                RenewLeaseCommand(
                    authority=self._authority(claim),
                    renewed_at=claim.lease_expires_at,
                    lease_duration_seconds=300,
                )
            )

        assert self.read_lifecycle_record("work-1") == before

    def test_completion_at_expiry_is_stale_without_mutation(self) -> None:
        port, claim, _ = self._claim_seed()
        before = self.read_lifecycle_record("work-1")

        with pytest.raises(WorkClaimLostError):
            port.complete(
                CompleteWorkCommand(
                    self._authority(claim),
                    claim.lease_expires_at,
                )
            )

        assert self.read_lifecycle_record("work-1") == before

    def test_completion_preserves_attempt_and_increments_revision_once(self) -> None:
        port, claim, _ = self._claim_seed()

        result = port.complete(
            CompleteWorkCommand(self._authority(claim), AFTER_NOW)
        )
        stored = self.read_lifecycle_record("work-1")

        assert result.to_status is WorkItemStatus.COMPLETED
        assert result.attempt_count == claim.attempt_count
        assert result.revision == claim.revision + 1
        assert stored.completed_at == AFTER_NOW
        assert stored.lease_owner is None

    def test_retryable_failure_schedules_retry_without_attempt_increment(self) -> None:
        port, claim, policy = self._claim_seed()
        decision = evaluate_retry(
            policy=policy,
            kind=claim.kind,
            work_item_id=claim.work_item.id,
            attempt_count=claim.attempt_count,
            failed_at=AFTER_NOW,
        )

        result = port.fail_retryable(
            RetryWorkCommand(
                self._authority(claim),
                AFTER_NOW,
                decision,
                _error(retryable=True),
            )
        )

        assert result.to_status is WorkItemStatus.RETRYING
        assert result.attempt_count == claim.attempt_count
        assert result.revision == claim.revision + 1
        assert result.available_at == decision.available_at

    def test_terminal_failure_dead_letters_without_attempt_increment(self) -> None:
        port, claim, _ = self._claim_seed()

        result = port.fail_terminal(
            FailTerminalWorkCommand(
                self._authority(claim),
                AFTER_NOW,
                _error(retryable=False),
            )
        )

        assert result.to_status is WorkItemStatus.DEAD_LETTER
        assert result.attempt_count == claim.attempt_count
        assert result.revision == claim.revision + 1
        assert result.exhausted is False

    def test_retry_exhaustion_uses_current_post_claim_attempt(self) -> None:
        policy = lifecycle_contract_policy(maximum_attempts=1)
        port, claim, _ = self._claim_seed(policy=policy)
        decision = evaluate_retry(
            policy=policy,
            kind=claim.kind,
            work_item_id=claim.work_item.id,
            attempt_count=claim.attempt_count,
            failed_at=AFTER_NOW,
        )

        result = port.fail_retryable(
            RetryWorkCommand(
                self._authority(claim),
                AFTER_NOW,
                decision,
                _error(retryable=True),
            )
        )

        assert decision.exhausted is True
        assert result.to_status is WorkItemStatus.DEAD_LETTER
        assert result.attempt_count == 1
        assert result.revision == 2
        assert result.exhausted is True

    def test_expired_work_at_budget_is_normalized_without_another_attempt(self) -> None:
        policy = lifecycle_contract_policy(maximum_attempts=1)
        expired = replace(
            pending_record(),
            status=WorkItemStatus.RUNNING,
            available_at=None,
            attempt_count=1,
            revision=1,
            lease_owner="old-worker",
            claim_token=TOKEN_1,
            lease_expires_at=NOW,
            claimed_at=BEFORE_NOW,
        )
        self.seed_lifecycle_record(expired)

        outcome = self._port(
            policy=policy,
            tokens=(TOKEN_2,),
        ).claim_next(self._request(policy))

        assert isinstance(outcome, WorkTransitionResult)
        assert outcome.to_status is WorkItemStatus.DEAD_LETTER
        assert outcome.attempt_count == 1
        assert outcome.revision == 2
        assert outcome.exhausted is True

    def test_stale_claimant_after_reclaim_cannot_complete(self) -> None:
        policy = lifecycle_contract_policy()
        expired = replace(
            pending_record(),
            status=WorkItemStatus.RUNNING,
            available_at=None,
            attempt_count=1,
            revision=1,
            lease_owner="old-worker",
            claim_token=TOKEN_1,
            lease_expires_at=NOW,
            claimed_at=BEFORE_NOW,
        )
        old_authority = ClaimAuthority("work-1", "old-worker", TOKEN_1, 1)
        self.seed_lifecycle_record(expired)
        port = self._port(policy=policy, tokens=(TOKEN_2,))
        reclaimed = port.claim_next(
            self._request(policy, worker_id="new-worker", claimed_at=AFTER_NOW)
        )
        assert isinstance(reclaimed, WorkClaim)
        before = self.read_lifecycle_record("work-1")

        with pytest.raises(WorkClaimLostError):
            port.complete(CompleteWorkCommand(old_authority, AFTER_NOW))

        assert self.read_lifecycle_record("work-1") == before

    def test_terminal_state_rejects_further_transition(self) -> None:
        port, claim, _ = self._claim_seed()
        port.complete(CompleteWorkCommand(self._authority(claim), AFTER_NOW))
        before = self.read_lifecycle_record("work-1")

        with pytest.raises(WorkInvalidTransitionError):
            port.complete(CompleteWorkCommand(self._authority(claim), AFTER_NOW))

        assert self.read_lifecycle_record("work-1") == before

    def test_sanitized_failure_metadata_round_trips_canonically(self) -> None:
        port, claim, _ = self._claim_seed()
        error = _error(retryable=False)

        result = port.fail_terminal(
            FailTerminalWorkCommand(self._authority(claim), AFTER_NOW, error)
        )
        stored = self.read_lifecycle_record("work-1")

        assert result.error == error
        assert stored.failure == error
        assert TOKEN_1 not in stored.failure.message

    def test_restart_preserves_claim_authority_and_state(self) -> None:
        _, claim, policy = self._claim_seed()

        reopened = self.reopen_lifecycle_port(
            policy=policy,
            tokens=(TOKEN_2,),
        )
        stored = self.read_lifecycle_record("work-1")

        assert stored.status is WorkItemStatus.RUNNING
        assert stored.claim_token == claim.claim_token
        assert reopened is not None


__all__ = [
    "WorkItemLifecycleContract",
    "lifecycle_contract_policy",
    "pending_record",
]
