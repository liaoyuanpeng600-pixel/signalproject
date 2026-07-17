#!/usr/bin/env python3
"""
One-off fix script: prepend ../ to relative .md links in ADR/*.md and RFC/*.md.

Bash one-liner was denied permission. This is the equivalent.
Idempotent: re-running has no effect.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Files that live in subdirectories and need ../ prefix.
TARGET_DIRS = [ROOT / "ADR", ROOT / "RFC"]

# Filenames that should get ../ prepended.
KNOWN_TOP_LEVEL = {
    "00_project_context.md", "01_signal_constitution.md",
    "02_agent_constitution.md", "03_workflow_constitution.md",
    "04_data_schema.md", "05_reasoning_framework.md",
    "06_scoring_framework.md", "07_prompt_guidelines.md",
    "08_architecture.md", "09_development_roadmap.md",
    "10_signal_taxonomy.md", "11_industry_mapping.md",
    "12_company_schema.md", "13_report_template.md",
    "14_watchlist.md",
    "INVARIANTS.md", "SPEC_VERSION.md", "GLOSSARY.md",
    "GOVERNANCE.md", "SCHEMA_EVOLUTION.md", "REVIEW_NOTES.md",
}

LINK_RE = re.compile(r"\]\(([^)]+)\)")

def fix_link(target: str) -> str:
    # Skip already-prefixed, external, or anchor-only.
    if target.startswith(("../", "http://", "https://", "mailto:", "#")):
        return target
    if "#" in target:
        file_part, anchor = target.split("#", 1)
    else:
        file_part, anchor = target, ""
    if file_part in KNOWN_TOP_LEVEL:
        file_part = "../" + file_part
    return file_part + (("#" + anchor) if anchor else "")

def fix_file(path: Path) -> int:
    text = path.read_text(encoding="utf-8")
    changes = 0
    def repl(m):
        nonlocal changes
        old = m.group(1)
        new = fix_link(old)
        if new != old:
            changes += 1
        return f"]({new})"
    # Skip links inside code fences.
    out = []
    in_fence = False
    fence_pat = re.compile(r"^```")
    for line in text.splitlines(keepends=True):
        if fence_pat.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        out.append(LINK_RE.sub(repl, line))
    new_text = "".join(out)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
    return changes

def main():
    total = 0
    for d in TARGET_DIRS:
        if not d.exists():
            continue
        for f in sorted(d.rglob("*.md")):
            n = fix_file(f)
            if n:
                print(f"{f.relative_to(ROOT)}: {n} links fixed")
                total += n
    print(f"Total: {total}")

if __name__ == "__main__":
    main()