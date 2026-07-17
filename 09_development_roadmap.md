# 09 · Development Roadmap

> **Document role:** Phased delivery plan. Defines phases, milestones, deliverables, dependencies, exit criteria, and deprecation schedule. Use this to plan work, not to justify scope.
>
> Requires: `00_project_context.md ≥ 0.2`, all other documents at any version.

---

## 1. Phasing Philosophy

SIGNAL is delivered in **eight phases**. Each phase has:
- A clear deliverable
- Explicit entry and exit criteria
- A freeze date for specs referenced in that phase
- A deprecation path for anything it introduces

We ship **vertical slices**, not horizontal layers. Each phase produces a working system that can run, even if reduced.

---

## 2. Phase Overview

| Phase | Name | Goal | Est. duration |
|---|---|---|---|
| 0 | Specification | All docs finalized | 2 weeks |
| 1 | Skeleton | Pipeline runs with one source, one signal type, manual review | 4 weeks |
| 2 | First Loop | End-to-end W1 with 5 sources, 10 signal types, daily report | 8 weeks |
| 3 | Calibration | Historical backtest, calibration pass, accuracy targets met | 6 weeks |
| 4 | Hardening | Security review, audit, multi-tenancy scaffolding | 4 weeks |
| 5 | Scale | 500+ entities, multi-region, full observability | 8 weeks |
| 6 | Differentiation | Cross-portfolio contagion, embedding novelty, UI | 12 weeks |
| 7 | Production GA | Compliance, SLA, 24/7 on-call | 4 weeks |

**Total: ~46 weeks (≈ 11 months) end-to-end from spec freeze.**

---

## 3. Phase 0 — Specification (current)

**Goal.** Lock down all 15 documents. No production code.

### 3.1 Deliverables

- All `00_*` through `14_*` documents at version 0.2 or higher
- All cross-references resolved
- Worked examples for each substantive section

### 3.2 Entry Criteria

- Project charter approved
- Document map agreed

### 3.3 Exit Criteria

- Every document has a version number
- Every cross-reference is a valid link
- Reviewed by at least 2 stakeholders

---

## 4. Phase 1 — Skeleton

**Goal.** A working pipeline that emits at least one Signal end-to-end, manually reviewed.

### 4.1 Deliverables

- Pipeline runner with W1 implemented
- 1 source connector: SEC EDGAR (regulatory filings)
- 1 agent: `detector` (basic version)
- Manual review UI (even a spreadsheet works)
- 5 watchlist entities for testing

### 4.2 Entry Criteria

- Phase 0 complete
- LLM provider account provisioned
- Basic infra (PostgreSQL, Redis, object store) deployed

### 4.3 Exit Criteria

- A SEC 8-K filing produces a `capital_action` Signal within 4 hours
- The Signal has a real source URL and a verified quote
- A human can review and approve/reject it
- The audit trail captures the full agent chain

### 4.4 What's Explicitly NOT in Phase 1

- No verifier (just trust the source)
- No scoring (manual)
- No synthesis
- No real reports

---

## 5. Phase 2 — First Loop

**Goal.** Full W1 cycle with multiple sources, multiple signal types, automated scoring, daily report.

### 5.1 Deliverables

- 5 source connectors (SEC EDGAR, press release feeds, 3 news wires)
- 5 agents (`harvester`, `detector`, `verifier`, `analyst`, `scorer`) per [02 §2](02_agent_constitution.md)
- All 10 core signal types per [10 §2](10_signal_taxonomy.md)
- Daily markdown report per [13 §3](13_report_template.md)
- Watchlist management UI per [14](14_watchlist.md)
- Pipeline stages S1–S9 per [03 §3](03_workflow_constitution.md)

### 5.2 Entry Criteria

- Phase 1 complete
- Prompt registry initialized
- Test suites for all 5 agent prompts at quality bar ([07 §6.4](07_prompt_guidelines.md))

### 5.3 Exit Criteria

- ≥ 50 Signals/day emitted (steady state)
- Calibration: ≥ 60% corroboration rate on high-confidence Signals
- Latency: median ≤ 4h during market hours (matches [00 §7.2](00_project_context.md))
- Cost: ≤ $0.50 per active Signal

### 5.4 Risks

| Risk | Mitigation |
|---|---|
| Detector prompt produces too many false positives | Iterate on prompt with calibration feedback; widen entity resolution |
| LLM cost overruns | Aggressive caching; tiered models; prompt compression |
| Source quality varies wildly | Per-source health monitoring; auto-disable bad sources |

---

## 6. Phase 3 — Calibration

**Goal.** Hit all calibration targets in [00 §7](00_project_context.md).

### 6.1 Deliverables

- Historical backtest harness (replay pipeline W5)
- Outcome-tracking system (records price action, subsequent filings)
- Calibration dashboard
- Re-scoring loop using outcomes

### 6.2 Entry Criteria

- Phase 2 complete
- ≥ 30 days of production Signals with outcomes

### 6.3 Exit Criteria

- Brier score ≤ 0.20 on holdout
- ≥ 70% corroboration rate on Signals with composite ≥ 0.7
- Decay-worker correctly decays ≥ 95% of eligible Signals

### 6.4 Calibration Methodology

1. Hold out the most recent 20% of Signals as a test set
2. Compute outcome (price move within horizon, subsequent corroborating event)
3. Compute Brier score per dimension and per band
4. Adjust scoring rubric if Brier > 0.20 on any band
5. Re-test, repeat until stable

---

## 7. Phase 4 — Hardening

**Goal.** Production-grade security, auditability, multi-tenancy foundation.

### 7.1 Deliverables

- Security review (external)
- Audit log immutability guarantees
- RBAC implementation
- Dual-approval for sensitive curator actions
- Penetration testing report

### 7.2 Entry Criteria

- Phase 3 complete
- Security budget approved

### 7.3 Exit Criteria

- All high-severity pen-test findings remediated
- Audit log verified immutable (cryptographic chain)
- RBAC tested with negative cases

---

## 8. Phase 5 — Scale

**Goal.** Cover 500+ watchlist entities with stable operations.

### 8.1 Deliverables

- Sharded pipeline runners (per-entity or per-industry)
- 20+ source connectors (international, niche)
- Full observability stack (Prometheus + Grafana + OpenTelemetry)
- Auto-scaling policies
- Disaster recovery drills

### 8.2 Entry Criteria

- Phase 4 complete

### 8.3 Exit Criteria

- Cycle wall time p95 ≤ 30 min at 500 entities
- Cost per Signal ≤ $0.30 at 500 entities
- Uptime ≥ 99.5% over 30 days

---

## 9. Phase 6 — Differentiation

**Goal.** Features that distinguish SIGNAL from generic LLM-over-news.

### 9.1 Deliverables

- Cross-portfolio contagion detection
- Embedding-based novelty (replace minhash)
- Per-reader personalized digest
- Counterfactual Signal scoring
- Interactive Signal explainer UI

### 9.2 Entry Criteria

- Phase 5 complete
- 3 months of stable production data

### 9.3 Exit Criteria

- Reader engagement (open rate) ≥ 50%
- User-feedback loop trained on ≥ 1000 examples
- Contagion detection validated against known historical cascades

---

## 10. Phase 7 — Production GA

**Goal.** Public availability, compliance, SLA, 24/7 support.

### 10.1 Deliverables

- SOC 2 Type II readiness (if applicable)
- Public SLA (uptime, latency)
- 24/7 on-call rotation
- Public documentation portal
- Pricing and onboarding

### 10.2 Exit Criteria

- 90 days at Phase 6 SLA without breach
- All compliance audits passed

---

## 11. Migration Log

Every MAJOR version bump in any spec must be logged here.

| Date | Spec | Old version | New version | Migration |
|---|---|---|---|---|
| 2026-07-16 | `00_project_context` | — | 0.2 | First engineering reference |
| 2026-07-16 | `00_project_context` | 0.2 | 0.3 | Pipeline stage table aligned to 9 stages per [03 §3](03_workflow_constitution.md); borderline zone corrected to 0.45–0.65 per [06 §5.3](06_scoring_framework.md) |
| 2026-07-16 | `01_signal_constitution` | — | 0.1 | Initial |
| 2026-07-16 | `01_signal_constitution` | 0.1 | 0.2 | Added `superseded` to lifecycle enum; aligned Provenance example to [04 §6](04_data_schema.md) schema |
| 2026-07-16 | `02_agent_constitution` | — | 0.1 | Initial |
| 2026-07-16 | `02_agent_constitution` | 0.1 | 0.2 | Curator actions expanded; detector model reference aligned to [07 §8](07_prompt_guidelines.md) |
| 2026-07-16 | `03_workflow_constitution` | — | 0.1 | Initial |
| 2026-07-16 | `03_workflow_constitution` | 0.1 | 0.2 | Gating threshold unified to ≥ 0.65 → active (matches [06 §5.1](06_scoring_framework.md)); S3 vs Signal-level dedup clarified; S9 supersedes writes added |
| 2026-07-16 | `04_data_schema` | — | 1.0 | Initial |
| 2026-07-16 | `04_data_schema` | 1.0 | 1.1 | OverrideRecord.action expanded to all curator actions; CycleReport.signals_emitted type-annotated; Metadata gained precedent_basis/conflict/reasoning_partial; versioning table complete |
| 2026-07-16 | `05_reasoning_framework` | — | 0.1 | Initial |
| 2026-07-16 | `06_scoring_framework` | — | 0.1 | Initial |
| 2026-07-16 | `06_scoring_framework` | 0.1 | 0.2 | Composite formula marked canonical; confidence downgrade attribution clarified |
| 2026-07-16 | `07_prompt_guidelines` | — | 0.1 | Initial |
| 2026-07-16 | `08_architecture` | — | 0.1 | Initial |
| 2026-07-16 | `08_architecture` | 0.1 | 0.2 | Topology now lists W1–W5 (was W1–W4) |
| 2026-07-16 | `10_signal_taxonomy` | — | 0.1 | Initial |
| 2026-07-16 | `13_report_template` | — | 0.1 | Initial |
| 2026-07-16 | `14_watchlist` | — | 0.1 | Initial |

---

## 12. Deprecation Schedule

When a document is being replaced:

1. New version is published
2. Old version remains in the spec folder for 90 days, marked DEPRECATED
3. After 90 days, old version is archived (kept in git history only)

Cross-document references to deprecated versions **must** be updated in the same release as the deprecation announcement.

---

## 13. Risk Register

Cross-phase risks:

| Risk | Phase(s) | Mitigation |
|---|---|---|
| LLM provider pricing change | 2–7 | Multi-provider gateway ([08 §5](08_architecture.md)); model tiering |
| Schema churn breaks downstream | 0–7 | Strict versioning; migration log; deprecation window |
| Calibration regression | 3–7 | Continuous monitoring; auto-rollback on drift ([06 §6.1](06_scoring_framework.md)) |
| Source licensing change | 1–7 | Multiple sources per entity type; legal review before connector addition |
| Insider threat via curator | 4–7 | Append-only overrides; dual approval; audit trail |
| LLM model deprecation | 1–7 | Pin model versions; replay detects divergence |

---

## 14. Phase Decision Gates

A phase does not advance unless **all** of:

1. Exit criteria met (per phase)
2. No critical bugs open
3. Documentation updated to reflect what shipped
4. Calibration report signed off (Phases 2+)
5. Security review (Phases 4+)

If a gate fails, the phase extends or rolls back. We do not advance with known regressions.

---

## 15. Out-of-Scope Confirmation

The following are confirmed out of scope for the current roadmap and would require a separate RFC + roadmap revision:

- Trading execution integration
- Insider / alternative data
- Real-time sub-second pipeline
- Mobile applications

See [00 §8](00_project_context.md) for the canonical non-goals list.

---

## 16. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold |

Phase additions/deletions are MAJOR. New exit criteria within an existing phase are MINOR. Wording fixes are PATCH.