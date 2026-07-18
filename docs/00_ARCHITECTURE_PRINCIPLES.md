# Architecture Principles

> **Document role:** Constitutional root. Defines the design philosophy of the SIGNAL repository. All other specifications (Signal Constitution, Workflow Constitution, Runtime, Research, Knowledge, Thesis, etc.) must conform to these principles. If a future implementation conflicts with a principle, the implementation must be reconsidered before the principle is changed.

---

## Document Metadata

| Field | Value |
|---|---|
| **Status** | Frozen |
| **Version** | 1.0 |
| **Effective Date** | 2026-07-18 |
| **Next Review** | TBD |
| **Owner** | Architecture |

> **Note.** Frozen status means the principles are binding. Revisions follow the process defined in [ARCHITECTURE_GOVERNANCE.md](ARCHITECTURE_GOVERNANCE.md).

---

## Purpose

SIGNAL is a Research Operating System.

Its objective is to continuously improve research understanding through evidence.

The system supports human research rather than replacing human judgment.

It is designed for researchers who accumulate understanding over time, not for systems that optimize a single decision.

SIGNAL transforms external information into continuously evolving research understanding. Evidence enters the system, is interpreted in context, and becomes part of a research fabric that grows more coherent over time. Long-term value is derived from accumulated knowledge rather than isolated observations: the system's worth is measured by how much understanding it has built up, not by how many individual items it has produced.

---

## Principle 1 — Reality First

### Motivation

Reality is interconnected. Objects in the world do not exist in isolation — a company, an industry, a regulation, a thesis are linked by cause, context, and consequence.

If the architecture artificially restricts relationships between objects, it forces researchers to work around the abstraction. The system then describes a simplified version of the world, not the world itself. Research built on a simplified world produces simplified conclusions.

### Principle

Architecture should model reality rather than simplify reality. The system must not artificially restrict the relationships that can exist between objects.

If two objects can be related in reality, the architecture must permit that relation — even if the relation is rare, indirect, or currently unused.

### Implication

Schemas and object models must accept arbitrary, declared relations between objects. Domain boundaries are fluid: a research object may legitimately belong to multiple contexts. New object types and new relation types must be addable without redesigning existing types.

---

## Principle 2 — Evidence First

### Motivation

A conclusion without evidence cannot be verified, challenged, or improved. It exists as opinion. Over time, an opinion-laden system accumulates unjustified claims, which distort downstream reasoning.

Evidence is the only currency that allows research to improve.

### Principle

Every research conclusion must ultimately be supported by verifiable evidence.

Conclusions without traceable evidence are not acceptable.

### Implication

No conclusion may enter the research record without a source. Sources must be retrievable, and their provenance and quality must be preserved alongside each piece of evidence. Evidence is not uniform in quality: the architecture must keep stronger evidence distinguishable from weaker evidence, never collapsing them into a single indistinguishable form. The system distinguishes between **what is claimed** and **what is evidenced**, and the latter is always required.

---

## Principle 3 — Evolution First

### Motivation

Knowledge is never complete. Treating a research object as final is a category error: today's consensus is tomorrow's footnote.

If the architecture assumes permanence, it cannot accommodate revision. The system becomes a museum of past conclusions rather than a living research instrument.

### Principle

All core objects are living objects.

Knowledge evolves. Research evolves. Thesis evolves. Nothing should be treated as permanently complete.

### Implication

Every object must support revision, replacement, and supersession without losing its history. The architecture records **how understanding changed**, not just the current state. Static snapshots are insufficient; evolution is the norm.

---

## Principle 4 — Knowledge Accumulation

### Motivation

News is transient. A daily signal without a place in accumulated knowledge is forgotten tomorrow. The longer a system runs, the more its value depends on what it has built up — not on what it produces today.

A research system optimized only for freshness optimizes for forgetting.

### Principle

The long-term output of the system is knowledge rather than news.

Research understanding is organized around theses — living research objects that continuously integrate observations into coherent interpretations. Knowledge accumulates through the evolution of theses.

Daily signals are transient. Knowledge is cumulative.

### Implication

Architecture must favor structures that accumulate over structures that expire. Each thesis should connect to prior theses and to the observations that produced it, so that value compounds over time. Transience is allowed inside the system, but persistence is the default.

---

## Principle 5 — Traceability

### Motivation

A conclusion that cannot be traced to its origin cannot be defended, reproduced, or corrected. Black-box conclusions may be right or wrong, but the system cannot tell which — and neither can the researcher.

Traceability is the precondition for trust.

### Principle

Every conclusion must be traceable back to its origin.

Traceability extends across the entire research lifecycle: from source, to signal, to research, to thesis, to knowledge.

No black-box conclusions.

### Implication

Every derived object must record the objects, sources, and reasoning steps that produced it. Tracing a conclusion to its origin must be possible from the object alone, across every stage of the lifecycle, without recourse to external systems or undocumented processes.

---

## Principle 6 — Research Before Decision

### Motivation

Decision is a human act. Research informs decision; it does not perform it. A system that crosses the line from research into decision-making assumes responsibilities it cannot ethically bear, makes claims it cannot defend, and removes the human from a position they must occupy.

A research system that produces decisions is not a research system.

### Principle

The system performs research. Humans make decisions.

The system must not directly generate investment decisions.

### Implication

The system's outputs surface evidence, structure, and reasoning. They do not prescribe action. Recommendation-style outputs are out of scope by design, regardless of apparent utility.

---

## Principle 7 — Human Judgment

### Motivation

A research system can produce outputs that no human can interpret, challenge, or take responsibility for. Such outputs may be fluent or confident, but they are an unreliable foundation for knowledge — and an unreliable foundation for any human decision they influence.

A system that outruns human comprehension becomes a black box by another name: impressive but unaccountable.

### Principle

The system augments human reasoning.

Human interpretation remains authoritative.

AI assists research but never replaces the researcher.

### Implication

Every output of the system must remain intelligible to a human researcher. The system structures evidence and surfaces interpretations, but it does not substitute its own interpretation for the researcher's. Where human and system views diverge, the human view prevails — and the system must make the disagreement visible rather than obscure it.

---

## Principle 8 — Composable Objects

### Motivation

Domains evolve. Today's primary object may be tomorrow's secondary object. A new research domain may emerge that the architecture never anticipated.

A rigid architecture becomes obsolete at the moment its assumptions stop holding. A composable architecture absorbs new domains by adding objects rather than redesigning.

### Principle

Objects should be loosely coupled.

Future domains should be added without redesigning the architecture.

### Implication

Object definitions should declare what they depend on but not require those dependencies to know about them. New object types integrate by reference, not by modification of existing types.

---

## Principle 9 — Evolution over Prediction

### Motivation

Prediction accuracy is a narrow metric. A system optimized for prediction accuracy may produce high-confidence forecasts that are individually precise but collectively shallow — mistaking noise for signal, moment for trend.

Research understanding is a broader goal: not "what happens next?" but "how does the world actually work, and how is my understanding changing?"

### Principle

The objective is continuous improvement of research understanding rather than prediction accuracy.

### Implication

The system optimizes for **how well understanding has improved**, not for **how accurate the last forecast was**. Metrics favor structures that reveal structure, expose assumptions, and refine prior conclusions — over structures that merely guess.

---

## Principle 10 — Incremental Evolution

### Motivation

Architectures that demand wholesale replacement are fragile. Each replacement risks losing accumulated understanding, breaking compatibility, and resetting institutional knowledge. By contrast, architectures that absorb new requirements through extension preserve both continuity and learning.

An architecture designed to be replaced is an architecture that will be replaced at the worst possible moment.

### Principle

The architecture should evolve primarily through extension rather than replacement.

Future domains, object types, and workflows should integrate into the existing constitutional model rather than forcing architectural rewrites.

### Implication

When new research domains emerge, they extend the existing model by adding object types, relations, and workflows — not by overwriting what exists. Backward compatibility is preferred over theoretical purity. The constitution is amended through deliberate process, not by accretion of incompatible changes.

---

## Closing Note

These principles are constitutional.

They are intended to outlast any single implementation, schema, or component. When a design choice is in doubt, these principles are the tiebreaker. When an implementation must violate a principle, the principle is reviewed — not silently overridden.

The repository evolves. The principles do not, except by deliberate process.
