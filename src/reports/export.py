"""
JSON Exporter — Phase 6 Checkpoint 4.

`JsonExporter` serializes a `Report` object to deterministic JSON.

Companion format per `docs/REPORT_SPECIFICATION.md`. The JSON exporter
parses no Markdown — it exports the structured Report domain model
directly. The Renderer and Exporter are independent; either may be used
without the other.

Determinism contract:
- Stable key ordering (JSON keys are sorted alphabetically).
- Section ordering matches the canonical order in REPORT_SPECIFICATION.md
  §3.1 (preserved from the Builder's section tuple).
- Omitted sections are NOT emitted as empty placeholders.
- Timestamps (`generated_at`) are recorded at export time as part of
  the metadata; their value is not part of the deterministic contract
  (the value depends on when export is called, not on Report contents).

Metadata schema (top-level fields):
- report_kind: ReportKind.value
- report_version: exporter version
- generated_at: ISO8601 UTC
- schema_version: report structure schema version
- anchor_entity_id: optional; present iff Report.anchor_entity_id is set
- cycle_ids: tuple[str, ...]
- agent_versions: tuple[str, ...]
- prompt_versions: tuple[str, ...]
- degrade_mode: bool
- coverage_gaps: tuple[str, ...]
- period_label: optional
- word_budget: int
- word_count: int
- title: str
- sections: list of structured section dicts (in canonical order)

Section structure (per section in sections):
- title: str
- section_kind: str
- body: str
- citations: list[str]

Dependency rules:
- Depends only on `reports.models`.
- Does NOT import runtime, workflow, persistence, scheduler, network,
  CLI, or LLMs.
- No Markdown parsing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.core.timestamps import now_utc
from src.reports.models import Report

# Exporter / report schema versions. Bump on breaking changes.
EXPORT_REPORT_VERSION = "1.0"
REPORT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class JsonExporter:
    """Deterministic JSON exporter for `Report` objects.

    The exporter holds no mutable state. Call `export(report)` to obtain
    the JSON string, or `to_dict(report)` for the structured dict.
    """

    def to_dict(self, report: Report) -> dict[str, object]:
        """Convert a Report to a JSON-serializable dict.

        Sections are emitted in the canonical order defined by the
        Builder (and preserved in the Report's `sections` tuple).
        """
        metadata: dict[str, object] = {
            "report_kind": report.kind.value,
            "report_version": EXPORT_REPORT_VERSION,
            "schema_version": REPORT_SCHEMA_VERSION,
            "generated_at": now_utc(),
            "cycle_ids": list(report.cycle_ids),
            "agent_versions": list(report.agent_versions),
            "prompt_versions": list(report.prompt_versions),
            "degrade_mode": report.degrade_mode,
            "coverage_gaps": list(report.coverage_gaps),
            "word_budget": report.word_budget,
            "word_count": report.word_count,
            "title": report.title,
        }
        # Optional fields: include only when set (per spec, no empty
        # placeholders for omitted sections / fields).
        if report.anchor_entity_id is not None:
            metadata["anchor_entity_id"] = report.anchor_entity_id
        if report.period_label is not None:
            metadata["period_label"] = report.period_label

        sections: list[dict[str, object]] = []
        for section in report.sections:
            sections.append(
                {
                    "title": section.title,
                    "section_kind": section.section_kind,
                    "body": section.body,
                    "citations": list(section.citations),
                }
            )

        return {
            "metadata": metadata,
            "sections": sections,
        }

    def export(self, report: Report) -> str:
        """Serialize a Report to a deterministic JSON string.

        Determinism properties:
        - `sort_keys=True` ensures stable key ordering across runs.
        - `ensure_ascii=False` keeps human-readable unicode.
        - `separators=(",", ":")` produces compact, stable whitespace.
        - Section order is preserved from `report.sections` (Builder
          provides the canonical order).
        - List-of-tuples fields (`cycle_ids`, `agent_versions`, etc.)
          are emitted as JSON lists in tuple order.
        """
        payload = self.to_dict(report)
        return json.dumps(
            payload,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )


__all__ = [
    "EXPORT_REPORT_VERSION",
    "JsonExporter",
    "REPORT_SCHEMA_VERSION",
]