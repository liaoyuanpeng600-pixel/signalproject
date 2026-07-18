# Constitution Alignment Report — Object Model v1.0

> **Document role:** Maps every Constitution document (01–14) against the frozen Object Model v1.0. Identifies per-document alignment work required.
>
> **Document Metadata**
> Status: Draft for review
> Version: 1.0
> Date: 2026-07-18
> Owner: Architecture
>
> Read alongside: [01_OBJECT_MODEL.md](01_OBJECT_MODEL.md) (frozen), [00_ARCHITECTURE_PRINCIPLES.md](00_ARCHITECTURE_PRINCIPLES.md) (frozen).

---

## Verdict Categories

| Verdict | Meaning |
|---|---|
| **Conforms** | Document is consistent with Object Model v1.0. No structural change required. Optional cross-reference addition only. |
| **Minor Alignment Needed** | Document is structurally compatible with Object Model v1.0 but requires targeted edits to make the alignment explicit (e.g., terminology, cross-references, scope clarifications). |
| **Major Conflict** | Document contains a definition or rule that contradicts Object Model v1.0. Requires substantive resolution before freeze can be considered stable. |

---

## Summary

| Verdict | Count | Documents |
|---|---|---|
| Conforms | 7 | 02, 06, 07, 08, 09, 10, 12 |
| Minor Alignment Needed | 7 | 01, 03, 04, 05, 11, 13, 14 |
| Major Conflict | 0 | — |
| **Total** | **14** | All 01–14 reviewed |

**Headline:** No major conflicts. Half the documents conform outright; half need minor alignment. The Object Model v1.0 freeze is stable against existing Constitutions.

---

## Per-Document Verdicts

### 01 — Signal Constitution

**Verdict:** Minor Alignment Needed

**Current state.** Defines Signal as the atomic unit of observation. Lifecycle states (draft → verified → active → decayed → superseded) align with the Object Model's Signal lifecycle.

**Why minor (not major).** No contradiction. The Signal definition and lifecycle are compatible. The issue is terminology and cross-reference only.

**Alignment work required.**
- Add explicit cross-reference to Object Model v1.0 §4 Signal in document header.
- Verify that the lifecycle states in 01 map 1-to-1 to the states named in Object Model v1.0 §4.
- Add a one-sentence note clarifying that `Cluster` and `ThesisDelta` are **runtime aggregates**, not Object Model objects (per Object Model §"Operational Concepts").

---

### 02 — Agent Constitution

**Verdict:** Conforms

**Current state.** Defines 8 agents as workflow-layer components. Each agent has a role and contracts.

**Why conforms.** Agents are explicitly out of Object Model scope per §"Operational Concepts". Agents operate **on** Objects (Signals, Research, Evidence) but are not Objects themselves.

**Optional work.**
- Add a one-line note in document header: "Agents are workflow components, not Object Model objects. They operate on the objects defined in [01_OBJECT_MODEL.md](01_OBJECT_MODEL.md)."

---

### 03 — Workflow Constitution

**Verdict:** Minor Alignment Needed

**Current state.** Defines 5 workflows (W1–W5) and 9 stages (S1–S9). Stages produce and consume Signals, Research, and ThesisDeltas.

**Why minor.** The stage outputs are mostly compatible with Object Model types. The misalignment is conceptual labeling, not structural conflict.

**Alignment work required.**
- For each stage, ensure the output type is mapped to an Object Model object or marked as a runtime aggregate.
- Confirm `synthesis_cycle` (W3) produces `Research` (not a new object).
- Confirm `report_cycle` (W4) reads from Signals + ThesisDeltas + Knowledge, producing Reports (Views).
- Add cross-reference to Object Model §"Object Relationships" in document header.

---

### 04 — Data Schema

**Verdict:** Minor Alignment Needed

**Current state.** Defines schemas for Signal, Evidence, Provenance, Score, RawDocument, ThesisDelta, Cluster, Company, etc.

**Why minor.** Schemas are the implementation-level representation of Object Model objects. They are below the Object Model in the hierarchy and should not redefine concepts. The schemas currently in place are largely compatible — they implement the Object Model rather than contradict it.

**Alignment work required.**
- Add a header note: "Schemas here implement the objects defined in [01_OBJECT_MODEL.md](01_OBJECT_MODEL.md). No schema in this document redefines or contradicts an Object Model type."
- Verify `ThesisDelta` and `Cluster` schemas are marked as **runtime aggregates**, not Object Model objects.
- Verify `CycleReport` schema is marked as a runtime artifact.

---

### 05 — Reasoning Framework

**Verdict:** Minor Alignment Needed

**Current state.** Defines reasoning methodology (significance, causality, durability, precedent) for the analyst agent. Operates on Signals and produces a `Reasoning` object.

**Why minor.** The Reasoning object in this Constitution is structurally equivalent to Object Model's `Research` object. The terminology is the source of misalignment.

**Alignment work required.**
- Establish the terminology mapping: the `Reasoning` object in 05 ≡ the `Research` object in Object Model.
- Either rename `Reasoning` → `Research` throughout, or explicitly document the equivalence in both documents.
- Add a header note clarifying the equivalence: "The Reasoning object defined here is the implementation of the Object Model's Research object."

---

### 06 — Scoring Framework

**Verdict:** Conforms

**Current state.** Defines the 5 scoring dimensions and composite formula. Operates on Signals as metadata.

**Why conforms.** Score is documented in Object Model v1.0 §"Operational Concepts" as **Signal metadata**, not a separate object. The 5 dimensions and composite formula are consistent with this classification.

**Optional work.**
- None required for conformance.
- Optional: add cross-reference to Object Model §"Operational Concepts" for the Score row.

---

### 07 — Prompt Guidelines

**Verdict:** Conforms

**Current state.** Defines prompt engineering standards. Operates at the agent/runtime boundary.

**Why conforms.** Prompts are below the Object Model in the hierarchy. They instruct agents on how to produce and consume Objects but do not redefine them.

**Optional work.**
- None required.

---

### 08 — Architecture

**Verdict:** Conforms

**Current state.** Defines technical architecture: storage tiers, LLM Gateway, observability, deployment. Defines `CycleReport` as a runtime artifact.

**Why conforms.** Runtime concerns (storage, deployment, observability) are explicitly below the Object Model in the hierarchy. `CycleReport` is correctly marked as a runtime artifact.

**Optional work.**
- None required for conformance.
- Optional: add cross-reference to Object Model §"Operational Concepts" for the Cycle/CycleReport row.

---

### 09 — Development Roadmap

**Verdict:** Conforms

**Current state.** Phased delivery plan. No definitions of objects, signals, or research concepts.

**Why conforms.** Roadmap is orthogonal to the Object Model. It describes *when* things get built, not *what* things are.

**Optional work.**
- None.

---

### 10 — Signal Taxonomy

**Verdict:** Conforms

**Current state.** Defines closed enum of 10 Signal types (earnings, guidance, capital_action, etc.).

**Why conforms.** Signal Taxonomy is a **refinement** of Object Model's Signal. It specifies subtypes of the Signal type, not new object types. This is exactly the kind of Constitution-level refinement the Object Model permits.

**Optional work.**
- None required.
- Optional: add header note: "This taxonomy refines the Signal object defined in [01_OBJECT_MODEL.md](01_OBJECT_MODEL.md). It does not introduce new object types."

---

### 11 — Industry Mapping

**Verdict:** Minor Alignment Needed

**Current state.** Defines industry chains as nodes (IndustryNode) and edges (ChainEdge). IndustryNodes have classifications like "upstream", "midstream", etc.

**Why minor.** Per Object Model Decision 2, Industry is now an **Entity refinement** (a grouping Entity), and chains are **relations between Entities**. This is structurally consistent with the existing 11 doc, but the doc's framing as "IndustryNode" vs "Entity refinement" needs explicit alignment.

**Alignment work required.**
- Add header note: "Industries defined here are Entity refinements. Chains are relations between Entities. This document conforms to [01_OBJECT_MODEL.md](01_OBJECT_MODEL.md) Decision 2."
- Update terminology where helpful (e.g., "IndustryNode" → "Industry Entity", keeping internal names as-is if renaming is invasive).
- Verify that the analyst agent's traversal of chains maps to the Object Model's causal reasoning rules.

---

### 12 — Company Schema

**Verdict:** Conforms

**Current state.** Defines Company as an Entity refinement with identity, classification, financials, governance.

**Why conforms.** Per Object Model Decision 1, Constitutions may introduce Entity refinements. Company is exactly such a refinement. The Company schema is structurally consistent with Object Model's Entity.

**Optional work.**
- None required.
- Optional: add header note: "Company is an Entity refinement per [01_OBJECT_MODEL.md](01_OBJECT_MODEL.md) Decision 1."

---

### 13 — Report Template

**Verdict:** Minor Alignment Needed

**Current state.** Defines report templates (Daily Brief, Weekly Review, Per-Entity Brief). References `Cluster` and `ThesisDelta` as inputs.

**Why minor.** Per Object Model Decision 4, Reports are **Views**, not Objects. `Cluster` and `ThesisDelta` are **runtime aggregates** of Signals. The doc already structures reports correctly; the misalignment is in labeling.

**Alignment work required.**
- Add header note: "Reports are Views, not Object Model objects. Cluster and ThesisDelta are runtime aggregates of Signals (per [01_OBJECT_MODEL.md](01_OBJECT_MODEL.md) §Operational Concepts)."
- Optionally rename internal report sections to make the View nature explicit (e.g., "View: Daily Brief").

---

### 14 — Watchlist

**Verdict:** Minor Alignment Needed

**Current state.** Defines watchlist tiers, per-tier pipeline behavior, coverage targets. Treats Watchlist as a primary operational concept.

**Why minor.** Per Object Model Decision 3, the Watchlist is a **View over Entities**, not an Object. The doc's content (tiers, coverage) describes selection criteria for the View, which is correct — but the doc currently does not explicitly frame itself as a View.

**Alignment work required.**
- Add header note: "The Watchlist is a View over Entities, not an Object Model object (per [01_OBJECT_MODEL.md](01_OBJECT_MODEL.md) Decision 3). Tiers and coverage targets are selection criteria for this View."
- Verify that no internal language implies Watchlist is an object with its own lifecycle (it should be operational state, not an Object).

---

## Cross-Document Patterns

### Terminology Mismatch: "Reasoning" vs "Research"

The most material inconsistency across documents is the use of **"Reasoning"** in [05_reasoning_framework.md](../05_reasoning_framework.md) vs **"Research"** in the Object Model. These appear to refer to the same concept (the structured output of the analyst agent). This is a terminology issue, not a conceptual conflict.

**Recommended alignment.** Either rename `Reasoning` → `Research` in 05, or document the equivalence explicitly in both 05 and the Object Model. The second option is less invasive.

### Runtime Aggregate Vocabulary

Three terms appear in existing Constitutions that are runtime aggregates, not Object Model objects:

| Term | Doc | Object Model classification |
|---|---|---|
| `Cluster` | 01, 13 | Runtime aggregate |
| `ThesisDelta` | 01, 04, 13 | Runtime aggregate |
| `CycleReport` | 03, 08 | Runtime artifact |

No structural change required, but each Constitutions should make this classification explicit.

### Object Refinement Tracking

Per Decision 1, Entity refinements are Constitution-level concerns. The following refinements are now recognized:

| Refinement | Doc |
|---|---|
| Company | [12_company_schema.md](../12_company_schema.md) |
| Industry | [11_industry_mapping.md](../11_industry_mapping.md) |

Future Constitutions may introduce additional refinements (Sector, AssetClass, Jurisdiction, etc.) without Object Model amendment.

---

## Remaining Architectural Risks

The freeze is stable, but three residual risks should be monitored:

### Risk 1 — Terminology Drift in Future Constitutions

**Description.** As new Constitutions are added, the temptation will be to introduce new terminology for established concepts (e.g., "Investigation" instead of "Research", "Discovery" instead of "Evidence", "Insight" instead of "Thesis").

**Mitigation.** Add a header convention: every Constitution should declare "Terminology conforms to [01_OBJECT_MODEL.md](01_OBJECT_MODEL.md) §Core Objects." Deviations must be justified in the Constitution's preamble.

### Risk 2 — Pressure to Promote Runtime Aggregates to Objects

**Description.** Over time, runtime aggregates like `Cluster`, `ThesisDelta`, and `CycleReport` may grow in importance and stakeholders may want to "promote" them to Object Model objects.

**Mitigation.** Any promotion must follow the [Architecture Governance amendment process](ARCHITECTURE_GOVERNANCE.md). The default position is that runtime aggregates stay at the runtime layer unless a concrete research-level need emerges.

### Risk 3 — Entity Refinement Proliferation

**Description.** Per Decision 1, Constitutions can introduce Entity refinements. Without coordination, different Constitutions may introduce overlapping or conflicting refinements (e.g., two Constitutions both defining "SectorEntity" with different properties).

**Mitigation.** The Architecture Owner should maintain a registry of declared Entity refinements, appended to the Object Model as a non-normative appendix. New refinements are reviewed for overlap before adoption.

---

## Alignment Work Summary

| Severity | Count | Estimated effort |
|---|---|---|
| Major Conflict | 0 | — |
| Minor Alignment | 7 | Each ~5–15 lines of targeted edit + cross-reference |
| Optional cross-reference | 7 | Each ~1–2 lines |

**Recommended execution order:**

1. Resolve the "Reasoning" vs "Research" terminology question (single decision, propagates to one or two docs).
2. Update 01, 03, 04, 11, 13, 14 with their explicit Object Model cross-references and clarifications.
3. Add optional cross-references to conforming documents (02, 06, 08, 12).
4. Skip 07, 09, 10 — no work needed.

The Object Model v1.0 freeze does not depend on these alignments being completed. The freeze is structural; the alignments are documentary.

---

## Version History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-18 | Initial alignment report for Object Model v1.0 freeze |
