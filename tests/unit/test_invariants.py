"""Tests for the invariants module (INV-1, INV-3, INV-4, INV-12)."""

import pytest

from src.core.invariants import (
    COMPOSITE_WEIGHTS,
    Score,
    assert_composite_weights_sum_to_one,
    assert_inv_1,
    assert_inv_3,
    assert_inv_4,
    assert_inv_9,
    assert_inv_10,
)


class TestCompositeWeights:
    def test_weights_sum_to_one(self) -> None:
        # INV-12
        assert_composite_weights_sum_to_one()
        assert sum(COMPOSITE_WEIGHTS.values()) == pytest.approx(1.0)

    def test_canonical_weights(self) -> None:
        # Per 06_scoring_framework §4
        assert COMPOSITE_WEIGHTS["magnitude"] == 0.30
        assert COMPOSITE_WEIGHTS["confidence"] == 0.25
        assert COMPOSITE_WEIGHTS["timeliness"] == 0.20
        assert COMPOSITE_WEIGHTS["novelty"] == 0.15
        assert COMPOSITE_WEIGHTS["actionability"] == 0.10


class TestScoreInvariant4:
    def test_valid_score(self) -> None:
        score = Score(0.5, 0.8, 0.3, 0.7, 0.9)
        assert score.magnitude == 0.5
        assert_inv_4(score)

    def test_boundary_zero(self) -> None:
        score = Score(0.0, 0.0, 0.0, 0.0, 0.0)
        assert_inv_4(score)

    def test_boundary_one(self) -> None:
        score = Score(1.0, 1.0, 1.0, 1.0, 1.0)
        assert_inv_4(score)

    def test_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="INV-4"):
            Score(-0.1, 0.5, 0.5, 0.5, 0.5)

    def test_above_one_rejected(self) -> None:
        with pytest.raises(ValueError, match="INV-4"):
            Score(0.5, 1.5, 0.5, 0.5, 0.5)

    def test_assert_inv_4_passes_for_valid_score(self) -> None:
        # Smoke test: assert_inv_4 does not raise on a valid Score.
        score = Score(0.5, 0.5, 0.5, 0.5, 0.5)
        assert_inv_4(score)  # Should not raise

    def test_inv_4_blocked_at_construction(self) -> None:
        # The assert function is a backup; the primary enforcement is in
        # Score.__post_init__. Out-of-range values cannot be constructed.
        # Already covered by test_negative_rejected / test_above_one_rejected
        # but we assert here for explicitness.
        with pytest.raises(ValueError, match="INV-4"):
            Score(-0.1, 0.5, 0.5, 0.5, 0.5)
        with pytest.raises(ValueError, match="INV-4"):
            Score(0.5, 1.5, 0.5, 0.5, 0.5)


class TestScoreComposite:
    def test_composite_calculation(self) -> None:
        score = Score(0.9, 0.95, 0.80, 0.70, 0.75)
        # 0.30*0.9 + 0.25*0.95 + 0.20*0.80 + 0.15*0.70 + 0.10*0.75
        # = 0.27 + 0.2375 + 0.16 + 0.105 + 0.075
        # = 0.8475
        assert score.composite == pytest.approx(0.8475)

    def test_composite_with_zero_scores(self) -> None:
        score = Score(0.0, 0.0, 0.0, 0.0, 0.0)
        assert score.composite == 0.0

    def test_composite_with_max_scores(self) -> None:
        score = Score(1.0, 1.0, 1.0, 1.0, 1.0)
        assert score.composite == 1.0


class TestInvariant1:
    def test_zero_evidence_fails(self) -> None:
        with pytest.raises(AssertionError, match="INV-1"):
            assert_inv_1(0)

    def test_one_evidence_passes(self) -> None:
        assert_inv_1(1)  # Should not raise

    def test_multiple_evidence_passes(self) -> None:
        assert_inv_1(5)


class TestInvariant3:
    def test_no_provenance_fails(self) -> None:
        with pytest.raises(AssertionError, match="INV-3"):
            assert_inv_3(False)

    def test_with_provenance_passes(self) -> None:
        assert_inv_3(True)


class TestInvariant9:
    def test_empty_cycle_id_fails(self) -> None:
        with pytest.raises(AssertionError, match="INV-9"):
            assert_inv_9("")

    def test_non_string_fails(self) -> None:
        with pytest.raises(AssertionError, match="INV-9"):
            assert_inv_9(123)  # type: ignore[arg-type]

    def test_uuid_passes(self) -> None:
        assert_inv_9("01HXY1234567890ABCDEFGHJK")


class TestInvariant10:
    def test_valid_utc_passes(self) -> None:
        assert_inv_10("2026-07-18T12:34:56+00:00")
        assert_inv_10("2026-07-18T12:34:56Z")

    def test_invalid_fails(self) -> None:
        with pytest.raises(AssertionError, match="INV-10"):
            assert_inv_10("not-a-timestamp")
