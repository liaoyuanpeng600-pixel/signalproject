# Object Model

> **Document role:** Defines the abstract vocabulary of the SIGNAL research system. Establishes the core objects, their responsibilities, their relationships, and their lifecycles. Sits between the Architecture Principles and the domain-specific Constitutions.
>
> Constitutions may refine or specialize these objects. Constitutions may not contradict them.

---

## Document Metadata

| Field | Value |
|---|---|
| **Status** | Frozen |
| **Version** | 1.0 |
| **Effective Date** | 2026-07-18 |
| **Next Review** | TBD |
| **Owner** | Architecture |

> **Note.** This document is the abstract layer below the Architecture Principles. It does not define schemas, fields, storage, APIs, prompts, or runtime concerns. Those belong to lower layers.

---

## Purpose

The Object Model defines the core vocabulary of the research system.

It answers four questions:

- **What kinds of things exist?** — the object types.
- **What is each kind for?** — the responsibility of each.
- **How do they relate?** — the relationships between them.
- **How do they live and die?** — the lifecycle of each.

Every Constitution in the repository builds on these objects. No Constitution may introduce a new core object type; new objects extend the model only through the process defined in [ARCHITECTURE_GOVERNANCE.md](ARCHITECTURE_GOVERNANCE.md).

---

## Hierarchy Position

```
Architecture Principles   ← constitutional root (frozen)
        ↓
Object Model             ← this document (frozen v1.0)
        ↓
Constitutions            ← domain-level constitutional documents
        ↓
Workflow
        ↓
Runtime
        ↓
Implementation
```

Lower layers may refine these objects. They may not contradict them.

---

## Principles Applied

This document conforms to the [Architecture Principles](00_ARCHITECTURE_PRINCIPLES.md). Each Principle shapes the Object Model:

- **P1 — Reality First**: Objects model real-world things, not abstractions imposed for convenience.
- **P2 — Evidence First**: Conclusions are objects grounded by Evidence, never by opinion.
- **P3 — Evolution First**: Every object is living. Every object has a lifecycle.
- **P4 — Knowledge Accumulation**: Objects exist to support accumulation. Transient objects (like Signals) feed durable objects (like Theses).
- **P5 — Traceability**: Objects participate in the chain Source → Evidence → Signal → Research → Thesis → Knowledge.
- **P6 — Research Before Decision**: Objects support research. They do not encode decisions.
- **P7 — Human Judgment**: Objects augment human reasoning, never replace it.
- **P8 — Composable Objects**: Objects are loosely coupled. New object types can be added without redesign.
- **P9 — Evolution over Prediction**: Objects exist to refine understanding, not to forecast.
- **P10 — Incremental Evolution**: New objects extend the model; they do not replace existing ones.

---

## Resolved Architectural Decisions

The following decisions were made during freeze. They are part of the v1.0 contract.

### Decision 1 — Entity Subtype Strategy

**Resolution.** Entity is a single abstract type in this Object Model. Constitutions MAY introduce **Entity refinements** (specific kinds of Entity) as needed; refinements do not become new core types.

**Rationale.** Per P10 (Incremental Evolution), the Object Model should not pre-enumerate subtypes. Premature commitment to a subtype list would force Constitutions to fit into fixed categories. Refinements stay local to the Constitution that introduces them.

**Examples of acceptable refinements** (not exhaustive):
- `Company` — refinement of Entity, introduced in [12_company_schema.md](../12_company_schema.md)
- `Industry` — refinement of Entity, introduced in [11_industry_mapping.md](../11_industry_mapping.md) (see Decision 2)
- Sector, jurisdiction, asset class — refinements where needed

### Decision 2 — Industry Is an Entity (with chains as relations)

**Resolution.** An Industry is an Entity — specifically, a **grouping Entity** whose purpose is to group other Entities. Industry chains are relations between Entities (Companies and Industries).

**Rationale.** Industries receive Signals (e.g., "EU semiconductor inventory days rose to 92"). A Signal subject must be an Entity. Industries also group Companies via relations. Modeling Industry as an Entity reconciles both observations while keeping the abstraction simple.

**Implication.** [11_industry_mapping.md](../11_industry_mapping.md) defines Industry as an Entity refinement and chains as relations between Entities. The doc remains structurally valid; only its relationship to the Object Model needs to be made explicit.

### Decision 3 — Watchlist Is a View, Not an Object

**Resolution.** The Watchlist is a **View over Entities** — a query with selection criteria (tier, coverage targets, curator intent). It is not an Object in this Model.

**Rationale.** A Watchlist does not have its own evidence, lifecycle, or research arc. It is operational selection criteria applied to Entities. Modeling it as an Object would add a category that contributes nothing to the research system.

**Implication.** [14_watchlist.md](../14_watchlist.md) is a Workflow-layer document. It describes a query plus selection criteria, not a new object type. No Object Model change required; the doc remains valid.

### Decision 4 — Reports Are Views, Not Objects

**Resolution.** Reports (Daily Brief, Weekly Review, Per-Entity Brief) are **Views** over Signals, ThesisDeltas, and Knowledge. They are rendered output, not first-class research objects.

**Rationale.** Reports do not have evidence, do not evolve through reasoning, and do not accumulate into Knowledge. They are the system's output for human consumption.

**Implication.** [13_report_template.md](../13_report_template.md) defines rendering rules for Views. `Cluster` and `ThesisDelta` (referenced in [13](../13_report_template.md) and [01](../01_signal_constitution.md)) are **runtime aggregates** of Signals — operational groupings used to render Reports, not Object Model types.

### Decision 5 — Defer Pattern, Question, Hypothesis

**Resolution.** Pattern, Question, and Hypothesis are **not** promoted to the Object Model in v1.0. They are deferred until concrete evidence justifies their inclusion.

**Rationale.** Per P10 (Incremental Evolution), adding object types without demonstrated need expands the conceptual surface and increases reconciliation cost. None of these three concepts appears with sufficient frequency or clarity in current Constitutions to warrant promotion now.

**Implication.** If a future Constitution or workflow discovers the need for Pattern, Question, or Hypothesis as objects, the promotion path is: write an RFC, demonstrate the need, propose the addition via the [Object Model amendment process](ARCHITECTURE_GOVERNANCE.md). The Object Model does not commit to these types in v1.0.

---

## Core Objects

Seven core objects. Each is essential to the research system.

### 1. Entity

#### Definition

An Entity is anything in the world that research understanding can attach to.

A company, a sector, a regulator, a person, a country, a commodity, an industry, a question — any real-world actor, object, or concept — is an Entity.

Entities are not "data records." They are the system's view of the world.

#### Responsibility

Entities anchor the system to reality.

Every observation, every claim, every research question must ultimately refer to something. The Entity is that "something." Without Entities, the system floats in abstraction.

#### Relationships

- **Source → Entity** (implicit): Sources describe Entities.
- **Signal → Entity**: Signals claim something about an Entity.
- **Research → Entity**: Research investigates Entities.
- **Thesis → Entity**: Theses articulate interpretations about Entities.

An Entity may be the subject of any number of Signals, Research objects, and Theses. There is no fixed cardinality.

#### Refinements

Constitutions MAY introduce Entity refinements (specific kinds of Entity) without modifying this Object Model. Examples include Company, Industry, Sector, and others as needed.

#### Lifecycle

- **Recognition**: An Entity exists in the system when research understanding needs to refer to it. Entities are recognized, not invented.
- **Persistence**: An Entity persists as long as it remains relevant to active research.
- **Reclassification**: An Entity's classification (sector, jurisdiction, refinement type) may evolve as understanding deepens.
- **Retirement**: An Entity is retired when no active Research or Thesis references it.

Entities are never deleted; they are retired.

---

### 2. Source

#### Definition

A Source is an origin of information.

A news feed, a regulatory filing, an earnings call, a research report, a data provider, a survey — any channel through which information about the world enters the system.

Sources are external to the system. The system observes them; it does not modify them.

#### Responsibility

Sources make Evidence possible.

A Source is a candidate producer of Evidence. The system assigns no interpretation to a Source; interpretation happens at the Evidence and Signal level.

#### Relationships

- **Source → Evidence**: Sources produce Evidence. Each Evidence object is attributed to one or more Sources.
- **Source → Entity** (implicit): Sources describe Entities through the Evidence they produce.

A Source is not itself Evidence. A Source may produce many Evidence objects. An Evidence originates from one or more Sources.

#### Lifecycle

- **Activation**: A Source becomes active when registered with the system and confirmed reachable.
- **Operation**: A Source is observed continuously while active.
- **Deactivation**: A Source is deactivated when its reliability declines or it is no longer accessible.
- **Retirement**: A Source is retired when no active Evidence references it.

The system records the quality and reliability of each Source over time. This metadata lives with the Evidence the Source produces, not with the Source itself.

---

### 3. Evidence

#### Definition

Evidence is a retrievable piece of information that supports a claim.

A quote, a paragraph, a data point, a chart, a measurement — any discrete information artifact that can be cited and retrieved.

Evidence is the only currency that grounds conclusions. Without Evidence, claims are speculation.

#### Responsibility

Evidence is the grounding layer of research.

Every Signal, every Research object, every Thesis ultimately refers to Evidence. Evidence is what makes conclusions auditable.

#### Relationships

- **Source → Evidence**: Evidence originates from one or more Sources.
- **Evidence → Signal**: Evidence grounds a Signal.
- **Evidence → Research**: Evidence supports a Research claim (directly or through Signals).
- **Evidence → Thesis**: Evidence grounds a Thesis.

Evidence is the only object that may directly reference a Source. Signals, Research, and Theses reference Sources only through Evidence.

#### Lifecycle

- **Capture**: Evidence is captured at the moment it is observed in a Source.
- **Preservation**: Once captured, Evidence is immutable. It is never edited, rewritten, or reinterpreted.
- **Quality recording**: The provenance and quality of Evidence are recorded at capture and never lost.
- **Retention**: Evidence is retained as long as any active conclusion references it.

Evidence quality is preserved alongside the Evidence itself. Stronger Evidence and weaker Evidence are never collapsed into a single indistinguishable form.

---

### 4. Signal

#### Definition

A Signal is a discrete, evidenced observation about an Entity.

A Signal is not a fact, not a forecast, and not an opinion. It is a record that something happened or something changed, with the Evidence to support that record.

A Signal is the atomic unit of observation.

#### Responsibility

Signals capture discrete changes in the world.

They are the points at which raw information becomes structured observation. Signals aggregate into Research; Research crystallizes into Theses.

#### Relationships

- **Signal → Entity**: Every Signal refers to one Entity.
- **Signal → Evidence**: Every Signal is grounded by at least one Evidence object.
- **Signal → Research**: Multiple Signals may be aggregated into a Research object.
- **Research → Thesis**: A Research object may crystallize into a Thesis.

A Signal does not directly reference a Source. It references Sources only through Evidence.

#### Lifecycle

- **Emergence**: A Signal emerges when an observation qualifies as a discrete, evidenced change.
- **Validation**: A Signal may be validated, qualified, or challenged by subsequent Signals.
- **Integration**: A Signal is integrated when it contributes to a Research object or Thesis.
- **Persistence**: A Signal persists in the record even after integration. It is not consumed.
- **Retirement**: A Signal is retired when it no longer informs any active Research or Thesis.

Signals are not transient in the system. They may be transient in importance, but the record persists.

---

### 5. Research

#### Definition

Research is an organized investigation into an Entity, sector, or question.

Research aggregates multiple Signals into a coherent intermediate understanding. It is the bridge between observation and interpretation.

Research is where the system does its analytical work: combining Signals, weighing Evidence, identifying patterns, drawing intermediate conclusions.

#### Responsibility

Research synthesizes observations into coherent analysis.

It answers questions like "what does the evidence say about this Entity?" or "what pattern is emerging across these Signals?"

Research produces intermediate conclusions that may — if they mature — become Theses.

#### Relationships

- **Research → Entity**: Every Research object refers to at least one Entity.
- **Research → Signal**: Research aggregates multiple Signals.
- **Research → Evidence**: Research grounds its claims in Evidence (directly or through Signals).
- **Research → Thesis**: Research may crystallize into a Thesis. A Thesis may generate new Research.

A Research object is more structured than a collection of Signals and less durable than a Thesis.

#### Lifecycle

- **Opening**: A Research object opens when a question is identified that requires structured investigation.
- **Ongoing**: Research accumulates Signals and Evidence as they arrive.
- **Conclusion**: Research concludes when its question is answered, abandoned, or superseded.
- **Extension**: Research may be extended by opening new questions on the same Entity.
- **Crystallization**: Research may crystallize into a Thesis when the understanding stabilizes.

Research is not consumed when it crystallizes into a Thesis. Both remain in the record. A Research object that produces no Thesis is still retained as a record of investigation.

---

### 6. Thesis

#### Definition

A Thesis is a living research object that articulates a coherent interpretation about an Entity, sector, or question.

A Thesis is the central organizing unit of research understanding. It is what the system "thinks" — continuously refined as new evidence arrives.

A Thesis is not a final answer. It is the system's current best interpretation, always open to revision.

#### Responsibility

Thesis organizes the system's understanding.

It is the level at which research understanding is integrated, evaluated, and communicated. Theses are what the system remembers, defends, and revises.

#### Relationships

- **Thesis → Entity**: Every Thesis refers to one or more Entities.
- **Thesis → Research**: A Thesis is supported by one or more Research objects.
- **Thesis → Signal**: A Thesis may reference specific Signals as illustrative evidence.
- **Thesis → Evidence**: A Thesis ultimately grounds its claims in Evidence.
- **Thesis ↔ Thesis**: Theses may support, contradict, refine, or supersede other Theses.

A Thesis is more durable than Research and more interpretive than Evidence.

#### Lifecycle

- **Emergence**: A Thesis emerges when Research stabilizes into a coherent interpretation.
- **Evolution**: A Thesis evolves continuously as new Evidence, Signals, and Research arrive. Every evolution is recorded.
- **Maturity**: A Thesis becomes mature when it has been stable for a meaningful period.
- **Supersession**: A Thesis is superseded when a better interpretation emerges.
- **Retirement**: A Thesis is retired when the Entity it addresses is no longer relevant.

A Thesis never "completes." It evolves, matures, or is superseded. Every state transition is recorded.

---

### 7. Knowledge

#### Definition

Knowledge is the accumulated, interconnected body of Theses, Research, Signals, and Evidence that the system retains over time.

Knowledge is the long-term output of the research system. It is what accumulates.

Knowledge is not a single object; it is the entire accumulated corpus. It is the system's memory.

#### Responsibility

Knowledge is the persistence layer of research understanding.

While individual Signals and Research objects may come and go, Knowledge is the substrate that compounds. Knowledge is what the system has learned.

#### Relationships

- **Knowledge ← Thesis**: Knowledge is composed of Theses.
- **Knowledge ← Research**: Knowledge includes the Research that produced its Theses.
- **Knowledge ← Signal**: Knowledge includes the Signals that informed its Research and Theses.
- **Knowledge ← Evidence**: Knowledge includes the Evidence that grounds its Theses.
- **Knowledge → Entity**: Knowledge is organized around Entities.

Knowledge is the only object that does not have a single instance. It is the sum of the rest, organized for retrieval and continued growth.

#### Lifecycle

- **Continuous accumulation**: Knowledge grows as new Theses are added.
- **Selective reorganization**: Knowledge may be reorganized when patterns emerge across Theses.
- **Selective forgetting**: When a Thesis is retired, its contribution to Knowledge is preserved in the Thesis's history. Knowledge itself does not lose content; it gains structure.

Knowledge has no end state. It accumulates until the system ends.

---

## Operational Concepts (Not Objects)

The following concepts appear in existing Constitutions but are **not** Object Model types. They are Views, runtime aggregates, or operational concepts.

| Concept | Status | Defined in |
|---|---|---|
| **Watchlist** | View over Entities | [14_watchlist.md](../14_watchlist.md) |
| **Report** (Daily, Weekly, Per-Entity) | View over Signals/ThesisDeltas | [13_report_template.md](../13_report_template.md) |
| **Cluster** | Runtime aggregate over Signals | [01_signal_constitution.md](../01_signal_constitution.md), [13_report_template.md](../13_report_template.md) |
| **ThesisDelta** | Runtime aggregate over Signals | [04_data_schema.md](../04_data_schema.md), [13_report_template.md](../13_report_template.md) |
| **Cycle / CycleReport** | Runtime artifact | [03_workflow_constitution.md](../03_workflow_constitution.md), [08_architecture.md](../08_architecture.md) |
| **Agent** | Workflow component | [02_agent_constitution.md](../02_agent_constitution.md) |
| **Score** | Signal metadata, not an object | [06_scoring_framework.md](../06_scoring_framework.md) |
| **OverrideRecord** | Signal metadata, not an object | [04_data_schema.md](../04_data_schema.md) |

These are operational concerns, not first-class research objects. They are valid in their respective Constitutions and must not be promoted to Object Model status without going through the [amendment process](ARCHITECTURE_GOVERNANCE.md).

---

## Object Relationships

```
            Source
              │
              ▼ produces
            Evidence
              │
              ▼ grounds
            Signal ──────────────┐
              │                  │ aggregated by
              ▼ referenced by   ▼
            Research ──────────► Thesis
              │                  │
              └──────────────────┘
                                 │
                                 ▼ accumulated into
                              Knowledge
                                 │
                                 ▼ organized by
                              Entity
```

Every object except Knowledge is anchored to one or more Entities. Entities are the substrate that all other objects refer to.

---

## Traceability Chain

Per Principle 5, the traceability chain is:

```
Source
  → Evidence
    → Signal
      → Research
        → Thesis
          → Knowledge
```

Every conclusion must be traceable along this chain. No conclusion may skip a step.

---

## Composition Rules

The Object Model defines seven core objects. The architecture may add new objects only by **extension**:

- New object types integrate by reference to existing objects.
- New object types may not redefine or replace existing objects.
- New object types are documented in this Object Model, not in Constitutions.
- Constitutions may refine these objects with specific properties, but not introduce new core types.

---

## Open Questions (Deferred)

The following questions remain open and are deferred to future versions of the Object Model:

1. **Knowledge access patterns.** Is Knowledge queryable as a single object, or only as a federated view over Theses? This affects whether Knowledge needs a schema or is purely a derived concept. Decision deferred until usage patterns emerge.
2. **Cross-cutting objects.** Patterns, Questions, and Hypotheses are deferred (see Resolved Decisions §5). If future Constitutions or workflows discover the need, the promotion path is through an RFC.
3. **Theses that contradict.** When two Theses on the same Entity reach different conclusions, how is the disagreement represented? As linked objects, as a "thesis conflict" object, or as metadata on each Thesis? Decision deferred until concrete conflict patterns emerge.

These are documented for future review, not as gaps in v1.0.

---

## Version History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-18 | Frozen. Resolved 5 architectural decisions during freeze: Entity subtype strategy, Industry as Entity, Watchlist as View, Reports as Views, deferred Pattern/Question/Hypothesis |
| 0.1 | 2026-07-18 | Initial draft for review |
