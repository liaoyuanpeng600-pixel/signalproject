# ADR — Architecture Decision Records

> **Directory role:** Captures the reasoning behind every significant design decision in the SIGNAL spec. ADRs are written **after** a decision is made; they document context, alternatives, trade-offs, and consequences.

---

## 1. When to Write an ADR

| Decision | ADR? |
|---|---|
| Threshold values (e.g., gating = 0.65) | Yes |
| Architecture choices (e.g., 9-stage pipeline) | Yes |
| Mathematical formulas (e.g., composite weights) | Yes |
| Storage / tech choices | Yes |
| Model tier selection per task | Yes |
| Naming a new agent / field | No (just update doc) |
| Bug fix / typo | No |
| New example | No |

When in doubt: write the ADR. The cost is small; the historical value is large.

---

## 2. ADR Template

Copy this template into `ADR-NNN-short-name.md` and fill in.

```markdown
# ADR-NNN: <Title>

> **Status:** proposed | accepted | superseded
> **Date:** YYYY-MM-DD
> **Supersedes:** ADR-NNN (if applicable)
> **Superseded by:** ADR-NNN (if applicable)

## Context

What is the issue we're seeing that motivates this decision? Include:
- The problem or need
- Constraints (technical, business, regulatory)
- Forces at play

## Decision

What did we decide? State it in one paragraph.

## Alternatives Considered

What other options were on the table? For each:
- Brief description
- Why it was rejected

## Trade-offs

What did we gain? What did we give up?

## Consequences

What becomes easier? What becomes harder? What new constraints do we accept?

## References

- Related documents
- Related ADRs / RFCs
- External sources
```

---

## 3. ADR States

| State | Meaning |
|---|---|
| `proposed` | Decision pending; ADR is a placeholder |
| `accepted` | Decision made and in effect |
| `superseded` | Later overridden by a newer ADR |

ADRs are never deleted. Superseded ADRs are kept for history; their state and `Superseded by` field are updated.

---

## 4. Numbering

- Each ADR has a unique, never-reused number.
- Format: `ADR-NNN-short-name.md`
- Numbers are assigned sequentially.
- If an ADR is superseded, the new one gets a new number; the old one's status is updated.

---

## 5. Index

| # | Title | Status | Date |
|---|---|---|---|
| [ADR-001](ADR-001-pipeline-design.md) | 9-stage pipeline design (vs 7 or 10) | accepted | 2026-07-16 |
| [ADR-002](ADR-002-gating-threshold.md) | Gating threshold = 0.65 | accepted | 2026-07-16 |
| [ADR-003](ADR-003-composite-formula.md) | Composite formula weights 0.30/0.25/0.20/0.15/0.10 | accepted | 2026-07-16 |
| [ADR-004](ADR-004-override-append-only.md) | OverrideRecord is append-only | accepted | 2026-07-16 |
| [ADR-005](ADR-005-superseded-status.md) | `superseded` as a lifecycle status | accepted | 2026-07-16 |
| [ADR-006](ADR-006-decay-worker.md) | Decay worker is a background job, not an agent | accepted | 2026-07-16 |