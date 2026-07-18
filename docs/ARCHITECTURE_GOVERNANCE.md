# Architecture Governance

> **Document role:** Governance for the SIGNAL Architecture Principles and the layered architecture below it. Defines what "Frozen" means, how the architecture evolves, and how future designs are reviewed.
>
> Read alongside: [00_ARCHITECTURE_PRINCIPLES.md](00_ARCHITECTURE_PRINCIPLES.md).
>
> **Document role:** Frozen
> **Version:** 1.0
> **Effective Date:** 2026-07-18
> **Next Review:** TBD
> **Owner:** Architecture

---

## Purpose

This document establishes the governance rules for the SIGNAL architecture.

It complements the [Architecture Principles](00_ARCHITECTURE_PRINCIPLES.md) by defining how those principles are maintained, revised, and applied to future design decisions.

It is the operational counterpart to the constitutional document: where the Principles state *what is true*, this document states *how the truth is preserved over time*.

---

## Scope

This document governs:

- The Architecture Principles document and its revisions.
- The layered architecture hierarchy (Principles → Object Model → Constitutions → Workflow → Runtime → Implementation).
- The process for proposing and accepting architectural changes.
- The review checklist used to evaluate new designs.

This document does **not** govern:

- The contents of constitutions, workflows, or runtime concerns. Those are owned by their respective documents.
- Implementation-level decisions. Implementation is below the architectural boundary.

---

## What "Frozen" Means

When the Architecture Principles document is marked **Status: Frozen**, the following applies:

- **No silent changes.** Principles cannot be modified without going through the revision process described below.
- **Constraints are binding.** All other documents in the repository must conform to the frozen principles.
- **Conflicts surface, not hide.** When a future design appears to conflict with a principle, the conflict must be made visible — not papered over.
- **The freeze applies to principles, not implementations.** A frozen principle does not freeze implementations built under it. Implementations may evolve freely within the principles.
- **The freeze is a commitment, not a tomb.** It signals that the principles are deliberate and reviewed, not that they are untouchable. Major revisions remain possible through the amendment process.

---

## Minor Revision Policy

A minor revision:

- Refines the wording of an existing principle without changing its meaning.
- Adds clarifications, examples, or cross-references.
- Corrects typos or formatting.
- Does not add, remove, or change the substance of any principle.

A minor revision is approved by the **Owner** (Architecture) and recorded in the document's version history. No constitutional process is required.

The document's MINOR version is incremented (e.g., `1.0 → 1.1`).

---

## Major Revision Policy

A major revision:

- Adds a new principle.
- Removes an existing principle.
- Changes the substance of an existing principle.
- Changes the relationship between principles.
- Reorders principles in a way that conveys a new priority.

A major revision requires the **Constitutional Amendment Process** described below.

The document's MAJOR version is incremented (e.g., `1.0 → 2.0`).

---

## Constitutional Amendment Process

A major revision follows this sequence:

1. **Proposal** — A written proposal is submitted, identifying the principle affected, the change proposed, the motivation, and the expected impact on downstream layers.
2. **Discussion** — The proposal is open for review by all stakeholders for a defined period (default: 14 days).
3. **Decision** — Acceptance requires the Owner's approval plus majority approval of the Stakeholder Group.
4. **Update** — The Architecture Principles document is updated; metadata is bumped to a new MAJOR version; the change is recorded in the document's version history.
5. **Propagation review** — Downstream layers (Object Model, Constitutions, Workflow, Runtime) are reviewed for consistency with the amended principle. Where they conflict, follow-up tasks are created. Implementation is not in scope.
6. **Announcement** — The amendment is announced with a summary of the change and its rationale.

A rejected proposal is archived with its motivation and the rejection rationale, for future reference.

---

## Architecture Review Process

Any new design proposal — whether a new document, a new schema, a new workflow, or a new component — must pass the **Architecture Review Checklist** (§[Architecture Review Checklist](#architecture-review-checklist)) before adoption.

The review is performed by the **Owner** (Architecture), with consultation from relevant domain owners as needed.

The default outcome of any review is **approval with notes**. Rejection is reserved for clear principle violations or unresolvable layer-inappropriateness.

---

## Stakeholder Group

The Stakeholder Group comprises:

- **Owner: Architecture** — chairs the group; arbitrates conflicts; approves minor revisions; signs off on major revisions.
- **Object Model author** — consulted when the change affects object types, relations, or domain structure.
- **Constitution owners** — consulted when the change affects a specific constitutional document (Signal Constitution, Workflow Constitution, Runtime, etc.).
- **Ad-hoc experts** — the Owner may invite domain experts for specific reviews.

The default Stakeholder Group size is small (3–5 people). Larger groups are formed only for major revisions.

---

## Repository Design Hierarchy

The SIGNAL architecture is layered. Higher layers constrain lower layers; lower layers may not violate higher layers.

```
Architecture Principles   ← Constitutional root (frozen)
        ↓
Object Model             ← Defines object types and their relations
        ↓
Constitutions            ← Domain-level constitutional documents
        ↓                          (Signal Constitution, Workflow Constitution, etc.)
Workflow                 ← Defines processes and orchestration
        ↓
Runtime                  ← Defines how the system runs
        ↓
Implementation           ← Code, schemas, deployments
```

### Hierarchy Rules

- A lower layer may not contradict an upper layer.
- A lower layer may refine or specialize an upper layer, but not weaken it.
- A change to an upper layer requires review of all lower layers for impact.
- A change to a lower layer does not require review of upper layers, but may trigger observation if it surfaces a hidden upper-layer assumption.

### Layer Definitions

| Layer | Owned by | Purpose |
|---|---|---|
| Architecture Principles | Architecture | Constitutional root: design philosophy |
| Object Model | Object Model author | Object types, relations, domain vocabulary |
| Constitutions | Domain owners | Domain-level constitutional documents (e.g., Signal Constitution, Workflow Constitution) |
| Workflow | Workflow owner | Process definitions, orchestration, lifecycle |
| Runtime | Runtime owner | Operational concerns: deployment, execution, observability |
| Implementation | Engineers | Concrete code, schemas in code, deployed artifacts |

---

## Architecture Review Checklist

Before any new design is adopted, the following questions must be answered.

### Constitutional Alignment

- **Does this violate an Architecture Principle?**
  - If yes, the design must be rejected or the principle must be amended through the major revision process.
- **Which principle(s) does this align with?**
  - State explicitly which principles the design supports.

### Layer Appropriateness

Working from the top of the hierarchy down:

- **Can this be solved in the Architecture Principles?**
  - If yes, the issue is a missing principle; propose an amendment instead of adding a workaround.
- **Can this be solved in the Object Model?**
  - If yes, prefer the Object Model over introducing new layers or constitutions.
- **Can this be solved in a Constitution?**
  - If yes, prefer a constitutional document over a workflow or runtime change.
- **Can this be solved in the Workflow?**
  - If yes, prefer a workflow change over a runtime or implementation change.
- **Can this be solved in the Runtime?**
  - If yes, prefer a runtime change over an implementation change.
- **Is an Architecture amendment actually required?**
  - Default: no. Architecture amendments are expensive and should be avoided unless necessary.

### Consistency

- **Does this contradict any existing constitution?**
- **Does this duplicate something that already exists in another layer?**
- **Are the cross-document references consistent?**

### Long-Term View

- **Will this still be the right design in 5 years?**
- **Does this preserve or improve the constitution's evolvability?**
- **Does this introduce a coupling that will be hard to reverse?**

### Outcome Rules

- A design that fails the first question (principle violation) **cannot** be adopted without a constitutional amendment.
- A design that fails any other question must be revised before adoption.
- A design that passes all questions is approved, with notes recorded for future reference.

---

## Review Cadence

| Item | Cadence |
|---|---|
| Architecture Principles | When a major revision is proposed, or every 24 months, whichever comes first |
| Repository hierarchy | Annually |
| This governance document | When the governance process itself needs updating |

---

## Related Documents

- [Architecture Principles](00_ARCHITECTURE_PRINCIPLES.md) — the constitutional root
- [Signal Constitution](../01_signal_constitution.md) — domain constitution (existing)
- [Workflow Constitution](../03_workflow_constitution.md) — domain constitution (existing)

---

## Version History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-18 | Initial governance document, concurrent with Architecture Principles v1.0 freeze |
