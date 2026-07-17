# 14 · Watchlist Specification

> **Document role:** Spec for the watchlist — the curated set of entities under active Signal coverage. Defines tiers, lifecycle, curation rules, and the contract between watchlist state and pipeline behavior.
>
> Requires: `00_project_context.md ≥ 0.2`, `02_agent_constitution.md ≥ 0.1`, `12_company_schema.md ≥ 0.1`.

---

## 1. What the Watchlist Is

The **watchlist** is a curated subset of the Company master ([12_company_schema.md](12_company_schema.md)) that the pipeline actively monitors. Not every Company in the master is on the watchlist.

```
Watchlist := {
  schema_version : semver,
  entities        : [WatchlistEntry],
  policies        : WatchlistPolicies,
  provenance      : Provenance
}

WatchlistEntry := {
  company_id      : string,           // references Company.id
  tier            : enum[tier_1, tier_2, tier_3, tier_4],
  added_at        : ISO8601,
  added_by        : string,           // curator user id
  last_review_at? : ISO8601,
  tier_history    : [TierChange],     // append-only
  notes?          : string,
  coverage_targets: CoverageTargets
}
```

A Company not in the watchlist is still tracked by the entity resolver but **receives no Signals**.

---

## 2. Why Tiers

Without tiers:
- Every Company is treated equally
- LLM cost scales linearly with watchlist size
- Latency degrades as more entities need reasoning
- Curator attention is unbounded

Tiers explicitly trade off **coverage depth** vs **resource cost**. Higher tier = deeper coverage = more agents invoked.

---

## 3. Tier Definitions

| Tier | Name | Coverage | Pipeline behavior |
|---|---|---|---|
| `tier_1` | Core | Deep | All stages run; full reasoning; cluster detection |
| `tier_2` | Active | Standard | All stages; reasoning; cluster detection |
| `tier_3` | Radar | Lightweight | Detect + Verify + Score only; no reasoning |
| `tier_4` | Watch | Event-driven | Detect only; verify/score on burst trigger |

### 3.1 Per-Tier Pipeline Behavior

| Stage | tier_1 | tier_2 | tier_3 | tier_4 |
|---|---|---|---|---|
| S1 harvest | always | always | always | conditional |
| S4 detect | always | always | always | burst-only |
| S5 verify | always | always | always | burst-only |
| S6 reason | always | always | skip | skip |
| S7 score | always | always | always | burst-only |
| S8 gate | full | full | full | full |
| S9 persist | always | always | always | always |

For tier_3 and tier_4, **fewer Signals are produced** because the cheaper path is used. This is by design.

### 3.2 Cost Implications

Approximate cost per entity per day:

| Tier | Cost/entity/day | Active entities |
|---|---|---|
| tier_1 | $0.50 | 20–50 |
| tier_2 | $0.20 | 50–150 |
| tier_3 | $0.05 | 100–500 |
| tier_4 | $0.01 | unlimited |

These are targets, not guarantees. Cost is a function of Signal volume, not just tier.

---

## 4. Coverage Targets

```
CoverageTargets := {
  min_signals_per_week? : int,        // alert if breached
  max_signals_per_week? : int,        // alert if breached (suspect flood)
  latency_p95_minutes?  : int,        // alert if breached
  calibration_floor?    : float[0,1]  // alert if breached
}
```

Default coverage targets per tier:

| Tier | min/wk | max/wk | latency p95 |
|---|---|---|---|
| tier_1 | 1 | 30 | 240 min |
| tier_2 | 1 | 20 | 360 min |
| tier_3 | 0 | 10 | 720 min |
| tier_4 | 0 | 5 | n/a |

A breach triggers an alert in the weekly review ([13 §4](13_report_template.md)).

---

## 5. Tier Change Lifecycle

A Company moves between tiers via a **TierChange** event. These are append-only.

```
TierChange := {
  from_tier   : Tier,
  to_tier     : Tier,
  changed_at  : ISO8601,
  changed_by  : string,
  reason      : string,             // free text, required
  evidence    : [URL]?              // optional supporting material
}
```

Tier changes are reversible (just add another TierChange). History is preserved.

### 5.1 Triggers

| Trigger | Source | Action |
|---|---|---|
| Manual decision | Curator | Curator adds TierChange with reason |
| Coverage gap detected | System (zero Signals for 30d) | System suggests demotion to Curator |
| Calibration collapse | System (per-entity corroboration < 30%) | System suggests demotion |
| Stale financials | System (snapshot > 90d) | Alert Curator; demotion optional |
| M&A / delisting | Signal | Status change in Company master; remove from watchlist |

### 5.2 Demotion Rules

```
IF entity has 0 Signals for 30 consecutive days
   AND tier ∈ {tier_1, tier_2}
   AND not in known-corporate-action window
THEN propose demotion (Curator decides)
```

```
IF entity corroboration_rate < 0.30 over last 20 Signals
THEN propose demotion or curator review
```

Demotion is never automatic; it always requires Curator sign-off.

---

## 6. Adding an Entity

To add an entity to the watchlist:

1. Verify Company exists in master ([12](12_company_schema.md)); add if missing
2. Assign tier per Curator decision
3. Populate `coverage_targets` (defaults apply if omitted)
4. Set `added_at`, `added_by`
5. Optional `notes`
6. Trigger one manual cycle for the entity to seed its baseline

### 6.1 Tier Selection Guidance

Suggested rubric:

| Use case | Tier |
|---|---|
| Active portfolio position, daily review | tier_1 |
| On portfolio, weekly review | tier_2 |
| Sector peer, monitoring | tier_3 |
| Event-driven (earnings, regulatory) | tier_4 |

---

## 7. Removing an Entity

Removal is **soft**: the `WatchlistEntry.status` is set to `removed`, not deleted.

```
WatchlistEntry.status := enum[active, paused, removed]
```

| Status | Meaning |
|---|---|
| `active` | Normal pipeline coverage |
| `paused` | Temporarily not covered (e.g., M&A pending) |
| `removed` | No longer in watchlist; retained for audit |

A removed entity retains its history but receives no new Signals. Re-adding is a new `WatchlistEntry`.

---

## 8. Watchlist Policies

```
WatchlistPolicies := {
  max_tier_1          : int,           // hard cap on tier_1 count
  max_tier_2          : int,
  max_tier_3          : int,
  max_tier_4          : int,
  review_cadence_days : int,           // curator must review each entity this often
  staleness_alert_days: int,           // alert if 0 Signals for this many days
  calibration_floor   : float[0,1],    // global floor for corroboration rate
  auto_demote_enabled : bool           // allow system-initiated demotion suggestions
}
```

### 8.1 Default Policies (Phase 1)

```yaml
max_tier_1: 30
max_tier_2: 100
max_tier_3: 500
max_tier_4: 2000
review_cadence_days: 90
staleness_alert_days: 30
calibration_floor: 0.60
auto_demote_enabled: true
```

### 8.2 Hard Caps

The hard caps on tier_1 and tier_2 are deliberate. tier_1 represents the deepest coverage and curator attention. Beyond ~30 tier_1 entities, attention dilutes. Curator may request a cap raise with written justification.

### 8.3 Soft Caps

tier_3 and tier_4 caps are soft — the system warns when approaching but does not block additions.

---

## 9. Curation Workflow

### 9.1 Curator Sessions

A curator session is a planned review:

```
Session := {
  started_at  : ISO8601,
  curator_id  : string,
  scope       : { tiers: [Tier], sectors: [string], explicit_ids: [string] },
  actions     : [CurationAction],
  ended_at    : ISO8601
}

CurationAction := enum[
  add_entity,
  remove_entity,
  change_tier,
  adjust_score,         // see [06 §8](06_scoring_framework.md)
  mark_noise,           // see [02 §A8](02_agent_constitution.md)
  mark_redundant,
  bind_industry_position, // see [11 §8.3](11_industry_mapping.md)
  update_notes
]
```

All actions are append-only and audit-logged.

### 9.2 Suggested Monthly Flow

1. Review weekly report's calibration (§3 of weekly review)
2. Review coverage gaps section
3. Review system-suggested demotions
4. Adjust tiers as needed
5. Note any new entities to add
6. Bind to industry chains if missing
7. Approve / reject any held Signals

---

## 10. System-Initiated Actions

Some actions the system takes without Curator input:

| Action | Trigger | Notes |
|---|---|---|
| Staleness alert | 0 Signals for `staleness_alert_days` | Notifies Curator; does not auto-demote |
| Calibration alert | corroboration < floor | Notifies Curator |
| Demotion suggestion | per §5.2 rules | Curator confirms |
| Coverage gap fill | Watchlist target not met | Curator adds entities |

System-initiated actions are **proposals** until Curator confirms.

---

## 11. Pipeline Integration

### 11.1 Entity Filter at S1

The harvester filters raw items by entity reference. Items referencing watchlist entities are prioritized:

| Item priority | Condition |
|---|---|
| P0 (immediate) | tier_1 entity + burst trigger condition |
| P1 (next cycle) | tier_1 OR tier_2 entity |
| P2 (within 2 cycles) | tier_3 entity |
| P3 (within 4 cycles) | tier_4 entity |
| Background | off-watchlist entity (still indexed, low priority) |

### 11.2 Burst Trigger Weighting

Burst trigger ([03 §5.2](03_workflow_constitution.md)) weights by tier:

| Tier | Burst weight |
|---|---|
| tier_1 | 3.0 |
| tier_2 | 2.0 |
| tier_3 | 1.0 |
| tier_4 | 0.5 |

A burst threshold hit counts more for high-tier entities.

### 11.3 Reasoning Skipping for Lower Tiers

For tier_3 and tier_4, the analyst agent is **skipped** (per §3.1). This means:
- `reasoning` field is null in Signal
- `metadata.reasoning_skipped: true` is set
- Reports include a banner for tier_3/4 Signals

This is the explicit cost-coverage trade-off.

---

## 12. Watchlist Reports

### 12.1 Weekly Watchlist Summary (in §4 of Weekly Review)

| Tier | Active | 0-Signal | Calibration | Top mover |
|---|---|---|---|---|
| tier_1 | 28 | 0 | 76% | ACME.US |
| tier_2 | 87 | 5 | 71% | BETA.US |
| tier_3 | 312 | 28 | 64% | GAMMA.TW |
| tier_4 | 1450 | 412 | 58% | DELTA.KR |

### 12.2 Quarterly Review

A separate quarterly report covers:
- Watchlist additions / removals
- Tier churn
- Per-entity calibration trends
- Curator session audit
- Coverage gap analysis
- Cost per tier vs target

---

## 13. Worked Example

### 13.1 Adding an Entity

```yaml
- action: add_entity
  company_id: NEWCO.US
  tier: tier_2
  coverage_targets:
    min_signals_per_week: 1
    max_signals_per_week: 10
    latency_p95_minutes: 360
  notes: "New position; track through next 2 earnings cycles."
  added_by: curator_002
  added_at: 2026-07-16T10:00:00Z
```

### 13.2 Demoting an Entity

```yaml
- action: change_tier
  company_id: QUIET.US
  from_tier: tier_2
  to_tier: tier_3
  reason: "0 Signals for 45d; corroboration 22% on last 12 Signals."
  evidence:
    - https://internal/calibration/quiet.us
  changed_by: curator_001
  changed_at: 2026-07-16T10:15:00Z
```

### 13.3 Marking a Signal as Noise

```yaml
- action: mark_noise
  signal_id: 01HK3...
  reason: "Source retracted announcement; original Signal now baseless."
  by: curator_001
  at: 2026-07-16T10:20:00Z
```

The Signal's status becomes `rejected`; the `OverrideRecord` records the original and the override.

---

## 14. Edge Cases

| Case | Handling |
|---|---|
| Entity at hard cap, Curator wants to add another | Curator must first remove or demote another entity |
| Tier change for entity with active cluster | Cluster retains Signals at old tier classification for audit; new tier applies to future Signals |
| System suggests demotion, Curator disagrees | Curator adds note explaining; system suggestion logged but not enforced |
| Coverage target breach across multiple entities | Weekly review flags as systemic; pipeline capacity review |
| Watchlist reference out of sync with Company master | Auto-sync; Curator notified |
| Curator session overlap | Last-write-wins per action; full audit log preserves order |

---

## 15. Anti-Patterns

- ❌ Adding entities without Curator review (auto-additions are proposals only)
- ❌ Auto-demotion without Curator confirmation
- ❌ Same entity in multiple tiers simultaneously
- ❌ tier_1 count exceeding cap without documented justification
- ❌ Removing entities solely because they're noisy — adjust detection first
- ❌ Changing tiers without recording a reason

---

## 16. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold |

Adding/removing tiers, changing default policies, or changing hard caps is MAJOR. Adding curation actions is MINOR. Wording fixes are PATCH.