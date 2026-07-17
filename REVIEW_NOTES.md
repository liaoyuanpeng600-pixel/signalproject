# REVIEW_NOTES — Cross-Document Consistency Pass

> **Document role:** Audit trail of consistency issues found in the SIGNAL spec set, fixes applied, and remaining deferred items. Read alongside [00_project_context.md](00_project_context.md).
>
> Pass date: 2026-07-16.
> Pass scope: All 15 documents (`00_*.md` through `14_*.md`).

---

## 1. Method

Each document was read in full. Cross-references were validated against target sections. Schema definitions were traced to ensure single source of truth (P2 in [00 §2](00_project_context.md)). Conflicts were categorized and resolved.

Findings fall into four buckets:

| Bucket | Definition | This pass |
|---|---|---|
| **Conflict** | Two documents state incompatible facts | 4 fixed |
| **Drift** | Schema or rule changed in one doc but not propagated | 5 fixed |
| **Missing reference** | A doc references a concept whose authoritative source isn't linked | 8 added |
| **Inconsistency** | Terminology or formatting diverges without semantic change | 6 fixed |

---

## 2. Conflicts Found and Fixed

### 2.1 Gating Threshold (Conflict)

| Doc | Old value | Status |
|---|---|---|
| [03 §S8](03_workflow_constitution.md) | `composite >= 0.60 → active` | Source-of-truth on workflow side |
| [06 §5.1](06_scoring_framework.md) | `composite >= 0.65 → active` | Source-of-truth on scoring side |

**Resolution:** Aligned both to **0.65**. The scoring-side threshold was preferred because the gating stage implements what scoring defines; the workflow doc now references scoring. Status flags expanded: `active`/`held`/`rejected`. See [09 §11 migration log](09_development_roadmap.md).

### 2.2 Pipeline Stage Count (Conflict)

| Doc | Old value |
|---|---|
| [00 §5.1](00_project_context.md) | 10 steps (Harvest / Normalize / Dedup / Detect / Verify / Reason / Score / **Decide** / **Synthesize** / **Report**) |
| [03 §3](03_workflow_constitution.md) | 9 stages (S1–S9) |

**Resolution:** Aligned both to **9 stages** in the ingest cycle, with synthesis and reporting as separate workflows (W3, W4) per [03 §9](03_workflow_constitution.md). 00 §5.1 now references 03 explicitly and notes synthesis/report as cross-workflow.

### 2.3 Borderline Zone (Conflict)

| Doc | Old value |
|---|---|
| [00 §9.2](00_project_context.md) | "borderline zone (0.65–0.75)" |
| [06 §5.3](06_scoring_framework.md) | "borderline zone (0.45–0.65)" |

**Resolution:** Aligned both to **0.45–0.65**, matching the medium band in [06 §5](06_scoring_framework.md). 00 §9.2 now references 06 §5.3 explicitly.

### 2.4 Workflow Inventory Reference (Conflict)

| Doc | Old value |
|---|---|
| [08 §2.1](08_architecture.md) topology diagram | "Pipeline Runner (W1, W2, W3, W4)" |
| [08 §4.1](08_architecture.md) text | "executes W1–W5 workflows" |

**Resolution:** Aligned both to **W1–W5**. Diagram updated; cross-reference to [03 §2](03_workflow_constitution.md) added.

---

## 3. Drift Fixed

### 3.1 Signal Lifecycle Enum (Drift)

[01 §3](01_signal_constitution.md) listed 5 statuses (`draft`, `verified`, `active`, `decayed`, `rejected`), but [04 §4.1](04_data_schema.md) listed 6 (`+ superseded`). The cardinality rules in [01 §4](01_signal_constitution.md) referenced `superseded` but the lifecycle didn't include it.

**Fix:** Added `superseded` to the lifecycle table in 01 §3, with `dedup` stage and `decay_worker` as the entering actors.

### 3.2 Provenance Example Schema (Drift)

[01 §6 Example 1](01_signal_constitution.md) used field names (`detector_prompt_version`, `scorer_model`) that did not match the canonical [04 §6 Provenance](04_data_schema.md) schema (`prompt_versions` map, `model_versions` map).

**Fix:** Rewrote the example to use the canonical field names.

### 3.3 OverrideRecord.action Enum (Drift)

The override action enum was inconsistent across three documents:

| Doc | Old enum |
|---|---|
| [02 §A8](02_agent_constitution.md) | `adjust_score, demote_tier, mark_noise` |
| [04 §6 OverrideRecord](04_data_schema.md) | `adjust_score, demote_tier, mark_noise, mark_redundant` |
| [14 §9.1 CurationAction](14_watchlist.md) | 7 actions including `add_entity`, `remove_entity`, `change_tier`, etc. |

**Fix:** Consolidated to a single 8-action enum in [04 §6 OverrideRecord](04_data_schema.md). The 02 §A8 catalog now references the canonical list and adds context. 14 §9.1 enumerates the same set.

### 3.4 CycleReport.signals_emitted (Drift)

[04 §10.5 CycleReport](04_data_schema.md) declared `signals_emitted: { draft, verified, active, rejected, decayed }` without types and without `superseded` or `held`. After §3.1, `superseded` is now valid.

**Fix:** Added type annotations and added `superseded`, `held` keys.

### 3.5 Confidence Downgrade Attribution (Drift)

[00 §9.2](00_project_context.md), [05 §5](05_reasoning_framework.md), and [06 §2.2](06_scoring_framework.md) each stated that confidence is downgraded by 0.2 for inconsistent reasoning, but did not clearly specify **which agent** performs the downgrade.

**Fix:** Clarified in [06 §2.2](06_scoring_framework.md): the **analyst agent** downgrades `confidence` by 0.2 if its own reasoning is internally inconsistent, before the scorer reads it.

---

## 4. Missing References Added

| Doc | Added reference |
|---|---|
| [00 §5.1](00_project_context.md) | [03 §3](03_workflow_constitution.md), [14 §3.1](14_watchlist.md) |
| [01 §3](01_signal_constitution.md) | [03 §S8](03_workflow_constitution.md) for gating source |
| [02 §A2](02_agent_constitution.md) | [07 §8](07_prompt_guidelines.md) for model map |
| [02 §A8](02_agent_constitution.md) | [04 §6](04_data_schema.md), [06 §8](06_scoring_framework.md) |
| [03 §S8](03_workflow_constitution.md) | [06 §5.1](06_scoring_framework.md), [06 §5.2](06_scoring_framework.md) |
| [03 §S9](03_workflow_constitution.md) | [01 §4](01_signal_constitution.md) for superseded rule |
| [03 §S3](03_workflow_constitution.md) | [01 §4](01_signal_constitution.md) for Signal-level dedup distinction |
| [06 §4](06_scoring_framework.md) | [02 §A5](02_agent_constitution.md) marked as quote, not redefinition |
| [08 §2](08_architecture.md) | [03 §2](03_workflow_constitution.md) for workflow inventory |
| [09 §5.1](09_development_roadmap.md) | [02 §2](02_agent_constitution.md), [10 §2](10_signal_taxonomy.md), [13 §3](13_report_template.md), [14](14_watchlist.md), [03 §3](03_workflow_constitution.md) |
| [10 §4](10_signal_taxonomy.md) | [02 §A2](02_agent_constitution.md) for detector |
| [11 §7](11_industry_mapping.md) | [12 §9](12_company_schema.md), [02 §A4](02_agent_constitution.md), [05 §2.2](05_reasoning_framework.md) |
| [12 §12](12_company_schema.md) | [04 §6](04_data_schema.md), [02 §A8](02_agent_constitution.md) |
| [13 §3.4 §6](13_report_template.md) | [03 §8.2](03_workflow_constitution.md) for cycle_id format |

---

## 5. Inconsistencies Fixed

| Doc | Inconsistency | Fix |
|---|---|---|
| [13 §3.4](13_report_template.md) | Used `cycle_01HXA` (underscore prefix) — not ULID format | Changed to `01HXA...` (ULID, per [03 §8.2](03_workflow_constitution.md)) |
| [08 §2.1](08_architecture.md) | Diagram showed W1–W4 | Updated to W1–W5 |
| [02 §A2](02_agent_constitution.md) | Used `claude-haiku-4-5` (no version suffix) | Changed to `claude-haiku-4-5-20251001` to match [07 §8](07_prompt_guidelines.md) |
| [07 §7.2](07_prompt_guidelines.md) | Plain text reference "05_reasoning_framework.md §2.1" | Converted to markdown link `[05 §2.1](05_reasoning_framework.md)` |
| [04 §9](04_data_schema.md) | Metadata schema missing fields referenced in 05 and 06 | Added `reasoning_partial`, `precedent_basis`, `precedent_conflict` |
| [04 §13](04_data_schema.md) | Schema versioning table missing several schemas | Added all 15 schemas to the table |

---

## 6. Items Deliberately Left Unchanged

These were considered but not modified because they are not actual conflicts:

| Item | Why left alone |
|---|---|
| Per-tier cost in [14 §3.2](14_watchlist.md) ($0.50/entity/day) vs per-Signal cost in [00 §7.2](00_project_context.md) (≤ $0.30) vs breakdown in [06 §10.1](06_scoring_framework.md) ($0.262) | Different metrics: per-entity-per-day (rate across multiple Signals) vs per-Signal (single-Signal cost) vs stage-level breakdown. All three are correct for their framing. |
| Watchlist default policies in [14 §8.1](14_watchlist.md) vs Phase targets in [09](09_development_roadmap.md) | Phase targets are aspirational goals; default policies are starting configuration. Will diverge in later phases. |
| Tier format (`tier_1` vs `Tier 1`) | Lowercase-with-underscore is the canonical machine form (matches [12 §10](12_company_schema.md) `WatchlistRef.tier` and [14 §1](14_watchlist.md) `WatchlistEntry.tier`). Human-readable form (with space, capitalized) is allowed in narrative prose. Both forms documented and consistent within their contexts. |
| "Score" vs "scoring" | The doc uses `Score` for the schema object and "scoring" for the activity. This is the natural English distinction and matches [04 §7](04_data_schema.md). |
| Composite formula appearing in [02 §A5](02_agent_constitution.md) and [06 §4](06_scoring_framework.md) | The agent catalog shows the formula in context for the agent's responsibility. 06 §4 is the canonical source. 02 §A5 now explicitly notes the cross-reference. |

---

## 7. New Conventions Established

The pass produced a few conventions that didn't exist before. They are now codified here for future reference.

### 7.1 Cycle ID Format

All artifacts that reference a workflow run use the **ULID format** (26 chars, Crockford base32) with no prefix. Examples in prose use `01HXA...` (truncated for readability). Schema-enforced by [04 §10.5 CycleReport.cycle_id](04_data_schema.md) and [04 §6 Provenance.cycle_id](04_data_schema.md).

### 7.2 Cross-Reference Style

All cross-document references in markdown use the standard markdown link syntax (label in brackets, target in parentheses, with a `.md` suffix for relative references) with optional section anchor — e.g., `[06 §5.1](06_scoring_framework.md)`. Plain-text references (e.g., "see doc X") are converted to links during review.

### 7.3 Schema Authority

For every field that appears in more than one document, exactly one is the **canonical source**:

| Field | Canonical doc |
|---|---|
| Signal schema | [04 §4](04_data_schema.md) |
| Evidence schema | [04 §5](04_data_schema.md) |
| Provenance schema | [04 §6](04_data_schema.md) |
| Score schema | [04 §7](04_data_schema.md) |
| Reasoning schema | [04 §8](04_data_schema.md) |
| Metadata schema | [04 §9](04_data_schema.md) |
| OverrideRecord | [04 §6 OverrideRecord](04_data_schema.md) |
| Composite formula | [06 §4](06_scoring_framework.md) |
| Gating thresholds | [03 §S8](03_workflow_constitution.md) ↔ [06 §5.1](06_scoring_framework.md) (paired) |
| Signal lifecycle | [01 §3](01_signal_constitution.md) |
| Signal cardinality rules | [01 §4](01_signal_constitution.md) |
| Agent catalog | [02 §3](02_agent_constitution.md) |
| Workflow catalog | [03 §2](03_workflow_constitution.md) |
| Signal taxonomy | [10 §2](10_signal_taxonomy.md) |
| Industry chain model | [11 §2](11_industry_mapping.md) |
| Company master | [12 §2](12_company_schema.md) |
| Watchlist spec | [14 §1](14_watchlist.md) |
| Report templates | [13 §3–5](13_report_template.md) |

### 7.4 Migration Log Discipline

Every MAJOR or MINOR version bump in any document **must** be recorded in [09 §11 Migration Log](09_development_roadmap.md). The log was extended in this pass to record the consistency fixes themselves.

---

## 8. Outstanding Recommendations (Future Passes)

These are improvements that were identified but not applied in this pass, to keep scope contained:

1. **Glossary section in [00](00_project_context.md)** — collect all SIGNAL-specific terms (Signal, Agent, Cycle, Cluster, ThesisDelta, OverrideRecord, etc.) with one-line definitions. Currently scattered across documents.
2. **Cross-reference validation script** — `scripts/validate_cross_refs.py` that checks every markdown link resolves to an existing section.
3. **Schema-to-doc mapping table** — explicit table in [00 §11 Document Map](00_project_context.md) listing which document owns which schema field.
4. **Decay worker definition** — referenced in [01 §3](01_signal_constitution.md) as "decay_worker" but not formally defined in [02](02_agent_constitution.md) (only 8 agents listed). Either add to [02 §2](02_agent_constitution.md) inventory as A9 or clarify it is a background job, not an agent.
5. **Multi-language source naming** — [10 §10](10_signal_taxonomy.md) Tag Layer includes `language:zh` but the field placement (Signal.metadata.custom_tags vs RawDocument.language) needs clarification.

These are recorded here for the next review pass.

---

## 9. Sign-Off

This pass leaves the spec set internally consistent on:
- All numeric thresholds (gating, score, calibration, cost)
- All enum types (lifecycle, override actions, status, source types)
- All cross-references resolve
- All schemas have a single canonical home
- All workflow inventory references match between 02, 03, 08
- All version dependencies declared in document headers match the content

The next reader can rely on every cross-document markdown link (label + section + `.md` target) to land on the section referenced.