"""Tests for the Evidence type (INV-1, INV-3, immutability)."""

import pytest

from src.core.evidence import Evidence, Quality, SourceType


class TestEvidenceCreate:
    def test_minimal_creation(self) -> None:
        evidence = Evidence.create(
            source_ids=("source-1",),
            content="ACME announced a buyback.",
            quality=Quality(
                source_reliability=0.95,
                content_completeness=1.0,
                retrieval_confidence=0.99,
            ),
        )
        assert evidence.id
        assert evidence.content == "ACME announced a buyback."
        assert evidence.source_ids == ("source-1",)
        assert evidence.retrievable is True

    def test_with_multiple_sources(self) -> None:
        evidence = Evidence.create(
            source_ids=("source-1", "source-2"),
            content="Multi-source corroborated.",
            quality=Quality(
                source_reliability=0.95,
                content_completeness=1.0,
                retrieval_confidence=0.95,
            ),
        )
        assert len(evidence.source_ids) == 2

    def test_with_optional_fields(self) -> None:
        evidence = Evidence.create(
            source_ids=("source-1",),
            content="ACME announced X.",
            quality=Quality(0.9, 0.9, 0.9),
            source_type=SourceType.PRESS_RELEASE,
            char_offset=(100, 200),
            excerpt="...ACME announced X...",
            document_hash="sha256:abc123",
        )
        assert evidence.source_type == SourceType.PRESS_RELEASE
        assert evidence.char_offset == (100, 200)
        assert evidence.excerpt == "...ACME announced X..."
        assert evidence.document_hash == "sha256:abc123"


class TestEvidenceImmutability:
    def test_cannot_modify_content(self) -> None:
        evidence = Evidence.create(
            source_ids=("s1",),
            content="Original.",
            quality=Quality(0.9, 0.9, 0.9),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            evidence.content = "Modified"  # type: ignore[misc]

    def test_cannot_modify_source_ids(self) -> None:
        evidence = Evidence.create(
            source_ids=("s1",),
            content="X",
            quality=Quality(0.9, 0.9, 0.9),
        )
        with pytest.raises(Exception):
            evidence.source_ids = ("s2",)  # type: ignore[misc]

    def test_cannot_modify_id(self) -> None:
        evidence = Evidence.create(
            source_ids=("s1",),
            content="X",
            quality=Quality(0.9, 0.9, 0.9),
        )
        with pytest.raises(Exception):
            evidence.id = "new_id"  # type: ignore[misc]


class TestEvidenceValidation:
    def test_no_source_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least one Source"):
            Evidence(
                id="ev-1",
                source_ids=(),
                content="No source.",
                quality=Quality(0.9, 0.9, 0.9),
            )

    def test_empty_content_rejected(self) -> None:
        with pytest.raises(ValueError, match="content is required"):
            Evidence(
                id="ev-1",
                source_ids=("s1",),
                content="",
                quality=Quality(0.9, 0.9, 0.9),
            )

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValueError):
            Evidence(
                id="",
                source_ids=("s1",),
                content="X",
                quality=Quality(0.9, 0.9, 0.9),
            )


class TestEvidenceCorrection:
    def test_correction_creates_new_evidence(self) -> None:
        original = Evidence.create(
            source_ids=("s1",),
            content="Original content.",
            quality=Quality(0.9, 0.9, 0.9),
        )
        corrected = original.with_correction("Corrected content.", "Source updated")
        assert corrected.id != original.id
        assert corrected.content == "Corrected content."
        # Original is unchanged
        assert original.content == "Original content."


class TestEvidenceNonRetrievable:
    def test_mark_non_retrievable_creates_new(self) -> None:
        evidence = Evidence.create(
            source_ids=("s1",),
            content="X",
            quality=Quality(0.9, 0.9, 0.9),
        )
        non_retrievable = evidence.mark_non_retrievable()
        assert non_retrievable.retrievable is False
        # Original is unchanged
        assert evidence.retrievable is True
        assert non_retrievable.id == evidence.id  # Same ID


class TestQualityValidation:
    def test_invalid_source_reliability(self) -> None:
        with pytest.raises(ValueError):
            Quality(source_reliability=1.1, content_completeness=0.9, retrieval_confidence=0.9)

    def test_invalid_content_completeness(self) -> None:
        with pytest.raises(ValueError):
            Quality(source_reliability=0.9, content_completeness=-0.1, retrieval_confidence=0.9)

    def test_invalid_retrieval_confidence(self) -> None:
        with pytest.raises(ValueError):
            Quality(source_reliability=0.9, content_completeness=0.9, retrieval_confidence=1.5)

    def test_boundary_values(self) -> None:
        q = Quality(source_reliability=0.0, content_completeness=1.0, retrieval_confidence=0.5)
        assert q.source_reliability == 0.0
        assert q.content_completeness == 1.0
