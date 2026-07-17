# 01 · Signal Constitution

> **Document role:** Definitional contract. Establishes what counts as a Signal, what does not, and how Signals are distinguished from noise. Authoritative for downstream agents and reports.

---

## 1. Definition (single source of truth)

A **Signal** is a structured, evidence-backed claim that an observable change has occurred to an entity and that this change may materially affect the entity's forward-looking investment thesis.

Formally:

```
Signal := {
  id          : ULID,
  entity_ref  : EntityRef,         // see 04_data_schema.md#entity-ref
  type        : SignalType,        // enum, see 10_signal_taxonomy.md
  claim       : string,            // one sentence, falsifiable
  direction   : {bullish | bearish | neutral},
  horizon     : {intraday | short | medium | long},
  evidence    : Evidence[≥1],      // see 04_data_schema.md#evidence
  timestamp   : ISO8601,           // when the underlying event occurred
  detected_at : ISO8601,           // when the system first emitted the signal
  score       : Score,             // see 06_scoring_framework.md
  status      : {draft | verified | active | decayed | rejected},
  provenance  : Provenance,        // see 04_data_schema.md#provenance
}
```

A Signal **must** satisfy these three invariants:

1. **Falsifiable claim** — the `claim` field can in principle be proven wrong by future evidence.
2. **Non-empty evidence** — at least one Evidence object with a retrievable `source_url` or document hash.
3. **Traceable provenance** — `provenance.agent_chain` records every agent that touched the Signal.

Any object failing one of these invariants is **not** a Signal and must not enter the downstream pipeline.

---

## 2. What a Signal Is NOT

To prevent ambiguity, the following are explicitly **not** Signals:

| Construct | Why it is not a Signal |
|---|---|
| **Opinion** | Lacks falsifiability and evidence |
| **News item** | Raw, unstructured; has no claim about impact |
| **Price quote** | Continuous data, not a discrete change |
| **Forecast** | Predictive, not a record of observed change |
| **Gossip / rumor** | Source is not primary or verifiable |
| **Composite thesis** | Multi-claim — must be decomposed into Signals first |
| **Duplicate** | Same claim + entity + 24h window as a prior Signal |

A composite thesis lives in `05_reasoning_framework.md` (synthesis layer) and **references** Signals; it is never itself a Signal.

---

## 3. Signal Lifecycle

```
            ┌─────────────────────────────────────────────────────┐
            │                                                     │
            ▼                                                     │
       ┌────────┐    ┌──────────┐    ┌─────────┐    ┌────────┐    │
emit → │ draft  │ →  │ verified │ →  │ active  │ →  │decayed │ ───┘
       └────────┘    └──────────┘    └─────────┘    └────────┘
            │              │
            │              ▼
            │         ┌──────────┐
            └───────→ │ rejected │
                      └──────────┘
```

| Status | Meaning | Entered by |
|---|---|---|
| `draft` | Initial emission from `detector` agent, evidence attached | `detector` |
| `verified` | `verifier` agent confirms source URL is live and quote matches | `verifier` |
| `active` | Passes scoring threshold and is published into queue | `scorer` (via gating, [03 §S8](03_workflow_constitution.md)) |
| `decayed` | Older than horizon window; no longer actionable | `decay_worker` |
| `superseded` | Replaced by a newer Signal on the same entity/claim (per [§4](01_signal_constitution.md) cardinality rules) | `dedup` stage / `decay_worker` |
| `rejected` | Fails verification, evidence insufficient, or marked `noise` by `curator` | `verifier` / `curator` |

A Signal in `draft` state **must not** appear in any user-facing report.

---

## 4. Cardinality Rules (Dedup Logic)

To prevent alert fatigue, the following equivalence rules collapse Signals:

| Rule | Definition | Action |
|---|---|---|
| Same-claim 24h | Two Signals on same `entity_ref` + near-identical `claim` within 24h | Keep the higher-score one; mark the other `superseded` |

> Note: the `superseded` status is added to the lifecycle enum to support cardinality-rule outcomes. See the Status table in §3.
| Same-event cluster | Multiple Signals referencing the same underlying event (e.g., one Earnings Signal + one Guidance Signal from same call) | Promote the highest-impact type; demote others to `supporting` |
| Type rotation | Same `entity_ref` produces > 5 Signals of same `type` in 7 days | Throttle; keep top 3 by score, decay rest as `redundant` |

Dedup is deterministic, not LLM-driven. Implementation: see [03_workflow_constitution.md#dedup-stage](03_workflow_constitution.md).

---

## 5. Quality Gates

A Signal cannot transition from `draft` to `verified` unless **all** of:

| Gate | Pass condition |
|---|---|
| Source reachability | `source_url` returns HTTP 2xx within 30s of fetch |
| Quotation match | If `evidence.quote` is given, the quoted substring appears verbatim in fetched source |
| Entity resolution | `entity_ref` resolves to a Company in [12_company_schema.md](12_company_schema.md) |
| Taxonomy match | `type` is a valid value in [10_signal_taxonomy.md](10_signal_taxonomy.md) |
| Score complete | `score` populated across all five dimensions per [06_scoring_framework.md](06_scoring_framework.md) |
| Non-duplicate | Does not violate any rule in §4 |

A Signal that fails any gate is sent back to `detector` for re-work **once**, or routed to `rejected` if re-work also fails.

---

## 6. Working Examples

### Example 1 — Valid Signal

```yaml
id: 01HXY...ULID
entity_ref: { kind: company, id: ACME.US }
type: capital_action
claim: "ACME announced a $500M share buyback program, ~3.2% of market cap."
direction: bullish
horizon: short
evidence:
  - source_url: "https://www.sec.gov/Archives/edgar/data/.../8-k.htm"
    source_type: regulatory_filing
    retrieved_at: 2026-07-16T13:05:00Z
    quote: "The Board authorized a $500 million share repurchase program."
    document_hash: sha256:ab12...
timestamp: 2026-07-16T13:00:00Z
detected_at: 2026-07-16T13:11:42Z
score: { magnitude: 0.55, confidence: 0.92, timeliness: 0.80, novelty: 0.70, actionability: 0.75, composite: 0.74 }
status: active
provenance:
  agent_chain: [harvester, detector, verifier, analyst, scorer]
  agent_versions: { detector: "1.4.2", verifier: "2.1.0", analyst: "0.3.1", scorer: "1.2.0" }
  prompt_versions: { detector/extract_signals: "1.4.2", scorer/score_dimensions: "1.2.0" }
  model_versions: { entity_extraction: "claude-haiku-4-5-20251001", score: "claude-opus-4-8" }
  temperature: 0.0
  cycle_id: 01HXA...
  emitted_at: 2026-07-16T13:11:42Z
```

### Example 2 — Invalid Signal (must not emit)

```yaml
claim: "ACME might be undervalued."
evidence: []              # ❌ Rule 2 violated
direction: bullish
```

This is opinion, not a Signal.

### Example 3 — Decay

A "Q1 earnings beat" Signal emitted on 2026-04-30 with `horizon: short` is auto-`decayed` on 2026-05-15 (15 trading days later, beyond the short-horizon window).

---

## 7. Versioning of This Document

Changes to invariant rules (§1, §2, §4, §5) require **major version bump** and migration note in `09_development_roadmap.md`. Changes to examples (§6) require only a minor bump.