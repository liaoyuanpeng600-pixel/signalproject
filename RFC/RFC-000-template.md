# RFC-NNN: <Title>

> **Status:** draft | reviewing | accepted | rejected | superseded | merged
> **Date:** YYYY-MM-DD
> **Author:** <name>
> **Reviewers:** <names, optional at draft>
> **Supersedes:** RFC-NNN (if applicable)
> **Superseded by:** RFC-NNN (if applicable)
> **Related ADRs:** ADR-NNN (if any)

---

## Summary

One-paragraph TL;DR of what this RFC proposes.

---

## Motivation

Why is this change needed? What problem does it solve? What use case is unserved today?

---

## Detailed Proposal

Describe the change precisely. Include:
- Affected documents (e.g., `02_agent_constitution.md`)
- Affected schemas (with current version)
- Affected invariants (with INV-N numbers)
- New or modified glossary terms
- Code examples (if applicable)

---

## Alternatives Considered

What other options were on the table? For each:
- Brief description
- Pros
- Cons
- Why rejected

---

## Trade-offs

What do we gain? What do we give up?

---

## Consequences

What becomes easier? What becomes harder? What new constraints do we accept?

---

## Backward Compatibility

Will existing consumers break? If yes, what's the migration path?

---

## Affected Documents

| Document | Change type |
|---|---|
| `00_*.md` | e.g., "add §X" |
| `02_*.md` | e.g., "add agent A9" |
| ... | ... |

---

## Affected Schemas

| Schema | Current version | Target version | Bump type |
|---|---|---|---|
| Signal | 1.0 | 1.1 | MINOR |
| ... | ... | ... | ... |

---

## Affected Invariants

- INV-N: how is it affected?
- INV-M: new? modified?

---

## SPEC_VERSION Impact

- **Current SPEC_VERSION:** X.Y.Z
- **Target SPEC_VERSION:** X.Y.Z (or MAJOR/MINOR bump)
- **Bump type:** MAJOR | MINOR | PATCH

---

## Glossary Impact

- New term: ?
- Modified term: ?
- Deprecated term: ?

---

## Migration Plan

If MAJOR: describe migration artifacts (`migrations/X_to_Y/`), shims, compatibility window.

If MINOR or PATCH: state "no migration required" or describe small migrations.

---

## Test Plan

How will this change be tested before merge?

- Unit tests: ?
- Integration tests: ?
- Calibration tests (if scoring changes): ?
- Lint pass: `scripts/lint_spec.py` must pass

---

## Open Questions

What is unresolved? What needs more discussion?

---

## References

- Related docs (with links)
- Related ADRs / RFCs
- External sources