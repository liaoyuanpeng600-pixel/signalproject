# GOVERNANCE — Spec Evolution Processes

> **Document role:** Defines how the SIGNAL spec set is changed. Three processes live here: **RFC** (proposals), **ADR** (decisions), and the **Release Checklist**.
>
> Read alongside: [SPEC_VERSION.md](SPEC_VERSION.md), [INVARIANTS.md](INVARIANTS.md), [GLOSSARY.md](GLOSSARY.md).

---

## 1. Why Governance

Without a process:

- The spec drifts in conflicting directions.
- New contributors don't know how to propose changes.
- Decisions are made but their context is lost.
- Releases ship with half-completed work.

A spec process provides:

1. **Proposals** (RFC) — anyone can propose; reviewers vet.
2. **Decisions** (ADR) — significant decisions are recorded with their reasoning.
3. **Releases** — a checklist ensures nothing is forgotten.

---

## 2. RFC — Request for Comments

An RFC is a **proposal to change the spec**. It is the entry point for any non-trivial change.

### 2.1 When to Write an RFC

| Change | RFC required? |
|---|---|
| New invariant | Yes (mandatory) |
| Invariant modification | Yes (mandatory) |
| New signal type | Yes |
| New agent | Yes |
| Schema MAJOR change | Yes |
| Schema MINOR change | No (ADR is sufficient) |
| New document | No (ADR is sufficient) |
| Bug fix in spec text | No (PR is sufficient) |
| Example fix | No |

When in doubt: write an RFC. The cost of an RFC is small; the cost of an undocumented change is large.

### 2.2 The Process

```
   Draft            Under Review           Accepted           Merged
     │                    │                    │                 │
     ▼                    ▼                    ▼                 ▼
  ┌─────┐  submit   ┌──────────┐  accept  ┌──────────┐  PR   ┌──────┐
  │draft│──────────►│reviewing │─────────►│ accepted │──────►│merged│
  └─────┘           └──────────┘          └──────────┘       └──────┘
     ▲                  │                     │
     │                  │ reject              │ superseded
     │                  ▼                     ▼
     │            ┌──────────┐          ┌──────────┐
     └────────────│ rejected │          │superseded│
                  └──────────┘          └──────────┘
```

### 2.3 RFC States

| State | Meaning |
|---|---|
| `draft` | Author is writing; not yet submitted |
| `reviewing` | Submitted; open for comments; PR against `RFC/` directory |
| `accepted` | Reviewers approved; ready to implement |
| `rejected` | Reviewers declined; closed with reasoning |
| `superseded` | Replaced by a newer RFC; old RFC is archived |
| `merged` | Implementation complete; spec docs updated; PR merged |

### 2.4 RFC Author Lifecycle

1. **Copy `RFC-000-template.md`** to `RFC/RFC-NNN-short-name.md` where NNN is the next number.
2. Fill in all sections.
3. Submit PR to `RFC/` directory.
4. Address reviewer comments.
5. On acceptance, change state to `accepted`.
6. Implement the changes (in spec docs).
7. Submit implementation PR.
8. On merge, change state to `merged`.

### 2.5 File Layout

```
RFC/
├── README.md                  # This governance explanation
├── RFC-000-template.md        # Template for new RFCs
├── RFC-001-pipeline-redesign.md
├── RFC-002-confidence-floor.md
└── ...
```

### 2.6 Review SLA

| Action | Target |
|---|---|
| First review response | 5 business days |
| Discussion period | 10 business days |
| Decision | 15 business days from submission |

A reviewer is a designated maintainer of the affected area (per `CODEOWNERS` or equivalent).

---

## 3. ADR — Architecture Decision Record

An ADR records a **decision that was made**. Unlike an RFC (which proposes), an ADR documents the result.

### 3.1 When to Write an ADR

| Decision | ADR required? |
|---|---|
| Choice of gating threshold | Yes |
| Choice of composite weights | Yes |
| Choice of pipeline architecture | Yes |
| Choice of storage tech | Yes |
| Choice of model tier for a task | Yes |
| Naming a new agent | No (just update [02](02_agent_constitution.md)) |
| Adding an example | No |
| Fixing a typo | No |

The principle: **if a future contributor would benefit from knowing "why this was decided", write an ADR**.

### 3.2 The Process

ADRs are written **after** a decision is made (whether by RFC acceptance or direct discussion). The process is:

1. Create `ADR/ADR-NNN-short-name.md` from the template.
2. Fill in the sections **as they were understood at decision time** (not with hindsight).
3. Set status to `accepted` (or `superseded` if later overridden).
4. Commit. No PR review is required for retroactive documentation, though optional review is welcome.

### 3.3 ADR States

| State | Meaning |
|---|---|
| `proposed` | Decision pending; ADR is a placeholder |
| `accepted` | Decision made and in effect |
| `superseded` | Later overridden by a newer ADR |

ADRs are **never deleted**. Superseded ones are kept for history.

### 3.4 File Layout

```
ADR/
├── README.md              # Process explanation + template
├── ADR-001-pipeline-design.md
├── ADR-002-gating-threshold.md
├── ADR-003-composite-formula.md
├── ADR-004-override-append-only.md
├── ADR-005-superseded-status.md
├── ADR-006-decay-worker.md
└── ...
```

### 3.5 Naming Convention

`ADR-NNN-short-name.md` where:
- `NNN` is a zero-padded sequence number; never reused, even if ADR is superseded.
- `short-name` is kebab-case, ≤ 30 chars.

### 3.6 ADR Numbering

Once an ADR number is assigned, it is **never reused**. If an ADR is superseded, the new ADR gets a new number, and the old ADR's status is updated to `superseded by ADR-NNN`.

---

## 4. RFC vs ADR — When to Use Which

| | RFC | ADR |
|---|---|---|
| **Direction** | Forward-looking (propose) | Backward-looking (record) |
| **Audience** | Reviewers, future maintainers | Future maintainers |
| **State changes** | Yes (draft → reviewing → ...) | Mostly stable (accepted) |
| **Cross-references** | RFCs reference ADRs; ADRs reference RFCs |
| **Lifecycle** | Short (until decision) | Long (forever) |

A typical flow:
1. RFC proposes a change.
2. RFC is accepted.
3. Implementation happens.
4. ADR is written capturing the decision rationale.

The ADR is the historical record. The RFC is the proposal.

---

## 5. Release Checklist

Every release (SPEC_VERSION bump) MUST pass this checklist before merging.

```
Release Checklist — SPEC_VERSION <X.Y.Z>

Pre-merge
☐ All open RFCs resolved (accepted, rejected, or postponed)
☐ All accepted RFCs have implementation PRs
☐ All schema changes have migration code (if MAJOR)
☐ All breaking changes documented in [SPEC_VERSION §3](SPEC_VERSION.md)
☐ All new terms added to [GLOSSARY.md](GLOSSARY.md)
☐ All new invariants added to [INVARIANTS.md](INVARIANTS.md)
☐ All decisions recorded in [ADR/](ADR/)
☐ [09 §11 Migration Log](09_development_roadmap.md) updated

Code-side
☐ Schema validators updated for any field changes
☐ Agent postconditions updated for any contract changes
☐ Workflow stage specs updated for any graph changes
☐ Migration shims implemented (if MAJOR)
☐ Backward-compatibility shims tested
☐ Deprecation warnings emitted on old paths

Documentation
☐ Document version footers updated
☐ Cross-references re-validated
☐ Worked examples still match schemas
☐ Glosssary entries reflect current usage
☐ No deprecated aliases ([GLOSSARY §7](GLOSSARY.md)) in active docs

Quality gates
☐ scripts/lint_spec.py passes with zero errors
☐ Unit tests pass (if applicable)
☐ E2E smoke test passes (if applicable)
☐ Calibration dashboard reviewed (if scoring changed)
☐ Two reviewer approvals

Post-merge
☐ SPEC_VERSION updated in [SPEC_VERSION.md §2](SPEC_VERSION.md)
☐ Migration artifacts tagged in git
☐ Deprecation clock started for old version (window per [SPEC_VERSION §5](SPEC_VERSION.md))
☐ Announcement written
☐ All affected docs' headers reflect new version dependency
```

This checklist is itself versioned. To propose a new item, write an RFC.

---

## 6. Release Versioning

A release is identified by the SPEC_VERSION bump:

| Bump type | Triggers | External impact |
|---|---|---|
| PATCH | Bug fixes, examples, clarifications | None |
| MINOR | New doc, new agent, new signal type, backward-compatible enhancements | Re-validate integration |
| MAJOR | Invariant change, schema break, contract break | Migration required |

See [SPEC_VERSION §3](SPEC_VERSION.md) for the full rules.

---

## 7. Roles

| Role | Responsibility | Authority |
|---|---|---|
| **Author** | Writes RFCs and ADRs | Anyone can author |
| **Reviewer** | Reviews RFCs, can accept/reject | Designated per area |
| **Curator** | Final say on controversial changes | Single designated person |
| **Operator** | Runs lint, applies changes | Has merge rights |
| **Auditor** | Reviews release compliance | Read-only |

For SIGNAL in v1.x, all roles are filled by the same person unless explicitly delegated. The role definitions exist for clarity when scaling.

---

## 8. Deprecation Policy

When a term, field, or contract is deprecated:

1. Mark it deprecated in its owner document with a clear note: `> DEPRECATED: use X instead. Removed in SPEC_VERSION Y.0.`
2. Add a deprecation alias entry in [GLOSSARY §7](GLOSSARY.md).
3. Emit a warning at runtime if applicable.
4. Set a removal target SPEC_VERSION (typically the next MAJOR).
5. Document in the migration log.

Deprecation **must** go through an RFC for any contract-level change.

---

## 9. Out-of-Process Changes

A change made without an RFC (when one was required) is a **process violation**. Such changes:

- Are reverted by default.
- May be re-applied if an RFC is written retroactively and accepted.
- Are flagged in the next release's audit log.

The lint pass does not catch process violations (it can't reason about intent); humans must enforce.

---

## 10. Version History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-16 | Initial governance: RFC + ADR + Release Checklist |