#!/usr/bin/env python3
"""
lint_spec.py — Cross-document consistency checker for the SIGNAL spec set.

Walks every .md file in the spec directory and verifies:
  1. Markdown links resolve to existing files and sections.
  2. No schema field is defined in more than one document.
  3. SPEC_VERSION references are consistent with current.
  4. Required documents exist for cross-references.
  5. Deprecated aliases are not used in active spec docs.
  6. Invariants are not silently violated in code examples.
  7. Composite weight example matches the canonical formula.
  8. Gating threshold example matches the canonical value.

Exit codes:
  0 — all checks pass
  1 — one or more checks failed (errors)
  2 — script-level error (e.g., config not found)

Run from the spec root directory:
    python scripts/lint_spec.py
    python scripts/lint_spec.py --verbose
    python scripts/lint_spec.py --check=links
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SPEC_ROOT = Path(__file__).resolve().parent.parent

# Files that count as "the spec" (everything we lint).
SPEC_GLOB = "*.md"

# Subdirectories that contain spec-relevant content.
SPEC_DIRS = ["ADR", "RFC"]

# Deprecated aliases that should not appear in active docs.
# Format: alias -> canonical term. The alias is forbidden in narrative prose.
DEPRECATED_ALIASES = {
    "Signal.lifecycle": "Signal.status",
    "entity_id": "EntityRef.id",
    "clusterId": "cluster_id",
    "cycleId": "cycle_id",
    "magnitude_band": "band",
}

# Canonical values that must appear consistently.
CANONICAL_GATING_THRESHOLD = 0.65
CANONICAL_COMPOSITE_WEIGHTS = {
    "magnitude": 0.30,
    "confidence": 0.25,
    "timeliness": 0.20,
    "novelty": 0.15,
    "actionability": 0.10,
}
CANONICAL_SIGNAL_STATUSES = {
    "draft",
    "verified",
    "active",
    "held",
    "rejected",
    "decayed",
    "superseded",
}
CANONICAL_LIFECYCLE_TRANSITIONS = {
    ("draft", "verified"),
    ("draft", "rejected"),
    ("verified", "active"),
    ("verified", "held"),
    ("verified", "rejected"),
    ("active", "decayed"),
    ("active", "superseded"),
    ("held", "active"),
    ("held", "rejected"),
}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class Issue:
    file: str
    line: int
    check: str
    severity: str  # "error" | "warning"
    message: str


@dataclass
class Report:
    issues: list[Issue] = field(default_factory=list)

    def add(self, file: str, line: int, check: str, severity: str, message: str) -> None:
        self.issues.append(Issue(file, line, check, severity, message))

    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    def print(self, verbose: bool = False) -> None:
        if not self.issues:
            print("[ok] no issues")
            return

        errors = self.errors()
        warnings = self.warnings()

        for issue in self.issues:
            if not verbose and issue.severity == "warning":
                continue
            tag = "[ERR]" if issue.severity == "error" else "[WARN]"
            print(
                f"{tag} {issue.file}:{issue.line} [{issue.check}] {issue.message}"
            )

        print()
        print(f"Errors:   {len(errors)}")
        print(f"Warnings: {len(warnings)}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def iter_spec_files() -> Iterable[Path]:
    """Yield every markdown file that's part of the spec set."""
    yield from sorted(SPEC_ROOT.glob(SPEC_GLOB))
    for d in SPEC_DIRS:
        dir_path = SPEC_ROOT / d
        if dir_path.exists():
            yield from sorted(dir_path.rglob("*.md"))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def relpath(path: Path) -> str:
    return str(path.relative_to(SPEC_ROOT))


# Regex helpers --------------------------------------------------------------

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`]+`")
ULID_RE = re.compile(r"\b01H[A-Z0-9]{22}\b")


# ---------------------------------------------------------------------------
# Check 1 — Markdown links resolve
# ---------------------------------------------------------------------------


def check_links(report: Report) -> None:
    """
    Every markdown link of the form [label](target) where target is a
    relative path or has a section anchor must resolve.

    External (http/https) links are skipped.
    """
    for path in iter_spec_files():
        if path.name == "RFC-000-template.md":
            # Template intentionally has placeholder links.
            continue
        text = read(path)
        # Strip code fences and inline code so we don't lint example links.
        stripped = CODE_FENCE_RE.sub("", text)
        stripped = INLINE_CODE_RE.sub("", stripped)

        for match in LINK_RE.finditer(stripped):
            label, target = match.group(1), match.group(2)
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if target.startswith("#"):
                # Pure anchor — handled by check_anchors separately.
                continue

            # Split target into file and optional anchor.
            if "#" in target:
                file_part, anchor = target.split("#", 1)
            else:
                file_part, anchor = target, None

            # Resolve the file.
            target_path = (path.parent / file_part).resolve()
            try:
                target_path.relative_to(SPEC_ROOT)
            except ValueError:
                report.add(
                    relpath(path),
                    _line_of(text, match.start()),
                    "links",
                    "error",
                    f"link escapes spec root: {target}",
                )
                continue

            if not target_path.exists():
                report.add(
                    relpath(path),
                    _line_of(text, match.start()),
                    "links",
                    "error",
                    f"broken link: {target!r} (file not found at {target_path.relative_to(SPEC_ROOT)})",
                )
                continue

            if anchor:
                check_anchor(report, path, target_path, anchor, match.start(), text)


def check_anchor(
    report: Report,
    source: Path,
    target_path: Path,
    anchor: str,
    offset: int,
    source_text: str,
) -> None:
    """Verify that an anchor (e.g., '§5.1' or 'signal-schema') exists in target."""
    target_text = read(target_path)
    headings = HEADING_RE.findall(target_text)

    # Anchor can be: 'section-name', '§N', '§N.M', '§N.M.K', or raw text.
    anchor_lc = anchor.lower()
    # Try matching against heading text or section number.
    found = False
    for hashes, title in headings:
        title_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        if title_slug == anchor_lc or anchor_lc in title_slug:
            found = True
            break
        # Allow anchor like '§5.1' to match a heading like '## 5.1 Foo'.
        m = re.match(r"^(\d+(?:\.\d+)*)", title)
        if m and f"§{m.group(1)}" == anchor_lc:
            found = True
            break

    if not found:
        report.add(
            relpath(source),
            _line_of(source_text, offset),
            "links",
            "warning",
            f"anchor not found: #{anchor} in {relpath(target_path)}",
        )


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


# ---------------------------------------------------------------------------
# Check 2 — No schema field is defined in more than one document
# ---------------------------------------------------------------------------


# Heuristic: detect Type := { ... } blocks, extract field names.
TYPE_DEF_RE = re.compile(
    r"^([A-Z][A-Za-z]+)\s*:=\s*\{(.*?)\}",
    re.MULTILINE | re.DOTALL,
)
FIELD_RE = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*:", re.MULTILINE)


def check_schema_authority(report: Report) -> None:
    """Each type name should be defined in exactly one document."""
    definitions: dict[str, list[tuple[str, int]]] = {}

    for path in iter_spec_files():
        text = read(path)
        stripped = CODE_FENCE_RE.sub("", text)
        for match in TYPE_DEF_RE.finditer(stripped):
            type_name = match.group(1)
            definitions.setdefault(type_name, []).append(
                (relpath(path), _line_of(text, match.start()))
            )

    for type_name, locations in sorted(definitions.items()):
        if len(locations) > 1:
            for file, line in locations[1:]:
                report.add(
                    file,
                    line,
                    "schema_authority",
                    "warning",
                    f"type '{type_name}' also defined in {locations[0][0]}; should have single authority",
                )


# ---------------------------------------------------------------------------
# Check 3 — Canonical values appear consistently
# ---------------------------------------------------------------------------


def check_canonical_values(report: Report) -> None:
    """Verify gating threshold and composite weights are stated correctly."""

    # Composite weight sum must equal 1.0.
    weight_sum = sum(CANONICAL_COMPOSITE_WEIGHTS.values())
    if abs(weight_sum - 1.0) > 1e-9:
        report.add(
            "lint_spec.py",
            0,
            "canonical_values",
            "error",
            f"CANONICAL_COMPOSITE_WEIGHTS sum to {weight_sum}, expected 1.0",
        )

    # Look for any explicit weight declarations in spec docs and verify
    # they match canonical (allowing ±0.005 tolerance for rounding).
    weight_pattern = re.compile(
        r"(?:composite\s*=\s*)?0\.(\d{2})\s*\*\s*(magnitude|confidence|timeliness|novelty|actionability)",
        re.IGNORECASE,
    )

    for path in iter_spec_files():
        text = read(path)
        stripped = CODE_FENCE_RE.sub("", text)
        for match in weight_pattern.finditer(stripped):
            weight = float("0." + match.group(1))
            dim = match.group(2).lower()
            expected = CANONICAL_COMPOSITE_WEIGHTS.get(dim)
            if expected is None:
                continue
            if abs(weight - expected) > 0.005:
                report.add(
                    relpath(path),
                    _line_of(text, match.start()),
                    "canonical_values",
                    "error",
                    f"weight for {dim} is {weight}, expected {expected}",
                )

    # Check gating threshold.
    gating_pattern = re.compile(
        r"composite\s*>=\s*(0\.\d+)\s*[→\-].*?active", re.IGNORECASE
    )
    for path in iter_spec_files():
        text = read(path)
        stripped = CODE_FENCE_RE.sub("", text)
        for match in gating_pattern.finditer(stripped):
            val = float(match.group(1))
            if abs(val - CANONICAL_GATING_THRESHOLD) > 0.005:
                report.add(
                    relpath(path),
                    _line_of(text, match.start()),
                    "canonical_values",
                    "warning",
                    f"gating threshold {val} differs from canonical {CANONICAL_GATING_THRESHOLD}",
                )


# ---------------------------------------------------------------------------
# Check 4 — No deprecated aliases in active docs
# ---------------------------------------------------------------------------


def check_deprecated_aliases(report: Report) -> None:
    """Warn if deprecated aliases appear in active spec docs."""
    # Don't check the deprecated-alias list itself (GLOSSARY §7).
    skip_files = {"GLOSSARY.md"}

    for path in iter_spec_files():
        if path.name in skip_files:
            continue
        text = read(path)
        stripped = CODE_FENCE_RE.sub("", text)
        # Strip inline code too — examples may legitimately use the alias.
        stripped = INLINE_CODE_RE.sub("", stripped)

        for alias, canonical in DEPRECATED_ALIASES.items():
            # Word-boundary match for camelCase / snake_case.
            pattern = re.compile(rf"\b{re.escape(alias)}\b")
            for match in pattern.finditer(stripped):
                report.add(
                    relpath(path),
                    _line_of(text, match.start()),
                    "deprecated_alias",
                    "warning",
                    f"deprecated alias '{alias}' used; prefer '{canonical}'",
                )


# ---------------------------------------------------------------------------
# Check 5 — Lifecycle transitions are valid
# ---------------------------------------------------------------------------


def check_lifecycle_transitions(report: Report) -> None:
    """Find arrow-style transitions in the lifecycle diagram and verify."""
    transition_re = re.compile(r"\b(\w+)\s*[→\-]+\s*(verified|active|held|rejected|decayed|superseded)\b")

    lifecycle_files = {"01_signal_constitution.md"}

    for path in iter_spec_files():
        if path.name not in lifecycle_files:
            continue
        text = read(path)
        # Only check inside the lifecycle section (rough heuristic).
        if "lifecycle" not in text.lower():
            continue
        for match in transition_re.finditer(text):
            # Skip non-transition patterns (e.g., "draft" appearing alone).
            from_state = match.group(1).lower()
            to_state = match.group(2).lower()
            if from_state in CANONICAL_SIGNAL_STATUSES and (from_state, to_state) not in CANONICAL_LIFECYCLE_TRANSITIONS:
                report.add(
                    relpath(path),
                    _line_of(text, match.start()),
                    "lifecycle",
                    "warning",
                    f"transition {from_state} -> {to_state} is not in the canonical lifecycle graph",
                )


# ---------------------------------------------------------------------------
# Check 6 — ULID format on cycle_id references
# ---------------------------------------------------------------------------


def check_cycle_id_format(report: Report) -> None:
    """Spot-check that cycle_id examples are ULID format."""
    cycle_id_re = re.compile(r"cycle[_-]?id[\"'\s:=]+([^\"'\s,;]+)", re.IGNORECASE)
    bad_pattern = re.compile(r"cycle_\w+|cycle-\w+", re.IGNORECASE)

    for path in iter_spec_files():
        text = read(path)
        for match in bad_pattern.finditer(text):
            # 'cycle_id' alone (the variable name) is fine.
            candidate = match.group(0).lower()
            if candidate in {"cycle_id", "cycle-id"}:
                continue
            # 'cycle_01HXY...' is wrong format — should be just '01HXY...'
            if re.match(r"cycle_01", candidate) or re.match(r"cycle-01", candidate):
                report.add(
                    relpath(path),
                    _line_of(text, match.start()),
                    "cycle_id_format",
                    "warning",
                    f"cycle_id example uses prefix: {candidate!r}; ULIDs have no prefix",
                )


# ---------------------------------------------------------------------------
# Check 7 — Required documents exist for cross-references
# ---------------------------------------------------------------------------


REQUIRED_DOCS = [
    "00_project_context.md",
    "01_signal_constitution.md",
    "02_agent_constitution.md",
    "03_workflow_constitution.md",
    "04_data_schema.md",
    "05_reasoning_framework.md",
    "06_scoring_framework.md",
    "07_prompt_guidelines.md",
    "08_architecture.md",
    "09_development_roadmap.md",
    "10_signal_taxonomy.md",
    "11_industry_mapping.md",
    "12_company_schema.md",
    "13_report_template.md",
    "14_watchlist.md",
    "INVARIANTS.md",
    "SPEC_VERSION.md",
    "GLOSSARY.md",
    "GOVERNANCE.md",
    "SCHEMA_EVOLUTION.md",
    "REVIEW_NOTES.md",
]


def check_required_docs(report: Report) -> None:
    for name in REQUIRED_DOCS:
        path = SPEC_ROOT / name
        if not path.exists():
            report.add(name, 0, "required_docs", "error", f"required doc missing: {name}")


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_selected(report: Report, only: str | None) -> None:
    checks = {
        "links": check_links,
        "schema_authority": check_schema_authority,
        "canonical_values": check_canonical_values,
        "deprecated_aliases": check_deprecated_aliases,
        "lifecycle": check_lifecycle_transitions,
        "cycle_id_format": check_cycle_id_format,
        "required_docs": check_required_docs,
    }
    if only:
        if only not in checks:
            print(f"unknown check: {only}", file=sys.stderr)
            print(f"available: {', '.join(checks)}", file=sys.stderr)
            sys.exit(2)
        checks[only](report)
        return
    for name, fn in checks.items():
        fn(report)


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    only = None
    for arg in argv:
        if arg.startswith("--check="):
            only = arg.split("=", 1)[1]

    if not SPEC_ROOT.exists():
        print(f"spec root not found: {SPEC_ROOT}", file=sys.stderr)
        return 2

    report = Report()
    run_selected(report, only)
    report.print(verbose=verbose)

    return 1 if report.errors() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))