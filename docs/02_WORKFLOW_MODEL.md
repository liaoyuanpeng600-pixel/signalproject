# Workflow Model

> **Document role:** Defines the logical flow of Objects through the SIGNAL research system. Specifies each stage's inputs, outputs, responsibilities, gates, failure paths, and cardinality rules. Sits between the Object Model and the Runtime layer.
>
> This document does not describe runtime, agents, prompts, implementation, or storage. It describes logical flow only.
>
> Read alongside: [00_ARCHITECTURE_PRINCIPLES.md](00_ARCHITECTURE_PRINCIPLES.md) (frozen), [01_OBJECT_MODEL.md](01_OBJECT_MODEL.md) (frozen).

---

## Document Metadata

| Field | Value |
|---|---|
| **Status** | Draft for Freeze |
| **Version** | 1.0 |
| **Effective Date** | TBD on freeze |
| **Next Review** | TBD |
| **Owner** | Workflow |

> **Note.** This document is implementation-independent. It defines logical flow, gates, and failure paths. Runtime executes the workflow; Runtime does not redefine it.

---

## Purpose

The Workflow Model defines how Objects move through the research system.

It answers five questions:

- **What happens at each stage?** — the responsibilities of each transition.
- **What must be true to advance?** — the gates and their conditions.
- **What happens when a Gate fails?** — the failure paths.
- **How many of each Object?** — the cardinality rules.
- **What is Runtime allowed to do?** — the boundary between workflow and runtime.

This document operates on the Objects defined in the [Object Model](01_OBJECT_MODEL.md). It does not introduce new object types. The Objects flow through the pipeline; the pipeline does not redefine them.

---

## Hierarchy Position

```
Architecture Principles   ← constitutional root (frozen)
        ↓
Object Model             ← frozen v1.0
        ↓
Workflow Model           ← this document (freeze candidate)
        ↓
Constitutions            ← domain-level constitutional documents
        ↓
Runtime
        ↓
Implementation
```

The Workflow Model is **above** Constitutions. Constitutions may refine the workflow for their domain, but may not contradict it.

---

## Principles Applied

This document conforms to the [Architecture Principles](00_ARCHITECTURE_PRINCIPLES.md) and respects the [Object Model](01_OBJECT_MODEL.md):

- **P1 — Reality First**: The workflow models how research actually progresses, not a simplified sequence.
- **P2 — Evidence First**: Every stage has evidence gates; conclusions cannot advance without provenance.
- **P3 — Evolution First**: Every transition is reversible; Objects can be re-examined at later stages.
- **P4 — Knowledge Accumulation**: The pipeline feeds durable Knowledge; nothing is consumed.
- **P5 — Traceability**: Each transition preserves the chain Source → Evidence → Signal → Research → Thesis → Knowledge.
- **P6 — Research Before Decision**: The workflow produces research artifacts; it does not produce decisions.
- **P7 — Human Judgment**: Gates may require human review; the workflow supports but does not replace it.
- **P8 — Composable Objects**: The workflow operates on loosely coupled Objects; a failure at one stage does not invalidate downstream Objects.
- **P9 — Evolution over Prediction**: The workflow accumulates understanding; it does not race to forecast.
- **P10 — Incremental Evolution**: New stages may be added by extending the workflow, not by replacing it.

---

## Cardinality

Cardinality is declared explicitly to avoid implicit assumptions.

| Stage | Input Cardinality | Output Cardinality |
|---|---|---|
| **1. Source Observation** | 1 Source | 0..N Candidate observations |
| **2. Evidence Production** | 1..N Candidate observations | 0..1 Evidence per candidate (typically 1:1) |
| **3. Signal Extraction** | 1..N Evidence | 0..N Signals per Evidence (typically 1:1) |
| **4. Research Synthesis** | 1..N Signals + 1 Entity | 0..1 Research per (Entity, question) |
| **5. Thesis Update** | 1 Research + 0..1 existing Thesis | 1 Thesis (new, updated, or supersession pair) |
| **6. Knowledge Update** | 1 Thesis | 1 Knowledge update (cumulative) |

### Cardinality Notes

- **One Evidence can ground many Signals.** If an Evidence object contains multiple discrete claims, each may become a separate Signal.
- **Many Signals aggregate into one Research.** A Research object is per question per Entity; multiple questions on one Entity produce multiple Research objects.
- **One Research crystallizes into one Thesis** (or none). Research that does not crystallize is still retained.
- **Supersession produces a pair.** When a Thesis is superseded, both the old (now `superseded`) and the new Thesis exist; the pair is the output.
- **Knowledge is cumulative.** There is no "old Knowledge" being replaced; Knowledge accumulates indefinitely.

---

## The Core Pipeline

```
┌─────────┐
│ Source  │  external origin
└────┬────┘
     │ Stage 1 — Source Observation
     ▼
┌─────────────┐
│  Candidate  │  raw information unit
│ observation │
└────┬────┘
     │ Stage 2 — Evidence Production
     ▼
┌─────────┐
│Evidence │  immutable, with provenance
└────┬────┘
     │ Stage 3 — Signal Extraction
     ▼
┌─────────┐
│ Signal  │  discrete, evidenced change
└────┬────┘
     │ Stage 4 — Research Synthesis
     ▼
┌──────────┐
│ Research │  coherent investigation
└────┬─────┘
     │ Stage 5 — Thesis Update
     ▼
┌─────────────────┐
│ Thesis Update   │  new or evolved
└────┬────────────┘
     │ Stage 6 — Knowledge Update
     ▼
┌──────────────────────┐
│ Knowledge Update     │  accumulated corpus
└──────────────────────┘
```

The pipeline is **linear and forward**. Each stage produces the input to the next. Objects do not move backward — but they can be superseded by newer Objects of the same type.

---

## Stages

Each stage has five facets: Input Objects, Output Objects, Responsibilities, **Gates**, and Failure Paths.

A **Gate** is a named, testable condition that an Object must pass to advance. Gates are atomic: they either pass or fail. They are deterministic within a given snapshot of the world.

A **Failure Path** is the destination of an Object that fails its Gate. Failure paths are part of the workflow definition — not exceptions to it.

### Stage 1 — Source Observation

#### Input Objects

- **Source** (one): an external origin of information

#### Output Objects

- **Candidate observations** (zero or more per Source): raw information units extracted from the Source

#### Responsibilities

- Detect that a Source has produced new information since the last observation.
- Extract candidate information units from the Source content.
- Tag each candidate with the Source identifier and an initial timestamp.
- Record Source health indicators (reachability, latency).

The stage does **not** interpret information. It captures what is there.

#### Gates

| Gate ID | Validates | Success Condition | Failure Condition | Reject Path | Retry Path |
|---|---|---|---|---|---|
| S1-G1 Source Reachability | Source is accessible | HTTP 2xx response within timeout | Timeout, 4xx (auth), 5xx after retries | Source marked `degraded`; cycle skips this Source | Next scheduled cycle |
| S1-G2 Content Retrievability | Content is extractable | Content successfully parsed | Parse failure, empty body, encoding error | Cycle logs failure; observation skipped | Manual: Source config update |
| S1-G3 Timestamp Plausibility | Source timestamp is sensible | Timestamp within plausible window (e.g., last 7 days for active Sources) | Future timestamp, implausibly old | Candidate logged with `timestamp_anomaly: true` flag | Manual review of Source clock |

**Failure outcome for Stage 1**: The cycle proceeds for other Sources; the failed Source is recorded as degraded or skipped. No upstream state is corrupted.

---

### Stage 2 — Evidence Production

#### Input Objects

- **Candidate observations**: from Stage 1
- **Source** (carried through): the originating Source

#### Output Objects

- **Evidence** (zero or one per candidate): an immutable, retrievable information unit with provenance and quality

#### Responsibilities

- Package each candidate observation as an Evidence object.
- Record full provenance: which Source, when retrieved, in what form.
- Record quality metadata: source reliability, content completeness, retrieval confidence.
- Preserve the original information content verbatim.

Evidence is **immutable**. Once produced, Evidence is never edited, rewritten, or reinterpreted.

#### Gates

| Gate ID | Validates | Success Condition | Failure Condition | Reject Path | Retry Path |
|---|---|---|---|---|---|
| S2-G1 Source Attribution | Evidence references a Source | At least one Source linked | No Source linked | Candidate rejected (logged) | Manual: add attribution, re-run |
| S2-G2 Content Preservation | Evidence matches Source content | Content matches verbatim | Content altered or corrupted | Candidate rejected; Source integrity investigation | After investigation: re-capture if Source was correct |
| S2-G3 Quality Recorded | Quality metadata populated | All required quality fields present | Missing required fields | Candidate rejected | Manual: complete quality metadata |
| S2-G4 Retrievability | Evidence can be retrieved by reference | Reference resolves within timeout | Reference cannot be resolved | Evidence marked `non_retrievable`; excluded from Signal grounding (still retained per Object Model lifecycle) | Manual: fix retrieval; Evidence's retrievability flag may update |

**Failure outcome for Stage 2**: A rejected candidate does not become Evidence. Its raw information is logged but not promoted. No downstream stage is affected.

---

### Stage 3 — Signal Extraction

#### Input Objects

- **Evidence** (one or more): immutable grounding material
- **Entity** (reference): the Entity the Evidence concerns

#### Output Objects

- **Signal** (zero or more per Evidence grouping): a discrete, evidenced observation about an Entity

#### Responsibilities

- Examine Evidence for discrete, falsifiable claims about an Entity.
- Construct a Signal: the claim, the direction, the horizon, the grounding Evidence.
- Resolve the Entity reference (the Evidence must clearly refer to a known Entity).
- Tag the Signal with its type per the Signal Taxonomy.

#### Gates

| Gate ID | Validates | Success Condition | Failure Condition | Reject Path | Retry Path |
|---|---|---|---|---|---|
| S3-G1 Entity Resolution | Evidence refers to a known Entity | Entity resolves to a known Entity (exact or fuzzy ≥ 0.85) | Entity not recognized or fuzzy match < 0.85 | Evidence retained; no Signal produced | When entity resolution improves (new Entity added to master) |
| S3-G2 Evidence Grounding | Signal is grounded by Evidence | ≥1 Evidence object grounds the Signal | No Evidence (invariant — cannot occur if Evidence is the input) | N/A | N/A |
| S3-G3 Falsifiability | Signal's claim is refutable | Claim is specific and verifiable | Claim is vague, generic, or opinion | Evidence retained; no Signal produced | With more specific Evidence or refined claim |
| S3-G4 Distinct Event | Signal represents a discrete change | Claim describes a specific event, transition, or new state | Claim is background noise, repetition, or generic | Evidence retained; no Signal produced | When event-detection criteria improve |

**Failure outcome for Stage 3**: Evidence remains in the record. No Signal is produced. The Evidence can be re-examined by future Signal Extraction (e.g., when Entity resolution improves).

---

### Stage 4 — Research Synthesis

#### Input Objects

- **Signals** (one or more): already-verified observations
- **Entity** (reference): the Entity under investigation
- **Research question** (implicit or explicit): what is being investigated

#### Output Objects

- **Research** (zero or one per investigation): a coherent investigation synthesizing Signals into intermediate understanding

#### Responsibilities

- Group related Signals around a coherent investigation.
- Weight Evidence quality across the aggregated Signals.
- Identify patterns, causal links, and durable interpretations.
- Produce structured Research output: significance, causality, durability, reversibility, precedents.

#### Gates

| Gate ID | Validates | Success Condition | Failure Condition | Reject Path | Retry Path |
|---|---|---|---|---|---|
| S4-G1 Question Coherence | Signals relate to a single question | Single coherent question identified | Signals scattered across multiple questions | Signals retained; no Research produced | When question is clarified, or Signals are split |
| S4-G2 Sufficient Signals | Question has enough Signal support | ≥1 Signal (recommendation: ≥3 for meaningful Research) | <1 Signal | Signals retained; no Research produced | When more Signals arrive |
| S4-G3 Entity Context | Entity context is available | Entity recognized; context loaded | Entity context missing or partial | Signals retained; Research held | When entity context becomes available |
| S4-G4 Evidence Traceability | Conclusions trace to Evidence | All Research conclusions traceable to Signals → Evidence | Some conclusions have no traceable Evidence | Research produced but flagged `traceability_gaps`; Signals retained | Manual: complete the trace |

**Failure outcome for Stage 4**: Signals remain available. Research is either not produced (Question Coherence, Sufficient Signals failures) or held (Entity Context failure) or flagged (Traceability failure). Signals can be re-examined when conditions change.

---

### Stage 5 — Thesis Update

#### Input Objects

- **Research** (new): a completed or in-progress investigation
- **Thesis** (optional, existing): a prior Thesis on the same Entity that the new Research may update, support, or contradict

#### Output Objects

- **Thesis** (exactly one): the result of the update — either evolved, new, or a supersession pair (new + predecessor marked superseded)

A Thesis is never destroyed. Superseded Theses remain in the record as history.

#### Responsibilities

- Crystallize Research into a coherent interpretation.
- Compare the new Research against any existing Thesis on the same Entity.
- Decide between the three paths: **Evolve**, **Supersede**, or **Hold** (see Update Rules below).
- Record every state transition with timestamp, responsible Research, and rationale.

#### Gates

| Gate ID | Validates | Success Condition | Failure Condition | Reject Path | Retry Path |
|---|---|---|---|---|---|
| S5-G1 Interpretation Coherence | Thesis articulates a single interpretation | Single coherent interpretation | Multiple conflicting interpretations | Research retained; no Thesis produced | When interpretation is clarified |
| S5-G2 Falsifiability | Thesis is refutable | Refutation criteria identifiable | Thesis is unfalsifiable | Research retained; no Thesis produced | With refutation criteria added |
| S5-G3 Entity Recognition | Thesis refers to known Entities | All Entities recognized | Some Entities unrecognized | Research retained; Thesis held | When Entities are added to master |
| S5-G4 Research Grounding | Thesis is supported by Research | ≥1 Research object | No Research support (invariant — cannot occur if Research is the input) | N/A | N/A |

**Failure outcome for Stage 5**: Research remains available. Thesis is either not produced (Coherence, Falsifiability failures) or held (Entity Recognition failure). Research can be re-examined.

---

### Stage 6 — Knowledge Update

#### Input Objects

- **Thesis** (new or updated): a mature interpretation
- **Knowledge** (existing): the accumulated corpus

#### Output Objects

- **Knowledge** (updated): the corpus after integration

#### Responsibilities

- Integrate the Thesis into the accumulated Knowledge.
- Connect the Thesis to related Theses, Research, Signals, and Evidence.
- Update retrieval structures: indexes, cross-references, navigation.
- Preserve the Thesis's history (every evolution, every Research that contributed).

#### Gates

| Gate ID | Validates | Success Condition | Failure Condition | Reject Path | Retry Path |
|---|---|---|---|---|---|
| S6-G1 Thesis Maturity | Thesis is stable enough to integrate | Thesis meets maturity criteria (see OQ-6) | Thesis still volatile or under active revision | Thesis recorded as `pending_integration` | When Thesis matures |
| S6-G2 Traceability Preservation | Links from Thesis back to Evidence remain intact | All links valid | Some links broken | Integration held; Thesis remains pending | When broken links are restored |
| S6-G3 Structure Consistency | Knowledge structure remains coherent | No circular refs, no orphaned nodes, no schema conflicts | Structural conflicts detected | Integration held; Thesis remains pending | When structure is repaired |

**Failure outcome for Stage 6**: Knowledge is unchanged. Thesis is recorded with `pending_integration` status. The Thesis is held until the gate passes.

---

## Failure Path Summary

Every Gate failure has a defined destination. The pipeline never silently drops Objects.

### Reject Path Destinations

| Destination | Meaning | Used By |
|---|---|---|
| **Reject** | Object is not promoted; original is discarded or logged | Stages 2, 3, 4, 5 |
| **Hold** | Object is preserved but not advanced; awaits better conditions | Stages 4, 5 |
| **Pending** | Object is preserved and tracked for future integration | Stage 6 |
| **Degraded** | Source is marked unhealthy; subsequent cycles skip it | Stage 1 |

### Per-Object Failure Outcomes

| Object | If Gate Fails | Object's Final Status |
|---|---|---|
| **Candidate observation** | Rejected | Discarded (raw info logged, not promoted) |
| **Evidence** (failed gate in S2) | Rejected | Not produced; candidate logged |
| **Evidence** (failed S2-G4 only) | Marked `non_retrievable` | Retained per Object Model lifecycle; excluded from Signal grounding |
| **Signal** | Rejected | Not produced; Evidence retained |
| **Research** | Rejected or Held | Not produced; Signals retained |
| **Research** (failed S4-G4 only) | Flagged `traceability_gaps` | Produced but flagged; Signals retained |
| **Thesis** | Rejected or Held | Not produced; Research retained |
| **Thesis (pending)** | Held | Recorded with `pending_integration`; Knowledge unchanged |
| **Knowledge** | Held | Unchanged; pending Thesis awaiting |

### Retry Eligibility

| Gate | Retry Trigger |
|---|---|
| S1-G1 Source Reachability | Next scheduled cycle |
| S1-G2 Content Retrievability | Manual Source config fix |
| S1-G3 Timestamp Plausibility | Manual review of Source clock |
| S2-G1 Source Attribution | Manual attribution correction |
| S2-G2 Content Preservation | After Source integrity investigation |
| S2-G3 Quality Recorded | Manual metadata completion |
| S2-G4 Retrievability | Manual retrieval mechanism fix |
| S3-G1 Entity Resolution | New Entity added to master |
| S3-G3 Falsifiability | New Evidence or refined claim |
| S3-G4 Distinct Event | Improved event-detection criteria |
| S4-G1 Question Coherence | Question clarified; Signals split |
| S4-G2 Sufficient Signals | New Signals arrive |
| S4-G3 Entity Context | Context becomes available |
| S4-G4 Traceability | Manual trace completion |
| S5-G1 Interpretation Coherence | Interpretation clarified |
| S5-G2 Falsifiability | Refutation criteria added |
| S5-G3 Entity Recognition | Entity added to master |
| S6-G1 Thesis Maturity | Thesis matures (see OQ-6) |
| S6-G2 Traceability Preservation | Links restored |
| S6-G3 Structure Consistency | Structure repaired |

---

## Workflow Gate Table (Consolidated)

The complete gate inventory across all six stages:

| Stage | Gate | Purpose | Reject Path |
|---|---|---|---|
| 1 | S1-G1 Source Reachability | Source is accessible | Source `degraded` |
| 1 | S1-G2 Content Retrievability | Content extractable | Cycle skips |
| 1 | S1-G3 Timestamp Plausibility | Timestamp sensible | Flag for review |
| 2 | S2-G1 Source Attribution | Source linked | Candidate rejected |
| 2 | S2-G2 Content Preservation | Content intact | Candidate rejected + investigation |
| 2 | S2-G3 Quality Recorded | Metadata complete | Candidate rejected |
| 2 | S2-G4 Retrievability | Reference resolves | Evidence `non_retrievable` |
| 3 | S3-G1 Entity Resolution | Entity known | Evidence retained, no Signal |
| 3 | S3-G2 Evidence Grounding | ≥1 Evidence (invariant) | N/A |
| 3 | S3-G3 Falsifiability | Claim refutable | Evidence retained, no Signal |
| 3 | S3-G4 Distinct Event | Specific change | Evidence retained, no Signal |
| 4 | S4-G1 Question Coherence | Single question | Signals retained, no Research |
| 4 | S4-G2 Sufficient Signals | ≥1 Signal (rec. ≥3) | Signals retained, no Research |
| 4 | S4-G3 Entity Context | Context available | Signals retained, Research held |
| 4 | S4-G4 Evidence Traceability | Conclusions traceable | Research flagged `traceability_gaps` |
| 5 | S5-G1 Interpretation Coherence | Single interpretation | Research retained, no Thesis |
| 5 | S5-G2 Falsifiability | Thesis refutable | Research retained, no Thesis |
| 5 | S5-G3 Entity Recognition | Entities known | Research retained, Thesis held |
| 5 | S5-G4 Research Grounding | ≥1 Research (invariant) | N/A |
| 6 | S6-G1 Thesis Maturity | Thesis stable | Thesis `pending_integration` |
| 6 | S6-G2 Traceability Preservation | Links intact | Thesis `pending_integration` |
| 6 | S6-G3 Structure Consistency | Structure coherent | Thesis `pending_integration` |

**Total gates:** 23 (4 of which are invariants that cannot fail by construction: S3-G2, S5-G4, plus two conceptual placeholders).

---

## Failure Path Diagram

The complete failure-path flow for the pipeline:

```
                    Stage 1 — Source Observation
                    ┌─────────────────────────┐
                    │ S1-G1: fail → Source    │
                    │       `degraded`        │
                    │ S1-G2: fail → skip       │
                    │ S1-G3: fail → flag       │
                    └────────────┬────────────┘
                                 │ pass
                                 ▼
                    Stage 2 — Evidence Production
                    ┌─────────────────────────┐
                    │ S2-G1/2/3: fail →       │
                    │   Candidate rejected     │
                    │   (logged, discarded)    │
                    │ S2-G4: fail → Evidence   │
                    │   `non_retrievable`      │
                    └────────────┬────────────┘
                                 │ pass
                                 ▼
                    Stage 3 — Signal Extraction
                    ┌─────────────────────────┐
                    │ S3-G1: fail → Evidence   │
                    │   retained, no Signal    │
                    │ S3-G3: fail → Evidence   │
                    │   retained, no Signal    │
                    │ S3-G4: fail → Evidence   │
                    │   retained, no Signal    │
                    └────────────┬────────────┘
                                 │ pass
                                 ▼
                    Stage 4 — Research Synthesis
                    ┌─────────────────────────┐
                    │ S4-G1: fail → Signals    │
                    │   retained, no Research  │
                    │ S4-G2: fail → Signals    │
                    │   retained, no Research  │
                    │ S4-G3: fail → Signals    │
                    │   retained, Research held│
                    │ S4-G4: fail → Research   │
                    │   flagged `traceability_ │
                    │   gaps` (still produced) │
                    └────────────┬────────────┘
                                 │ pass
                                 ▼
                    Stage 5 — Thesis Update
                    ┌─────────────────────────┐
                    │ S5-G1: fail → Research  │
                    │   retained, no Thesis    │
                    │ S5-G2: fail → Research  │
                    │   retained, no Thesis    │
                    │ S5-G3: fail → Research  │
                    │   retained, Thesis held  │
                    └────────────┬────────────┘
                                 │ pass
                                 ▼
                    Stage 6 — Knowledge Update
                    ┌─────────────────────────┐
                    │ S6-G1: fail → Thesis     │
                    │   `pending_integration`  │
                    │ S6-G2: fail → Thesis     │
                    │   `pending_integration`  │
                    │ S6-G3: fail → Thesis     │
                    │   `pending_integration`  │
                    └────────────┬────────────┘
                                 │ pass
                                 ▼
                              Knowledge
                              (integrated)
```

### Failure-Path Rule

> Every Gate failure has a defined destination. No Object is silently dropped. Rejected Objects may be discarded (raw candidates) or preserved with reduced status (Evidence, Signals, Research, Thesis).

---

## Workflow Diagram (Complete)

The full logical flow, including the three Thesis-update paths and the alternative Knowledge-uptake path:

```
                              ┌─────────────────┐
                              │     Source      │
                              │  (external)     │
                              └────────┬────────┘
                                       │ Stage 1
                                       ▼
                              ┌─────────────────┐
                              │   Candidate     │
                              │  observation    │
                              └────────┬────────┘
                                       │ Stage 2
                                       ▼
                       ┌─── Evidence (immutable) ───┐
                       │   with provenance + quality │
                       └────────────┬───────────────┘
                                    │ Stage 3
                                    ▼
                        ┌─── Signal (verified) ────┐
                        │  claim + Evidence + ...  │
                        └────────────┬─────────────┘
                                     │ Stage 4
                                     ▼
                          ┌── Research (coherent) ──┐
                          │  causal analysis + ...   │
                          └────────────┬─────────────┘
                                       │ Stage 5
            ┌──────────────────────────┼──────────────────────────┐
            │                          │                          │
       Path A (Evolve)         Path B (Supersede)         Path C (Hold)
            │                          │                          │
            ▼                          ▼                          ▼
      ┌───────────┐          ┌─────────────────┐         ┌─────────────────┐
      │  Thesis   │◄─────────│   New Thesis    │         │  Thesis         │
      │ (evolved) │          │  (predecessor   │         │ (unchanged)     │
      │           │          │   superseded)   │         │  + open question│
      └─────┬─────┘          └────────┬────────┘         └────────┬────────┘
            │                          │                          │
            └──────────────────────────┼──────────────────────────┘
                                       │ Stage 6
                                       ▼
                              ┌─────────────────┐
                              │    Knowledge    │
                              │ (cumulative)    │
                              └─────────────────┘
```

---

## Object Transition Table

| From | To | Stage | Trigger | Cardinality | Gate | Failure Path |
|---|---|---|---|---|---|---|
| Source | Candidate observation | 1 | New content in Source | 1 → 0..N | S1-G1, G2, G3 | Degraded / Skip / Flag |
| Candidate | Evidence | 2 | Information stable | 1 → 0..1 | S2-G1, G2, G3, G4 | Reject (logged) or `non_retrievable` |
| Evidence | Signal | 3 | Discrete change detected | 1..N → 0..N | S3-G1, G3, G4 | Evidence retained |
| Signal | Research | 4 | Coherent question | 1..N → 0..1 | S4-G1, G2, G3, G4 | Signals retained / Research held / flagged |
| Research | Thesis | 5 | Crystallization | 1 (+ 0..1 prior) → 1 | S5-G1, G2, G3 | Research retained / Thesis held |
| Thesis | Knowledge | 6 | Maturity | 1 → 1 (cumulative) | S6-G1, G2, G3 | Thesis `pending_integration` |

---

## Update Rules

### Rule 1 — New Signal Handling

A Signal enters the system via Stage 3.

1. The Signal is created in `draft` status with full Evidence grounding.
2. Validation gates run. If any gate fails, the Signal is not produced; the Evidence remains available.
3. If the Signal passes gates, it advances to `verified` status and becomes a candidate for Research.
4. The Signal is **never consumed**. After integration into Research, it persists in the record with a reference to the Research that used it.

### Rule 2 — Existing Thesis Update

When new Research arrives for an Entity that already has a Thesis:

- **Path A — Evolve**: New Research supports, refines, or partially qualifies the existing Thesis → Thesis updated; evolution recorded.
- **Path B — Supersede**: New Research invalidates the existing Thesis → existing Thesis marked `superseded`; new Thesis created. Predecessor's full history preserved.
- **Path C — Hold**: New Research is relevant but inconclusive → Research recorded as associated; Thesis unchanged; open question annotated.

### Rule 3 — Conflicting Research

When two Research objects reach different conclusions about the same Entity:

1. **Both Research objects are retained.** Conflicts are not erased.
2. The conflict is recorded as a relationship between the two Research objects.
3. The Thesis stage considers the conflict: integrate if possible, coexist if not.
4. **Multiple Theses may coexist** on the same Entity, each with a clearly bounded perspective.
5. The Knowledge structure records the conflict and the multiple Theses.

### Rule 4 — Knowledge Accumulation

1. **Growth.** Knowledge grows by adding Theses. Each Thesis is integrated once mature.
2. **Reorganization.** Knowledge may be reorganized; structure grows, content never shrinks.
3. **Preservation on retirement.** Superseded Theses remain queryable as historical record.
4. **No forgetting.** Knowledge is never reduced.
5. **Structure over volume.** Architecture favors cross-references and hierarchies over raw accumulation.

---

## Runtime Boundary

The Runtime layer **executes** the workflow defined here. It must not:

- **Redefine workflow logic.** Stages, gates, cardinalities, and failure paths are fixed by this document.
- **Introduce new stages.** New stages require a Workflow Model amendment.
- **Skip gates.** Every Gate defined here must be evaluated by Runtime.
- **Change failure paths.** Where an Object goes on failure is fixed by this document.
- **Override Object Model rules.** Rejected-but-retained Objects (e.g., Evidence without Signal) follow the Object Model's lifecycle rules, not Runtime's preferences.

Runtime is responsible for:

- **Executing** the gates defined here, in order.
- **Recording** the outcome of each gate (pass/fail).
- **Routing** Objects to their failure-path destination on gate failure.
- **Persisting** Objects per the Object Model's lifecycle rules.
- **Retrying** per the retry paths defined here.

Any change to the workflow — including new gates, removed gates, modified failure paths, or altered cardinalities — must be proposed through the Workflow Model amendment process (per [ARCHITECTURE_GOVERNANCE.md](ARCHITECTURE_GOVERNANCE.md)).

---

## Open Questions Before Runtime

These questions block Runtime design but not Workflow Model freeze.

### OQ-1 — Thesis Update Path Decision Logic

How is the choice between Path A (Evolve), Path B (Supersede), Path C (Hold) made?

- Human-driven (curator): requires intervention point at Stage 5.
- Automated (criteria): requires explicit thresholds for "invalidate" vs. "refine".
- Hybrid: likely needed.

### OQ-2 — Timing and Ordering

How does the workflow handle out-of-order arrivals, lagging Research, or late Evidence?

- Are there ordering guarantees?
- How is retroactive Evidence handled?

### OQ-3 — Reverse Edges and Re-examination

How does the system support revisiting earlier stages?

- New workflows vs. loops within this one?
- Cost-bounded re-examination?

### OQ-4 — Batch vs. Streaming

Does the pipeline operate in batches or as a stream?

- Batch: simpler gates, more latency.
- Streaming: less latency, consistency issues.

### OQ-5 — Macro-Level Signals

How do industry/sector-level Signals enter the pipeline?

- Aggregated from Company-level, or independent entry?
- Per Object Model Decision 2: Industry is an Entity.

### OQ-6 — Thesis Maturity Trigger

What defines "mature" for Stage 6?

- Time-based? (Simple but arbitrary.)
- Stability-based? (Requires stability definition.)
- Curator-driven? (Conservative, human-in-loop.)

### OQ-7 — Conflict Surfacing Cadence

How are Thesis conflicts surfaced to humans?

- Without explicit surfacing, conflicts accumulate silently.

### OQ-8 — Concurrent Thesis Updates

How does the system handle concurrent updates to the same Thesis?

- Race conditions? Last-write-wins? Explicit locking?

### OQ-9 — Conflicting Source Evidence

When multiple Sources produce conflicting Evidence about the same event, which is canonical?

- Source priority? Time-of-arrival? Reliability score?

### OQ-10 — Retroactive Corrections

How does the system handle a Source publishing a correction after Evidence has already been captured?

- New Evidence (a "correction Signal") that supersedes the prior?
- Audit-only flag?

### OQ-11 — Lifecycle of `non_retrievable` Evidence

How long is Evidence that failed S2-G4 retained?

- Forever (audit)? Until Sources fixed? Configurable TTL?

### OQ-12 — Reject vs. Delete Semantics

The workflow uses "Reject" as a destination. Is this equivalent to deletion?

- Per Object Model: nothing is deleted.
- Therefore "Reject" for Evidence, Signals, Research, Thesis means **status change**, not deletion.
- Candidates (Stage 1–2) are raw, not objects; they can be discarded.
- Confirmation needed: Reject = status change for Objects, discard for raw candidates.

---

## Version History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-18 | Freeze Candidate: added explicit Gates (23 total), Failure Paths, Cardinality rules, Runtime Boundary, and 5 additional Open Questions |
| 0.1 | 2026-07-18 | Initial draft for review |
