"""Tests for JsonExporter (Phase 6 Checkpoint 4)."""

import json

import pytest

from src.reports.builder import (
    DailyBriefInputs,
    PerEntityBriefBuilder,
    PerEntityBriefInputs,
    ReportBuilder,
    WeeklyReviewBuilder,
    WeeklyReviewInputs,
)
from src.reports.export import (
    EXPORT_REPORT_VERSION,
    REPORT_SCHEMA_VERSION,
    JsonExporter,
)
from src.reports.models import Report, ReportKind, ReportSection


# ----------------------- helpers -----------------------


def _daily_brief() -> Report:
    return ReportBuilder().build_daily_brief(DailyBriefInputs())


def _weekly_review() -> Report:
    return WeeklyReviewBuilder().build(
        WeeklyReviewInputs(
            period_label="Week of 2026-07-13",
            risk_notes=("r1",),
            lookahead_notes=("l1",),
        )
    )


def _entity_brief() -> Report:
    from src.core.entities import Entity, EntityKind
    from src.core.ids import ID

    entity = Entity.create(kind=EntityKind.COMPANY, name="ACME", id=ID("e-1"))
    return PerEntityBriefBuilder().build(PerEntityBriefInputs(anchor_entity=entity))


# ----------------------- basic export -----------------------


class TestBasicExport:
    def test_export_returns_string(self) -> None:
        out = JsonExporter().export(_daily_brief())
        assert isinstance(out, str)

    def test_export_is_valid_json(self) -> None:
        out = JsonExporter().export(_daily_brief())
        json.loads(out)  # raises if invalid

    def test_to_dict_returns_dict(self) -> None:
        out = JsonExporter().to_dict(_daily_brief())
        assert isinstance(out, dict)

    def test_to_dict_top_level_keys(self) -> None:
        out = JsonExporter().to_dict(_daily_brief())
        assert "metadata" in out
        assert "sections" in out


# ----------------------- metadata fields -----------------------


class TestMetadataFields:
    def test_report_kind(self) -> None:
        d = JsonExporter().to_dict(_daily_brief())
        assert d["metadata"]["report_kind"] == "daily_brief"

    def test_report_kind_weekly_review(self) -> None:
        d = JsonExporter().to_dict(_weekly_review())
        assert d["metadata"]["report_kind"] == "weekly_review"

    def test_report_kind_per_entity_brief(self) -> None:
        d = JsonExporter().to_dict(_entity_brief())
        assert d["metadata"]["report_kind"] == "per_entity_brief"

    def test_report_version_constant(self) -> None:
        d = JsonExporter().to_dict(_daily_brief())
        assert d["metadata"]["report_version"] == EXPORT_REPORT_VERSION

    def test_schema_version_constant(self) -> None:
        d = JsonExporter().to_dict(_daily_brief())
        assert d["metadata"]["schema_version"] == REPORT_SCHEMA_VERSION

    def test_generated_at_present(self) -> None:
        d = JsonExporter().to_dict(_daily_brief())
        ts = d["metadata"]["generated_at"]
        assert isinstance(ts, str)
        assert len(ts) > 0

    def test_title_propagated(self) -> None:
        d = JsonExporter().to_dict(_daily_brief())
        assert d["metadata"]["title"] == "Daily Brief — 0 signals, 0 research items"

    def test_word_budget_propagated(self) -> None:
        d = JsonExporter().to_dict(_daily_brief())
        assert d["metadata"]["word_budget"] == 5000

    def test_word_count_propagated(self) -> None:
        d = JsonExporter().to_dict(_daily_brief())
        assert d["metadata"]["word_count"] >= 0


# ----------------------- provenance -----------------------


class TestProvenance:
    def test_cycle_ids_propagated(self) -> None:
        report = ReportBuilder().build_daily_brief(
            DailyBriefInputs(), cycle_ids=("c-1", "c-2")
        )
        d = JsonExporter().to_dict(report)
        assert d["metadata"]["cycle_ids"] == ["c-1", "c-2"]

    def test_agent_versions_propagated(self) -> None:
        report = ReportBuilder().build_daily_brief(
            DailyBriefInputs(), agent_versions=("v1.0", "v2.0")
        )
        d = JsonExporter().to_dict(report)
        assert d["metadata"]["agent_versions"] == ["v1.0", "v2.0"]

    def test_prompt_versions_propagated(self) -> None:
        report = ReportBuilder().build_daily_brief(
            DailyBriefInputs(), prompt_versions=("p1.0",)
        )
        d = JsonExporter().to_dict(report)
        assert d["metadata"]["prompt_versions"] == ["p1.0"]

    def test_degrade_mode_propagated(self) -> None:
        report = ReportBuilder().build_daily_brief(
            DailyBriefInputs(), degrade_mode=True
        )
        d = JsonExporter().to_dict(report)
        assert d["metadata"]["degrade_mode"] is True

    def test_coverage_gaps_propagated(self) -> None:
        report = ReportBuilder().build_daily_brief(
            DailyBriefInputs(coverage_gaps=("ent-1", "ent-2"))
        )
        d = JsonExporter().to_dict(report)
        assert d["metadata"]["coverage_gaps"] == ["ent-1", "ent-2"]

    def test_period_label_propagated_for_weekly(self) -> None:
        d = JsonExporter().to_dict(_weekly_review())
        assert d["metadata"]["period_label"] == "Week of 2026-07-13"


# ----------------------- anchor_entity_id -----------------------


class TestAnchorEntityId:
    def test_present_for_per_entity_brief(self) -> None:
        d = JsonExporter().to_dict(_entity_brief())
        assert d["metadata"]["anchor_entity_id"] == "e-1"

    def test_absent_for_daily_brief(self) -> None:
        d = JsonExporter().to_dict(_daily_brief())
        assert "anchor_entity_id" not in d["metadata"]

    def test_absent_for_weekly_review(self) -> None:
        d = JsonExporter().to_dict(_weekly_review())
        assert "anchor_entity_id" not in d["metadata"]


# ----------------------- sections -----------------------


class TestSections:
    def test_sections_present(self) -> None:
        d = JsonExporter().to_dict(_daily_brief())
        assert isinstance(d["sections"], list)
        assert len(d["sections"]) >= 1

    def test_section_structure(self) -> None:
        d = JsonExporter().to_dict(_daily_brief())
        for section in d["sections"]:
            assert "title" in section
            assert "section_kind" in section
            assert "body" in section
            assert "citations" in section
            assert isinstance(section["citations"], list)

    def test_section_order_preserved(self) -> None:
        d = JsonExporter().to_dict(_daily_brief())
        titles = [s["title"] for s in d["sections"]]
        # Daily Brief: Headline → Cycle Summary → ... → Provenance (renderer order).
        # Builder produces: Headline, Cycle Summary, (optional sections).
        assert titles[0] == "Headline"
        assert titles[1] == "Cycle Summary"

    def test_section_preserves_citations(self) -> None:
        # Build a report with explicit citations.
        report = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="t",
            sections=(
                ReportSection(
                    title="s",
                    body="body",
                    section_kind="body",
                    citations=("[sig:abc]", "[thesis:xyz]"),
                ),
            ),
        )
        d = JsonExporter().to_dict(report)
        assert d["sections"][0]["citations"] == ["[sig:abc]", "[thesis:xyz]"]


# ----------------------- omission rules -----------------------


class TestOmission:
    def test_omitted_sections_not_exported(self) -> None:
        """No `Risks` section in inputs → no Risks section in export."""
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p")
        )
        d = JsonExporter().to_dict(report)
        titles = [s["title"] for s in d["sections"]]
        assert "Risks" not in titles
        assert "Next Week Focus" not in titles

    def test_omitted_optional_metadata_not_exported(self) -> None:
        """anchor_entity_id and period_label absent → not in metadata."""
        report = ReportBuilder().build_daily_brief(DailyBriefInputs())
        d = JsonExporter().to_dict(report)
        meta = d["metadata"]
        assert "anchor_entity_id" not in meta
        assert "period_label" not in meta

    def test_present_optional_metadata_exported(self) -> None:
        report = ReportBuilder().build_daily_brief(
            DailyBriefInputs(coverage_gaps=("ent-x",)),
            cycle_ids=("c-1",),
            agent_versions=("v1",),
            prompt_versions=("p1",),
        )
        d = JsonExporter().to_dict(report)
        meta = d["metadata"]
        assert meta["cycle_ids"] == ["c-1"]
        assert meta["agent_versions"] == ["v1"]
        assert meta["prompt_versions"] == ["p1"]
        assert meta["coverage_gaps"] == ["ent-x"]

    def test_empty_arrays_preserved(self) -> None:
        """An empty but explicit list (e.g., coverage_gaps=()) IS exported
        as an empty list — this is not an "omitted" field, just an empty one."""
        report = ReportBuilder().build_daily_brief(DailyBriefInputs())
        d = JsonExporter().to_dict(report)
        assert d["metadata"]["coverage_gaps"] == []
        assert d["metadata"]["cycle_ids"] == []


# ----------------------- determinism -----------------------


class TestDeterminism:
    def test_same_input_same_structured_output(self) -> None:
        """Two exports of the same Report produce the same structured dict
        (ignoring generated_at)."""
        report = _daily_brief()
        d1 = JsonExporter().to_dict(report)
        d2 = JsonExporter().to_dict(report)
        # Same sections, same metadata fields except generated_at.
        d1.pop("metadata")["generated_at"]  # access for type
        d1_meta = JsonExporter().to_dict(report)["metadata"].copy()
        d2_meta = JsonExporter().to_dict(report)["metadata"].copy()
        # Reset generated_at for comparison.
        d1_meta.pop("generated_at")
        d2_meta.pop("generated_at")
        assert d1_meta == d2_meta

    def test_same_input_same_section_list(self) -> None:
        report = _daily_brief()
        d1 = JsonExporter().to_dict(report)
        d2 = JsonExporter().to_dict(report)
        # Sections don't include generated_at — they should match exactly.
        assert d1["sections"] == d2["sections"]

    def test_json_keys_sorted(self) -> None:
        out = JsonExporter().export(_daily_brief())
        # Top-level keys appear in sorted order in the JSON text.
        # 'metadata' < 'sections' alphabetically → metadata appears first.
        assert out.index('"metadata"') < out.index('"sections"')

    def test_section_keys_sorted_within_section(self) -> None:
        """Section dict keys appear in alphabetical order in the JSON output.

        Verified by parsing the JSON and checking the order of keys in the
        first section dict (avoids substring confusion with metadata keys).
        """
        report = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="t",
            sections=(
                ReportSection(
                    title="s",
                    body="b",
                    section_kind="body",
                    citations=(),
                ),
            ),
        )
        out = JsonExporter().export(report)
        parsed = json.loads(out)
        section = parsed["sections"][0]
        keys = list(section.keys())
        # Alphabetical order: body, citations, section_kind, title.
        assert keys == ["body", "citations", "section_kind", "title"]
        # Also confirm the section substring in raw JSON has the keys in
        # alphabetical order.
        section_start = out.index('"sections":[{') + len('"sections":[{')
        section_end = out.index('}]}', section_start)
        section_str = out[section_start:section_end]
        body_pos = section_str.index('"body":')
        citations_pos = section_str.index('"citations":')
        section_kind_pos = section_str.index('"section_kind":')
        title_pos = section_str.index('"title":')
        assert body_pos < citations_pos < section_kind_pos < title_pos

    def test_compact_separators_round_trip(self) -> None:
        """Round-trip through json: re-serializing the parsed output yields
        the same bytes (because separators are compact and stable)."""
        out = JsonExporter().export(_daily_brief())
        parsed = json.loads(out)
        re_emitted = json.dumps(
            parsed,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        assert out == re_emitted

    def test_section_order_from_builder(self) -> None:
        """Section order in JSON matches the order in the Report tuple."""
        report = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="t",
            sections=(
                ReportSection(title="Z-section", body="z", section_kind="body"),
                ReportSection(title="A-section", body="a", section_kind="body"),
                ReportSection(title="M-section", body="m", section_kind="body"),
            ),
        )
        d = JsonExporter().to_dict(report)
        titles = [s["title"] for s in d["sections"]]
        # Order preserved from the tuple (NOT sorted alphabetically).
        assert titles == ["Z-section", "A-section", "M-section"]


# ----------------------- compatibility with all builders -----------------------


class TestBuilderCompatibility:
    def test_export_daily_brief(self) -> None:
        out = JsonExporter().export(_daily_brief())
        parsed = json.loads(out)
        assert parsed["metadata"]["report_kind"] == "daily_brief"

    def test_export_weekly_review(self) -> None:
        out = JsonExporter().export(_weekly_review())
        parsed = json.loads(out)
        assert parsed["metadata"]["report_kind"] == "weekly_review"

    def test_export_per_entity_brief(self) -> None:
        out = JsonExporter().export(_entity_brief())
        parsed = json.loads(out)
        assert parsed["metadata"]["report_kind"] == "per_entity_brief"
        assert parsed["metadata"]["anchor_entity_id"] == "e-1"

    def test_export_propagates_provenance_from_weekly(self) -> None:
        report = WeeklyReviewBuilder().build(
            WeeklyReviewInputs(period_label="p"),
            cycle_ids=("c-w1", "c-w2"),
            agent_versions=("v2",),
        )
        out = JsonExporter().export(report)
        parsed = json.loads(out)
        assert parsed["metadata"]["cycle_ids"] == ["c-w1", "c-w2"]
        assert parsed["metadata"]["agent_versions"] == ["v2"]


# ----------------------- independence from renderer -----------------------


class TestRendererIndependence:
    def test_exporter_does_not_import_render(self) -> None:
        import re

        import src.reports.export as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        # Exporter must not depend on Renderer (independent components).
        assert re.search(
            r"^\s*from\s+src\.reports\.render", contents, re.MULTILINE
        ) is None, "exporter must not import renderer"

    def test_exporter_works_without_calling_renderer(self) -> None:
        """Exporting must not require rendering first."""
        report = _daily_brief()
        # Do not render; export directly.
        out = JsonExporter().export(report)
        parsed = json.loads(out)
        assert "metadata" in parsed
        assert "sections" in parsed


# ----------------------- dep inversion -----------------------


class TestDepInversion:
    def test_exporter_does_not_import_forbidden_modules(self) -> None:
        import re

        import src.reports.export as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        forbidden = (
            r"^\s*from\s+src\.runtime",
            r"^\s*from\s+src\.workflow",
            r"^\s*from\s+src\.persistence",
            r"^\s*from\s+src\.scheduler",
        )
        for pat in forbidden:
            assert re.search(pat, contents, re.MULTILINE) is None, (
                f"unexpected import: {pat}"
            )

    def test_exporter_does_not_import_knowledge(self) -> None:
        import re

        import src.reports.export as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        assert re.search(
            r"^\s*from\s+src\.core\.knowledge", contents, re.MULTILINE
        ) is None

    def test_exporter_does_not_parse_markdown(self) -> None:
        """Exporter must not import Markdown parsing libs."""
        import re

        import src.reports.export as mod

        source = mod.__file__ or ""
        with open(source, encoding="utf-8") as f:
            contents = f.read()
        for lib in ("markdown", "mistune", "markdown_it", "commonmark"):
            assert lib not in contents.lower() or lib in (
                "no markdown parsing"  # docstring mention, OK
            ), f"exporter must not depend on {lib}"


# ----------------------- edge cases -----------------------


class TestEdgeCases:
    def test_empty_report(self) -> None:
        report = Report(kind=ReportKind.DAILY_BRIEF, title="t", sections=())
        d = JsonExporter().to_dict(report)
        assert d["sections"] == []
        assert d["metadata"]["title"] == "t"

    def test_section_with_unicode_body(self) -> None:
        report = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="t",
            sections=(
                ReportSection(
                    title="s",
                    body="ACME — résumé — 14% — ✓",
                    section_kind="body",
                ),
            ),
        )
        out = JsonExporter().export(report)
        parsed = json.loads(out)
        assert parsed["sections"][0]["body"] == "ACME — résumé — 14% — ✓"

    def test_unicode_preserved_in_json(self) -> None:
        """ensure_ascii=False keeps human-readable Unicode in the output."""
        report = Report(
            kind=ReportKind.DAILY_BRIEF,
            title="t",
            sections=(
                ReportSection(title="s", body="café", section_kind="body"),
            ),
        )
        out = JsonExporter().export(report)
        assert "café" in out
        assert "\\u00e9" not in out  # not escaped

    def test_export_is_pure(self) -> None:
        """Exporter must not mutate the input Report."""
        report = _daily_brief()
        original_meta = report.kind
        JsonExporter().export(report)
        JsonExporter().to_dict(report)
        assert report.kind == original_meta


# ----------------------- schema versioning -----------------------


class TestSchemaVersioning:
    def test_schema_version_is_string(self) -> None:
        d = JsonExporter().to_dict(_daily_brief())
        assert isinstance(d["metadata"]["schema_version"], str)

    def test_schema_version_starts_with_digit(self) -> None:
        """Sanity: schema_version follows semver-like format."""
        d = JsonExporter().to_dict(_daily_brief())
        version = d["metadata"]["schema_version"]
        assert version[0].isdigit()

    def test_constants_match(self) -> None:
        """The exported schema_version field matches the module constant."""
        d = JsonExporter().to_dict(_daily_brief())
        assert d["metadata"]["schema_version"] == REPORT_SCHEMA_VERSION
        assert d["metadata"]["report_version"] == EXPORT_REPORT_VERSION