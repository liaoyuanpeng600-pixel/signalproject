# RFC — Request for Comments

> **Directory role:** Proposals for changes to the SIGNAL spec. An RFC is the entry point for any non-trivial spec change. See [GOVERNANCE.md §2](../GOVERNANCE.md) for the process.

---

## 1. When to Write an RFC

| Change | RFC required? |
|---|---|
| New or modified invariant | **Mandatory** |
| New agent or workflow stage | Yes |
| New signal type | Yes |
| New schema field (MINOR) | Optional (ADR sufficient) |
| Schema MAJOR change | Yes |
| Schema MAJOR removal | Yes |
| New document in spec set | Optional |
| Backward-compatibility shim design | Yes |
| Bug fix in spec text | No (PR sufficient) |
| Example fix | No |

When in doubt, write the RFC. The cost is small; the protection against undocumented change is large.

---

## 2. RFC Lifecycle

```
Draft → Reviewing → Accepted → Merged
              ↓           ↓
           Rejected   Superseded
```

| State | Meaning |
|---|---|
| `draft` | Author writing; not yet submitted |
| `reviewing` | Submitted; PR open against `RFC/` directory |
| `accepted` | Reviewers approved; awaiting implementation |
| `rejected` | Reviewers declined; closed with reasoning |
| `superseded` | Replaced by a newer RFC |
| `merged` | Implementation complete; spec updated; PR merged |

A new state is set by updating the Status field in the RFC's frontmatter and committing. Status transitions are linear except for `superseded`, which can occur at any time.

---

## 3. File Layout

```
RFC/
├── README.md                # This file
├── RFC-000-template.md      # Template
├── RFC-001-...md
├── RFC-002-...md
└── ...
```

---

## 4. Numbering

- `RFC-NNN-short-name.md` where NNN is zero-padded and never reused.
- Author picks the next available number.
- If an RFC is superseded, the new one gets a new number; the old one's state is updated.

---

## 5. SLAs

| Step | Target |
|---|---|
| First reviewer response | 5 business days |
| Discussion period | 10 business days |
| Final decision | 15 business days from submission |
| Implementation | 30 days after acceptance |

SLAs are targets, not deadlines. Quality matters more than speed.

---

## 6. Author Checklist

Before submitting:

```
☐ All template sections filled
☐ At least one alternative considered
☐ Trade-offs acknowledged
☐ Consequences enumerated (positive AND negative)
☐ Affected documents listed
☐ Affected invariants listed (with INV-N numbers if applicable)
☐ SPEC_VERSION impact assessed (MAJOR/MINOR/PATCH)
☐ Backward compatibility impact assessed
☐ Migration plan if MAJOR
☐ ADR draft prepared (will be finalized on acceptance)
```

---

## 7. Reviewer Checklist

When reviewing:

```
☐ Problem is clearly stated
☐ Decision is justified
☐ Alternatives are reasonable
☐ Trade-offs are honest
☐ Consequences are realistic
☐ Backward compatibility story exists (or none needed)
☐ Migration plan exists if MAJOR
☐ Affected invariants identified
☐ Glossary impact considered
☐ Test plan exists (for implementation phase)
```

---

## 8. From Acceptance to Merge

When an RFC is accepted:

1. State → `accepted`.
2. Author writes implementation PR(s) against affected docs.
3. If MAJOR: write migration code in `migrations/`.
4. After spec docs updated, lint passes, and reviewers approve → state → `merged`.
5. Add an ADR capturing the final decision ([GOVERNANCE §3](../GOVERNANCE.md)).
6. Update [SPEC_VERSION.md §2](../SPEC_VERSION.md) and [09 §11 Migration Log](../09_development_roadmap.md).

---

## 9. RFC Template

See [RFC-000-template.md](RFC-000-template.md).

---

## 10. Index

| # | Title | Status | Date |
|---|---|---|---|
| RFC-000 | Template | n/a | 2026-07-16 |

(No active RFCs at this time; the current spec set was authored directly. As the spec matures, RFCs will be added here for any future changes.)