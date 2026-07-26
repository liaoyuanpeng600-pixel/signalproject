from __future__ import annotations

from tests.contract.persistence.test_work_item_lifecycle_contract import (
    WorkItemLifecycleContract,
)


def test_lifecycle_adapter_contract_suite_is_reusable_and_unbound() -> None:
    required = {
        "test_pending_due_claim_returns_canonical_running_authority",
        "test_due_retrying_claim_increments_attempt_and_revision_once",
        "test_not_due_pending_or_retrying_is_excluded",
        "test_expired_running_is_directly_reclaimed",
        "test_unexpired_running_is_excluded_without_mutation",
        "test_ordering_is_expired_then_lower_priority_then_due_then_id",
        "test_due_ordering_uses_priority_availability_and_id_directions",
        "test_lost_claim_race_returns_one_claim_and_one_none",
        "test_authority_mismatch_rejects_without_mutation",
        "test_renewal_before_expiry_preserves_attempt_owner_and_token",
        "test_renewal_at_expiry_is_stale_without_mutation",
        "test_completion_at_expiry_is_stale_without_mutation",
        "test_completion_preserves_attempt_and_increments_revision_once",
        "test_retryable_failure_schedules_retry_without_attempt_increment",
        "test_terminal_failure_dead_letters_without_attempt_increment",
        "test_retry_exhaustion_uses_current_post_claim_attempt",
        "test_expired_work_at_budget_is_normalized_without_another_attempt",
        "test_stale_claimant_after_reclaim_cannot_complete",
        "test_sanitized_failure_metadata_round_trips_canonically",
        "test_restart_preserves_claim_authority_and_state",
    }

    assert required.issubset(vars(WorkItemLifecycleContract))
    assert callable(WorkItemLifecycleContract.create_lifecycle_port)
    assert callable(WorkItemLifecycleContract.seed_lifecycle_record)
    assert callable(WorkItemLifecycleContract.read_lifecycle_record)
    assert callable(WorkItemLifecycleContract.claim_concurrently)
