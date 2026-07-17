# SPEC_VERSION — Global Specification Versioning

> **Document role:** Defines the global versioning scheme for the entire SIGNAL specification set, the per-schema versioning rules, and the migration policy. Authoritative for any version number that appears in the spec set.
>
> Read alongside: [INVARIANTS.md](INVARIANTS.md), [SCHEMA_EVOLUTION.md](SCHEMA_EVOLUTION.md), [00_project_context.md](00_project_context.md).

---

## 1. Three Version Layers

The SIGNAL spec uses **three independent version layers**, each with its own rules:

| Layer | Format | Lives in | Authority |
|---|---|---|---|
| **SPEC_VERSION** | `MAJOR.MINOR.PATCH` | This document header + every doc's "Required versions" line | This document |
| **Document version** | `MAJOR.MINOR` (no PATCH) | Each document's version footer | The document itself |
| **Schema version** | `MAJOR.MINOR.PATCH` | Each schema's header in [04_data_schema.md](04_data_schema.md) | The schema definition |

Why three layers?

- **SPEC_VERSION** lets external consumers (downstream teams, partners) say "we're compatible with SPEC_VERSION X.Y."
- **Document version** is internal; tracks the maturity of each individual document.
- **Schema version** is wire-level; what an agent reads/writes must conform to a specific schema version.

---

## 2. Current SPEC_VERSION

> **SPEC_VERSION: 1.3.0** (as of 2026-07-16)

This represents the third revision of the spec set after the consistency pass ([REVIEW_NOTES.md](REVIEW_NOTES.md)). All documents are at version 0.1 or higher; all schemas are at 1.0 or 1.1.

### 2.1 Document and Schema Versions

| Document / Schema | Version | Notes |
|---|---|---|
| SPEC_VERSION | 1.3.0 | This document |
| `00_project_context.md` | 0.3 |  |
| `01_signal_constitution.md` | 0.2 |  |
| `02_agent_constitution.md` | 0.2 |  |
| `03_workflow_constitution.md` | 0.2 |  |
| `04_data_schema.md` | 1.1 | All schemas at 1.0+ |
| `05_reasoning_framework.md` | 0.1 |  |
| `06_scoring_framework.md` | 0.2 |  |
| `07_prompt_guidelines.md` | 0.1 |  |
| `08_architecture.md` | 0.2 |  |
| `09_development_roadmap.md` | 0.2 |  |
| `10_signal_taxonomy.md` | 0.1 |  |
| `11_industry_mapping.md` | 0.1 |  |
| `12_company_schema.md` | 0.1 |  |
| `13_report_template.md` | 0.1 |  |
| `14_watchlist.md` | 0.1 |  |
| `INVARIANTS.md` | 1.0 | New in this release |
| `GLOSSARY.md` | 1.0 | New in this release |
| `GOVERNANCE.md` | 1.0 | New in this release |
| `SCHEMA_EVOLUTION.md` | 1.0 | New in this release |
| `REVIEW_NOTES.md` | 1.0 | Existing |
| Schemas (Signal, Evidence, Provenance, Score, Reasoning, Metadata, etc.) | 1.0 / 1.1 | Per [04 §13](04_data_schema.md) |

---

## 3. SPEC_VERSION Semver Rules

The SPEC_VERSION follows strict semver:

### 3.1 MAJOR (X.0.0)

A SPEC_VERSION MAJOR bump is required when **any** of:

1. Any invariant ([INVARIANTS.md](INVARIANTS.md)) is added, removed, or changed.
2. Any schema's MAJOR bumps (per [SCHEMA_EVOLUTION.md §3](SCHEMA_EVOLUTION.md)).
3. Any agent's input/output contract changes in a breaking way (per [02 §6](02_agent_constitution.md)).
4. Any cross-cutting policy (P1–P9 in [00 §2](00_project_context.md)) changes.

External consumers **must** revalidate against the new SPEC_VERSION.

### 3.2 MINOR (0.X.0)

A SPEC_VERSION MINOR bump is required when **any** of:

1. A new document is added (e.g., `INVARIANTS.md` in 1.3.0).
2. A new agent is added.
3. A new schema is added.
4. A new signal type is added ([10 §6](10_signal_taxonomy.md)).
5. Backward-compatible enhancements.

External consumers can opt in; old version remains supported per migration window (§5).

### 3.3 PATCH (0.0.X)

A SPEC_VERSION PATCH bump is required when **any** of:

1. Typos, clarifications, examples.
2. Internal-only documentation fixes.
3. New edge cases documented.
4. Performance notes that don't change contracts.

External consumers do not need to act.

---

## 4. Schema Version Semver Rules

Per-schema versioning is stricter (wire-level). Rules live in [SCHEMA_EVOLUTION.md](SCHEMA_EVOLUTION.md); summarized here:

| Change | Version bump | Examples |
|---|---|---|
| Add optional field | MINOR | `+ new_optional_field` |
| Add required field with default | MINOR | `+ required_field_with_default` |
| Add enum value | MINOR | `+ enum_member` |
| Remove optional field | MAJOR | `- optional_field` |
| Remove required field | MAJOR | `- required_field` |
| Change field type | MAJOR | `string → int` |
| Rename field | MAJOR (treat as remove + add) |  |
| Tighten validation | MAJOR | `int → enum` |
| Add enum constraint to existing field | MAJOR | `string → enum[A,B,C]` |
| Make field required (was optional) | MAJOR | `?X → X` |
| Make field optional (was required) | MINOR | `X → ?X` |

---

## 5. Migration Policy

When a MAJOR bump happens, a migration path is mandatory.

### 5.1 Migration Window

| Change scope | Window |
|---|---|
| Schema MAJOR bump | Old version supported **90 days** after new version's release |
| SPEC_VERSION MAJOR bump | Old version supported **180 days** |
| Workflow/Agent breaking change | Old version supported **90 days** |

After the window, the old version is **archived** (kept in git history; not in active spec folder).

### 5.2 Migration Artifacts

A MAJOR bump produces:

| Artifact | Location | Required? |
|---|---|---|
| Migration code | `migrations/<from_version>_to_<to_version>/` | Yes |
| Migration log entry | [09_development_roadmap.md §11](09_development_roadmap.md) | Yes |
| Migration ADR | `ADR/ADR-NNN-<migration-name>.md` | Yes (if non-trivial) |
| Compatibility shim | Wherever old contracts are read | Yes (during window) |
| Deprecation notice | Affected docs' header | Yes |

### 5.3 Compatibility Shims

During the migration window:

- The pipeline can be configured to **read** either the old or new schema version.
- The pipeline **writes** the new schema version.
- Old-version data is upgraded on read by a shim function.

Shims live in `migrations/<v>/shim.py`. Each shim is itself versioned and tested.

### 5.4 Backward-Compatibility Promise

While a MAJOR version is in its migration window:
- New data MUST validate against both old and new schemas (via shim).
- Old data MUST validate against the new schema (via upgrade shim).
- A reader requesting old format gets old format.
- A writer always writes new format.

After the window: only the new schema is supported.

---

## 6. Version Dependency Matrix

Documents declare their required versions in their headers (e.g., "Requires: `00_project_context.md ≥ 0.2`"). The matrix below lists the maximum required version of each document under the current SPEC_VERSION.

| Document | Requires minimum |
|---|---|
| 01 | `00 ≥ 0.2` |
| 02 | `00 ≥ 0.2`, `01 ≥ 0.2` |
| 03 | `00 ≥ 0.2`, `01 ≥ 0.2`, `02 ≥ 0.2` |
| 04 | `00 ≥ 0.2`, `01 ≥ 0.2` |
| 05 | `00 ≥ 0.2`, `01 ≥ 0.2`, `02 ≥ 0.2`, `04 ≥ 1.0` |
| 06 | `00 ≥ 0.2`, `01 ≥ 0.2`, `02 ≥ 0.2`, `04 ≥ 1.0`, `05 ≥ 0.1` |
| 07 | `00 ≥ 0.2`, `02 ≥ 0.2` |
| 08 | `00 ≥ 0.2`, `02 ≥ 0.2`, `03 ≥ 0.2`, `04 ≥ 1.0` |
| 09 | `00 ≥ 0.2` |
| 10 | `00 ≥ 0.2`, `01 ≥ 0.2`, `04 ≥ 1.0` |
| 11 | `00 ≥ 0.2`, `04 ≥ 1.0`, `12 ≥ 0.1` |
| 12 | `00 ≥ 0.2`, `04 ≥ 1.0`, `11 ≥ 0.1` |
| 13 | `00 ≥ 0.2`, `01 ≥ 0.2`, `04 ≥ 1.0` |
| 14 | `00 ≥ 0.2`, `02 ≥ 0.2`, `12 ≥ 0.1` |

A `lint_spec.py` rule (`check_version_matrix`) verifies the actual declarations match this matrix.

---

## 7. Bumping SPEC_VERSION

To bump SPEC_VERSION:

1. Identify the bump type (MAJOR / MINOR / PATCH) per §3.
2. For MAJOR: write an RFC per [GOVERNANCE.md §2](GOVERNANCE.md).
3. For MINOR or PATCH: an ADR is sufficient.
4. Update this document's §2 (Current SPEC_VERSION).
5. Update affected documents' headers and footers.
6. Add migration artifacts if MAJOR.
7. Run `lint_spec.py` — must pass.
8. Update [09 §11 Migration Log](09_development_roadmap.md).

---

## 8. What "Compatible" Means

When downstream code says "we support SPEC_VERSION X.Y", it means:

- The code can read artifacts produced by SPEC_VERSION X.Y.
- The code does NOT need to be re-validated for X.Y.PATCH bumps.
- The code DOES need to be re-validated for X.MINOR or X+1.0 bumps.

If downstream code requires `> X.Y.Z` (strict), it means it cannot read older versions. If it requires `>= X.Y.Z`, it accepts everything since.

---

## 9. Version History

| SPEC_VERSION | Date | Summary |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold |
| 0.2 | 2026-07-16 | Engineering reference expansion |
| 1.0 | 2026-07-16 | First complete spec set; all 15 documents at version ≥ 0.1; all schemas at 1.0 |
| 1.1 | 2026-07-16 | Consistency pass: gating threshold unified, lifecycle enum complete, OverrideRecord expanded ([REVIEW_NOTES.md](REVIEW_NOTES.md)) |
| 1.2 | 2026-07-16 | Pipeline stage count aligned; missing references added |
| 1.3 | 2026-07-16 | Governance layer: INVARIANTS, GLOSSARY, GOVERNANCE, SCHEMA_EVOLUTION, ADR + RFC processes, lint_spec.py |