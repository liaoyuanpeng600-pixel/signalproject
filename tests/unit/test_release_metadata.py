"""Release metadata and public compatibility-surface checks."""

from __future__ import annotations

import re
from pathlib import Path

import src.workflow as workflow


ROOT = Path(__file__).parents[2]
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _project_value(name: str) -> str:
    match = re.search(rf'^{re.escape(name)}\s*=\s*"([^"]+)"$', PYPROJECT, re.MULTILINE)
    assert match is not None
    return match.group(1)


def test_release_version_has_single_authoritative_value() -> None:
    """The package release is intentionally independent of schema/spec versions."""
    assert _project_value("version") == "0.1.0"


def test_readme_release_version_matches_authoritative_metadata() -> None:
    assert f"Release version: **{_project_value('version')} (alpha)**." in README


def test_declared_python_floor_matches_used_runtime_features() -> None:
    assert _project_value("requires-python") == ">=3.10,<3.14"


def test_legacy_workflow_persistence_is_not_publicly_exported() -> None:
    assert "persistence" not in workflow.__all__
