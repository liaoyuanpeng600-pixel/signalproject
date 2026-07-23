# Report Specification

> **Document role:** Defines the common reporting language for the entire Reports subsystem. Establishes report philosophy, section definitions, ordering principles, writing style, action rules, and provenance requirements shared by every report type. All current and future report types (Daily Brief, Weekly Review, Per-Entity Brief, and any later additions) must conform to this specification.
>
> This document is a **frozen design specification**. It produces no code. It constrains future implementation.
>
> Requires: `00_ARCHITECTURE_PRINCIPLES.md`, `01_OBJECT_MODEL.md`, `13_REPORT_TEMPLATE.md`.

---

## Document Metadata

| Field | Value |
|---|---|
| **Status** | Frozen |
| **Version** | 1.0 |
| **Effective Date** | 2026-07-19 |
| **Next Review** | TBD |
| **Owner** | Architecture |

---

## 1. Report Philosophy

Reports communicate **research state**.

They are not narration. They are not commentary. They are not opinion. They
are a deterministic surface that lets a human operator see what the system
currently believes, with citations, about a defined slice of the world.

Every SIGNAL report must satisfy all of the following:

- **Communicate research state.** A report answers the question "what is
  the system's current research understanding of X?" where X is defined by
  the report's anchor (a watchlist, a reporting period, or an Entity).
- **Be thesis-centric.** When a Thesis exists for the report's anchor, it
  organizes everything else. Signals and Evidence are presented as support
  for the Thesis, not as independent lists.
- **Be deterministic.** Two runs of the same pipeline against the same
  inputs MUST produce byte-identical reports. No randomness. No LLM. No
  stochastic ranking. Time-sensitive fields (timestamps) are inputs, not
  sources of variation.
- **Be evidence-backed.** Every factual statement in a report must be
  traceable to a Signal ID, a Thesis ID, or a calibration data point. No
  orphan facts.
- **Avoid chronological narration.** Reports do not say "first this happened,
  then that happened". They say "the current state is X, supported by Y, Z".
- **Communicate state changes.** When a report includes deltas (overrides,
  new Signals, Thesis updates), the changes are surfaced explicitly with
  the prior and new state visible.

---

## 2. Common Section Definitions

The following sections are the canonical vocabulary of SIGNAL reports.
Each section has exactly one responsibility. A section MUST NOT take on
the responsibilities of another section.

### 2.1 Overview

**Responsibility.** A one-paragraph synthesis of the report's anchor and
the most important conclusion the reader should walk away with. May be a
short headline plus a 1–3 sentence summary.

The Overview is the only section that may contain prose that is not
directly traceable to a Signal or Thesis. It MUST still be factual and
quantitative.

### 2.2 Current Thesis

**Responsibility.** State the current Thesis (interpretation) for the
report's anchor, including its status (emerging / evolving / mature /
superseded / retired) and confidence.

When no Thesis exists for the anchor, this section explicitly says so
and the downstream supporting sections MAY be omitted.

### 2.3 Supporting Signals

**Responsibility.** List the Signals that directly support the Current
Thesis. Each Signal is cited inline and ranked by composite score.

A Signal that does not support any Thesis MUST NOT appear here; it
belongs in a Knowledge summary (out of scope for Reports).

### 2.4 Supporting Evidence

**Responsibility.** Show the Evidence that grounds the Supporting Signals.
Evidence is presented as quality-graded excerpts, not full documents.

### 2.5 Research Progress

**Responsibility.** Describe the Research investigations that produced
or modified the Current Thesis. Includes Research status, signal
aggregation counts, and traceability flags.

### 2.6 Open Questions

**Responsibility.** Surface `Thesis.open_questions` (Path C annotations
from the ThemeEvolver). These are explicitly unresolved and require
curator or future-research attention.

### 2.7 Upcoming Catalysts

**Responsibility.** List known future events (earnings, regulatory
deadlines, scheduled announcements) relevant to the anchor. Sourced from
caller-supplied notes — Reports do not invent catalysts.

If the caller supplies no notes, this section is omitted.

### 2.8 Risks

**Responsibility.** Surface pre-curated risk items relevant to the anchor.
Sourced from caller-supplied notes — Reports do not invent risks.

If the caller supplies no notes, this section is omitted.

### 2.9 Calibration Summary

**Responsibility.** Surface calibration data (Score Deltas, conflict
counts, action distribution). Only present when `CalibrationData` is
supplied as input.

### 2.10 Provenance

**Responsibility.** Always present. List the cycle IDs covered, agent
versions used, prompt versions used, degrade mode status, and coverage
gaps (anchors with zero Signals in the window).

### 2.11 Section Inheritance Rules

A report type MAY use a subset of these sections, but it MUST NOT use a
section for a purpose other than the one defined above. If a new purpose
arises, a new section definition is added here before any implementation.

---

## 3. Section Ordering Principles

The preferred information flow is:

```
High-level conclusion (Overview)
        ↓
Supporting thesis (Current Thesis)
        ↓
Evidence (Supporting Signals → Supporting Evidence)
        ↓
Actions (Research Progress → Open Questions → Upcoming Catalysts → Risks)
        ↓
Appendix (Calibration Summary)
        ↓
Appendix (Provenance — always last)
```

### 3.1 Ordering Invariants

The following ordering invariants apply to every report type that uses
the corresponding sections:

1. **Overview always first** (after the title).
2. **Current Thesis precedes Supporting Signals**, which precede
   Supporting Evidence.
3. **Open Questions, Upcoming Catalysts, and Risks** follow the
   supporting-evidence chain; their relative order is determined by
   the report type.
4. **Calibration Summary** precedes Provenance.
5. **Provenance is always last.**

A report type that violates one of these rules must justify the
violation in its docstring.

### 3.2 Section Omission Rules

Optional sections are omitted entirely (not rendered as empty stubs)
when their inputs are absent:

| Section | Omitted when |
|---|---|
| Supporting Signals | No Signals support the Current Thesis |
| Supporting Evidence | No Signals → no Evidence to surface |
| Research Progress | No Research items exist for the anchor |
| Open Questions | `Thesis.open_questions` is empty |
| Upcoming Catalysts | Caller-supplied notes are empty |
| Risks | Caller-supplied notes are empty |
| Calibration Summary | `CalibrationData` not provided |

Current Thesis itself is mandatory unless the report is explicitly a
"no-thesis-yet" anchor (in which case Overview states this and the
downstream chain is omitted).

---

## 4. Writing Style

Reports MUST be:

- **Objective.** No subjective adjectives. No editorial framing. No
  rhetorical questions.
- **Evidence-based.** Every factual claim cites a Signal, Thesis, or
  data point. No unsourced assertions.
- **Quantitative where possible.** Prefer numbers over words. "EPS +14%
  vs consensus" not "strong quarter". "Composite 0.78" not "high
  confidence".
- **Free from promotional language.** No buy / sell / hold verbs. No
  target prices. No "we recommend".
- **No hype.** No "game-changer", "moon", "rocket", "to the moon", or
  similar.
- **No storytelling.** Reports do not narrate events in time order;
  they describe current state.

### 4.1 Banned Phrases (Static Denylist)

The following phrases MUST NOT appear in any rendered output. The
renderer enforces this as a post-generation regex check.

- "we recommend", "we suggest buying", "we suggest selling"
- "target price:"
- "significantly" (unless paired with a number, checked elsewhere)
- "game-changer", "game changer", "moon", "rocket", "to the moon",
  "mooning"
- "strong quarter", "weak quarter" (vague)
- "buy", "sell", "hold" as verbs on a position
- "definitely", "certainly" (overconfident without warrant)

### 4.2 Citation Format

Inline citations use the short form `[sig:01HXY...]` for individual
Signals and `[thesis:01HW2...]` for Theses. The full provenance is in
the JSON companion (deferred to a future exporter).

---

## 5. Action Rules

When a report contains a recommendation or proposed action, it MUST
specify all four of the following:

| Field | Meaning |
|---|---|
| **Condition** | The state under which the action is appropriate. |
| **Action** | The specific action being recommended. |
| **Priority** | Relative urgency (e.g., high / medium / low). |
| **Confidence** | The system's confidence in the recommendation (composite-like value in [0, 1]). |

Unconditional recommendations ("this entity should be added to the
watchlist" with no Condition) are forbidden.

This rule applies to curator recommendations surfaced in Weekly Review
and Per-Entity Brief reports. The Daily Brief does not contain
recommendations.

---

## 6. Provenance Requirements

Every report MUST include a Provenance footer (always last) with the
following fields:

| Field | Source | Required |
|---|---|---|
| Cycle IDs covered | Pipeline | Yes (may be empty for manual reports) |
| Agent versions | Build / deployment | Yes (or "unspecified") |
| Prompt versions | Build / deployment | Yes (or "unspecified") |
| Degrade mode status | Cycle metadata | Yes |
| Coverage gaps | Synthesis input | Yes (may be empty) |
| Reporting period (Weekly Review) | Caller | Yes for Weekly Review |
| Anchor Entity ID (Per-Entity Brief) | Caller | Yes for Per-Entity Brief |

Future metadata fields (e.g., `generated_at`, `builder_version`,
`renderer_version`, `report_version`, `word_count`, `signal_count`,
`entity_count`) MAY be added to the `Report` model without breaking
this specification, provided they remain additive and do not redefine
existing fields.

---

## 7. Conformance

Every report type implemented in `src/reports/` MUST:

1. Use only the section definitions in §2.
2. Follow the ordering invariants in §3.1.
3. Honor the omission rules in §3.2.
4. Enforce the writing-style rules in §4 (including the banned-phrase
   denylist).
5. Apply the action-rule format in §5 wherever recommendations appear.
6. Emit the Provenance footer per §6.

A report type that needs a section not defined in §2 must first add
the section definition here, then implement it.

---

## 8. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-19 | Initial freeze: Report Philosophy, Section Definitions, Ordering, Writing Style, Action Rules, Provenance |

Section additions are MINOR. New writing-style prohibitions are MINOR.
Reordering existing sections is MAJOR.