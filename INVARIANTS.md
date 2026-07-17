# INVARIANTS — System-Wide Immutable Constraints

> **Document role:** Defines rules that **cannot be violated** by any agent, workflow, operator, or external caller. Violation of any invariant is a system error — never a silent failure.
>
> Read alongside: [SPEC_VERSION.md](SPEC_VERSION.md), [GLOSSARY.md](GLOSSARY.md), [00_project_context.md](00_project_context.md).

---

## 1. What Is an Invariant

An **invariant** is a property of the system that **must always hold**, in every state, under every operation. Invariants differ from rules in that:

- Rules can be temporarily broken (a Score can be recomputed; a Signal can be reclassified).
- Invariants cannot. If broken, the system has a bug, not a state.

Every invariant is:
- **Testable** — there exists a check (often a `lint_spec.py` rule) that verifies it
- **Traceable** — it cites the canonical document that defines the underlying contract
- **Enforced** — there is an enforcement point (agent, validator, linter)

---

## 2. The 12 Invariants

### INV-1 — Evidence Is Required

> **Statement.** Every Signal MUST have a non-empty `evidence[]` array. A Signal with zero evidence is rejected at verification.

| Property | Value |
|---|---|
| Owner doc | [01_signal_constitution.md §1](01_signal_constitution.md), [04 §4.2](04_data_schema.md) |
| Enforcement | `verifier` agent ([02 §A3](02_agent_constitution.md)) |
| Failure mode | Signal status set to `rejected`, reason `missing_evidence` |
| Lint check | `lint_spec.py::check_invariant_invariant_evidence` |

### INV-2 — Signal ID Is Immutable

> **Statement.** A Signal's `id` is generated once (ULID) and never changes for the Signal's lifetime. Renames, corrections, and overrides do not regenerate the ID.

| Property | Value |
|---|---|
| Owner doc | [01 §1](01_signal_constitution.md), [04 §3.2](04_data_schema.md) |
| Enforcement | SignalStore write path; curator override path (preserves `id`) |
| Failure mode | Detected by `lint_spec.py::check_id_immutable`; alerts Operator |
| Migration | None — if violated, the Signal is corrupted and must be regenerated |

### INV-3 — Provenance Is Mandatory

> **Statement.** Every Signal MUST have a complete `Provenance` object: `agent_chain` non-empty, `agent_versions` non-empty, `cycle_id` set, `emitted_at` set.

| Property | Value |
|---|---|
| Owner doc | [04 §6](04_data_schema.md) |
| Enforcement | Schema validator at write time |
| Failure mode | Rejected at persist stage ([03 §S9](03_workflow_constitution.md)) |
| Lint check | `lint_spec.py::check_invariant_provenance_complete` |

### INV-4 — Score Values Are Bounded

> **Statement.** Every `Score` field (`magnitude`, `confidence`, `timeliness`, `novelty`, `actionability`, `composite`) MUST be in `[0.0, 1.0]`. Out-of-range values are clamped at write time.

| Property | Value |
|---|---|
| Owner doc | [04 §7](04_data_schema.md), [06 §4.2](06_scoring_framework.md) |
| Enforcement | `compute_composite()` clamps; writer validates |
| Failure mode | Value clamped silently; warning logged; alert if >5% of writes need clamping |
| Lint check | `lint_spec.py::check_score_bounds` |

### INV-5 — Composite Is Deterministic

> **Statement.** `Score.composite` MUST equal `compute_composite(score)` per [06 §4](06_scoring_framework.md). The LLM never assigns composite directly. If a stored composite doesn't match recomputation, an integrity error fires.

| Property | Value |
|---|---|
| Owner doc | [06 §4](06_scoring_framework.md) |
| Enforcement | Post-write verifier; nightly audit |
| Failure mode | Critical alert; Operator investigates; affected Signal is held |
| Lint check | `lint_spec.py::check_composite_formula` (cross-checks examples) |

### INV-6 — Lifecycle Transitions Are Valid

> **Statement.** A Signal's `status` may only transition along the allowed edges in [01 §3](01_signal_constitution.md). Specifically:

```
draft → verified → active → decayed
draft → rejected
verified → active
verified → held
verified → rejected
active → superseded
active → decayed
held → active | rejected
```

Any transition not in this graph is invalid. There is no `* → draft` transition (Signals are never revived into draft).

| Property | Value |
|---|---|
| Owner doc | [01 §3](01_signal_constitution.md) |
| Enforcement | SignalStore transition validator |
| Failure mode | Transition rejected; integrity alert |
| Lint check | `lint_spec.py::check_lifecycle_transitions` |

### INV-7 — Schema Authority Is Unique

> **Statement.** Each schema field has **exactly one canonical definition** in exactly one document. Other documents reference, never redefine. The authority table is in [REVIEW_NOTES §7.3](REVIEW_NOTES.md).

| Property | Value |
|---|---|
| Owner doc | [REVIEW_NOTES §7.3](REVIEW_NOTES.md), [00 §2 P2](00_project_context.md) |
| Enforcement | `lint_spec.py::check_schema_authority` (heuristic) |
| Failure mode | Documentation defect; assigned to whoever owns the duplicate |
| Lint check | `lint_spec.py::check_schema_authority` |

### INV-8 — Draft Signals Never Reach Users

> **Statement.** A Signal in `status = draft` MUST NOT appear in any user-facing report, UI list, or curator queue. Only `verified`+ signals appear downstream.

| Property | Value |
|---|---|
| Owner doc | [01 §3](01_signal_constitution.md) |
| Enforcement | Reporter filter ([02 §A7](02_agent_constitution.md), [13 §2](13_report_template.md)); API access control |
| Failure mode | Critical alert; report pulled; investigation |
| Lint check | `lint_spec.py::check_draft_signals_visible` |

### INV-9 — Cycle ID Is ULID

> **Statement.** Every `cycle_id` MUST be a 26-character ULID (Crockford base32). No prefix, no suffix, no transformation.

| Property | Value |
|---|---|
| Owner doc | [03 §8.2](03_workflow_constitution.md), [04 §6](04_data_schema.md) |
| Enforcement | Cycle ID generator; write validator |
| Failure mode | Cycle rejected |
| Lint check | `lint_spec.py::check_cycle_id_format` |

### INV-10 — All Times Are ISO8601 UTC

> **Statement.** Every timestamp field (`timestamp`, `detected_at`, `scored_at`, `emitted_at`, `occurred_at`, `verified_at`, `as_of`, etc.) MUST be ISO8601 in UTC (`Z` suffix or `+00:00`). Local times are forbidden.

| Property | Value |
|---|---|
| Owner doc | [04 §2](04_data_schema.md), [04 §12](04_data_schema.md) |
| Enforcement | Schema validator |
| Failure mode | Rejected at write |
| Lint check | `lint_spec.py::check_timestamp_format` |

### INV-11 — Override Records Are Append-Only

> **Statement.** `OverrideRecord[]` (in `Provenance.override_records`) MUST be append-only. Existing records cannot be modified or deleted. Curator actions create new records; they never overwrite.

| Property | Value |
|---|---|
| Owner doc | [02 §A8](02_agent_constitution.md), [04 §6](04_data_schema.md) |
| Enforcement | SignalStore write path; database triggers |
| Failure mode | Critical alert; tampering indicator |
| Lint check | `lint_spec.py::check_override_immutable` |

### INV-12 — Composite Weight Sum Is 1.0

> **Statement.** The five composite weights (`magnitude`, `confidence`, `timeliness`, `novelty`, `actionability`) MUST sum to `1.0` exactly. Configuration drift is detected and rejected at boot.

| Property | Value |
|---|---|
| Owner doc | [06 §4](06_scoring_framework.md) |
| Enforcement | Config validator at boot |
| Failure mode | Boot fails; pipeline halts |
| Lint check | `lint_spec.py::check_composite_weights` |

---

## 3. Invariant Lifecycle

Each invariant is itself versioned. An invariant may be **deprecated** or **strengthened** only via the RFC process ([GOVERNANCE.md §2](GOVERNANCE.md)).

| Lifecycle state | Meaning |
|---|---|
| **active** | Currently enforced; any violation is a bug |
| **deprecated** | Still checked, but a replacement is planned; violations warn instead of fail |
| **retired** | No longer checked (the underlying contract no longer exists) |

State transitions are recorded in the version history at the bottom of this document.

---

## 4. Enforcing Invariants

Each invariant is enforced at three levels:

1. **Schema validator** — at write time, the field-level schema check rejects malformed data.
2. **Agent postcondition** — each agent declares its postconditions (e.g., "Every emitted Signal has ≥1 Evidence"). The runner verifies postconditions before accepting output.
3. **Lint pass** — `scripts/lint_spec.py` checks the entire spec set for consistency, runs in CI, fails the build on violations.

If an invariant is violated at runtime:
- **Recoverable** (e.g., bad input from a source): the offending item is rejected; the rest of the cycle continues.
- **Non-recoverable** (e.g., a System invariant like INV-7 or INV-12): the pipeline halts; Operator is paged.

---

## 5. Adding a New Invariant

To propose a new invariant:

1. Write an RFC per [GOVERNANCE.md §2](GOVERNANCE.md).
2. The RFC must specify:
   - **Statement** (one sentence, falsifiable)
   - **Owner doc** (where the underlying contract is defined)
   - **Enforcement** (which agent or check catches violations)
   - **Failure mode** (what happens on violation)
   - **Lint check** (which rule in `lint_spec.py` enforces it)
3. On RFC acceptance, add the invariant here with a new INV-N number.
4. Update `lint_spec.py` to enforce it.
5. Update affected agent specs (postconditions).

---

## 6. Cross-Reference Index

For convenience, the invariants mapped to the documents that touch them:

| Invariant | Primary doc | Linter check |
|---|---|---|
| INV-1 Evidence required | [01 §1](01_signal_constitution.md), [04 §4](04_data_schema.md) | `check_invariant_evidence` |
| INV-2 ID immutable | [04 §3.2](04_data_schema.md) | `check_id_immutable` |
| INV-3 Provenance mandatory | [04 §6](04_data_schema.md) | `check_invariant_provenance_complete` |
| INV-4 Score bounded | [06 §4](06_scoring_framework.md) | `check_score_bounds` |
| INV-5 Composite deterministic | [06 §4](06_scoring_framework.md) | `check_composite_formula` |
| INV-6 Lifecycle valid | [01 §3](01_signal_constitution.md) | `check_lifecycle_transitions` |
| INV-7 Schema authority unique | [REVIEW_NOTES §7.3](REVIEW_NOTES.md) | `check_schema_authority` |
| INV-8 Draft hidden | [01 §3](01_signal_constitution.md) | `check_draft_signals_visible` |
| INV-9 Cycle ID is ULID | [03 §8.2](03_workflow_constitution.md) | `check_cycle_id_format` |
| INV-10 Times are ISO8601 UTC | [04 §2](04_data_schema.md) | `check_timestamp_format` |
| INV-11 Override append-only | [02 §A8](02_agent_constitution.md) | `check_override_immutable` |
| INV-12 Composite weights sum 1.0 | [06 §4](06_scoring_framework.md) | `check_composite_weights` |

---

## 7. Version History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-16 | Initial 12 invariants defined |