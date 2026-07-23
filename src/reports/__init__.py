"""
SIGNAL Reports — Phase 6.

This package implements report generation per the report template
(`13_report_template.md`) and the frozen Report Specification
(`docs/REPORT_SPECIFICATION.md`).

Phase 6 Checkpoint 1:
- models, utils, builder (Daily Brief), render (Daily Brief)

Phase 6 Checkpoint 2:
- WeeklyReviewBuilder + WeeklyReviewRenderer

Phase 6 Checkpoint 3:
- PerEntityBriefBuilder + PerEntityBriefRenderer

Phase 6 Checkpoint 4 (this checkpoint):
- JsonExporter — deterministic companion JSON format

Deferred:
- Markdown→HTML/PDF exporters, scheduling, notification, UI.
"""

from __future__ import annotations

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
from src.reports.render import DailyBriefRenderer
from src.reports.render_entity import PerEntityBriefRenderer
from src.reports.render_weekly import WeeklyReviewRenderer

__all__ = [
    "DailyBriefInputs",
    "DailyBriefRenderer",
    "EXPORT_REPORT_VERSION",
    "JsonExporter",
    "PerEntityBriefBuilder",
    "PerEntityBriefInputs",
    "PerEntityBriefRenderer",
    "REPORT_SCHEMA_VERSION",
    "Report",
    "ReportBuilder",
    "ReportKind",
    "ReportSection",
    "WeeklyReviewBuilder",
    "WeeklyReviewInputs",
    "WeeklyReviewRenderer",
]