# 11 · Industry Mapping

> **Document role:** Industry chain model. Defines how companies relate to industries and to each other (supply chain, customer chain, competitive set). Used by the `analyst` agent for causal reasoning and by the `synthesizer` for cross-entity Signals.
>
> Requires: `00_project_context.md ≥ 0.2`, `04_data_schema.md ≥ 1.0`, `12_company_schema.md ≥ 0.1`.

---

## 1. Why Industry Mapping Exists

A Signal on Company A often **materially affects** Companies B, C, D via industry chain. Without an explicit model of those relationships:

- The analyst cannot identify legitimate second-order CausalLinks ([05 §2.2](05_reasoning_framework.md))
- Cross-entity contagion detection ([00 §10.3](00_project_context.md)) is impossible
- Supply chain surprises blindside the system

An industry map is a **directed graph** of nodes (industry positions) and edges (relationships). Companies attach to one or more positions.

---

## 2. Core Concepts

### 2.1 Industry Chain Node

A **node** represents a position in the value chain. Not a company — a *role*.

```
IndustryNode := {
  id              : string,             // ULID or kebab-case slug
  name            : string,
  level           : enum[upstream, midstream, downstream, distribution, end_market],
  description     : string,
  gics_sector?    : string,             // optional top-level mapping
  parent_id?      : string,             // for hierarchical chains
  children_ids    : [string]
}
```

### 2.2 Chain Relationship

A **relationship** connects two nodes. Edges are typed and weighted.

```
ChainEdge := {
  from            : IndustryNodeId,
  to              : IndustryNodeId,
  type            : enum[supplier, customer, substitute, complement, distribution, regulator],
  strength        : enum[primary, secondary, tertiary],     // how dominant is this relationship
  description     : string
}
```

### 2.3 Why a Separate Entity from Company

A Company occupies **one or more** IndustryNode positions. A single Company can be both an upstream supplier (to one customer) and a midstream producer (for its own product). Modeling this multi-position membership is essential.

Example: ACME Semiconductor — node "wafer-fab" (midstream) AND node "foundry-service" (supplier to fabless designers).

---

## 3. Chain Levels

The chain has **five canonical levels**. A Signal typically cascades **downstream** (impact flows from upstream to end-market).

| Level | Definition | Examples |
|---|---|---|
| `upstream` | Raw inputs, basic materials | Mining, agriculture, energy |
| `midstream` | Intermediate processing / manufacturing | Refining, fab, assembly |
| `downstream` | Final-product manufacturing | OEM, brand owners |
| `distribution` | Logistics, retail, wholesale | Carriers, e-commerce, big-box |
| `end_market` | Final demand | Consumer, enterprise, government |

A typical chain traversal:

```
upstream → midstream → downstream → distribution → end_market
```

Most causal impact cascades traverse 2–3 levels. Cascades beyond 4 levels are usually speculative (and the analyst agent limits CausalLink hops per [05 §2.2](05_reasoning_framework.md)).

---

## 4. Relationship Types

| Type | Definition | Example |
|---|---|---|
| `supplier` | `from` provides inputs to `to` | Wafer fab → chip designer |
| `customer` | Inverse of supplier | Chip designer → OEM |
| `substitute` | `from` competes with `to` for same end demand | Pepsi ↔ Coca-Cola |
| `complement` | `from` and `to` are consumed together | Printers ↔ ink |
| `distribution` | `from` distributes `to`'s output | Retailer → brand |
| `regulator` | `from` sets rules on `to` | FDA → pharma |

### 4.1 Strength

| Strength | Definition |
|---|---|
| `primary` | The dominant input/output; entity cannot operate without it |
| `secondary` | Important but substitutable |
| `tertiary` | Minor; multiple alternatives |

A `primary` edge carries stronger causal weight in reasoning than `tertiary`.

---

## 5. Worked Example — Semiconductor Industry Chain

```
[Silicon mining]  ──supplier(primary)──►  [Wafer fab]
[Wafer fab]       ──supplier(primary)──►  [Chip designer (fabless)]
[Wafer fab]       ──substitute(secondary)──►  [IDM (integrated)]
[Chip designer]   ──supplier(primary)──►  [OEM]
[OEM]             ──supplier(primary)──►  [Distribution]
[Distribution]    ──supplier(primary)──►  [End market]
[End market]      ──demand──►  [Distribution]
[Regulator (export controls)] ──regulator(primary)──►  [Chip designer]
```

A Signal on "wafer fab" capacity cuts propagates:
- `primary` to fabless designers (input shortage)
- `secondary` to OEMs (chip shortage → production cuts)
- `secondary` to end market (device price increases)

The analyst agent uses this map to populate `CausalLink`s on the original Signal ([05 §2.2](05_reasoning_framework.md)).

---

## 6. Mapping Schema (Persisted)

The chain is stored as nodes and edges:

```
IndustryChain := {
  schema_version : semver,
  nodes          : [IndustryNode],
  edges          : [ChainEdge],
  last_updated   : ISO8601,
  updated_by     : string,
  provenance     : { sources: [URL], notes: string }
}
```

This is a **single artifact** per chain family (e.g., `semiconductors.v3.yaml`). Chains are versioned.

---

## 7. Company-to-Chain Binding

Each Company ([12_company_schema.md §9](12_company_schema.md)) carries:

```
Company.industry_positions := [
  { node_id: "wafer-fab", share: float[0,1], note?: string },
  { node_id: "foundry-service", share: float[0,1] }
]
```

`share` indicates the fraction of the Company's revenue derived from this position (sum should equal 1.0 ± 0.05 for a pure-play; multi-position companies may have several).

When a Signal lands on a Company, the analyst ([02 §A4](02_agent_constitution.md)):
1. Looks up the Company's `industry_positions`
2. For each position, traverses outgoing `ChainEdge`s
3. Identifies likely affected entities
4. Generates `CausalLink`s per [05 §2.2](05_reasoning_framework.md)

---

## 8. Building and Maintaining the Chain

### 8.1 Initial Build

For each chain family:
1. Start from a top-level taxonomy (e.g., GICS sector)
2. Identify the canonical value chain (level-by-level)
3. Populate nodes
4. Identify primary, secondary, tertiary edges from public sources (industry reports, 10-K segment disclosures)
5. Bind to Companies in the watchlist

### 8.2 Maintenance Triggers

A chain is updated when **any** of:
- A new Company enters the watchlist that doesn't map cleanly to existing nodes
- A major M&A alters a chain (acquirer + target may map to same node)
- A regulator adds new rules creating a new edge
- Annual review catches structural shifts

### 8.3 Curator Authority

Curator ([02 §A8](02_agent_constitution.md)) is the only authorized source for chain edits:
- `add_node`
- `add_edge`
- `update_strength`
- `bind_company`

All chain edits are versioned and audit-logged. Edits do not retroactively rewrite past Signals.

---

## 9. Causal Inference Rules

The analyst agent follows these rules when traversing chains:

| Rule | Detail |
|---|---|
| Hop limit | Max 3 edges from source Signal's entity |
| Strength weighting | `primary` edges contribute full causal weight; `secondary` 0.5; `tertiary` 0.25 |
| Bidirectional | `supplier` edges can be traversed in reverse when cause is downstream |
| Negative-link pruning | If an entity is in both `supplier` and `substitute` relations to source, suppress the weaker |
| Same-entity dedup | If two paths lead to same entity, take the stronger |

These rules prevent combinatorial explosion of CausalLinks.

---

## 10. Cross-Chain Effects

Some industries touch multiple chains (e.g., semiconductors feed both consumer electronics and defense). The map supports **shared nodes**:

```
[Chip designer] ──► [Smartphone OEM]     (consumer chain)
[Chip designer] ──► [Defense OEM]        (defense chain)
```

A Signal on `[Chip designer]` cascades into both. The analyst emits CausalLinks to both downstream chains but caps at 5 total CausalLinks per Signal ([05 §2.2](05_reasoning_framework.md)).

---

## 11. Special Industry Types

### 11.1 Financials

Banks, insurers, asset managers have different chain semantics:
- `depositor` ↔ `bank` is a *liability* relation, not a supplier one
- `bank` ↔ `borrower` is an *asset* relation

For financials, treat chain level as a flat sector with no upstream/midstream/downstream distinction. Use a separate `FinancialChain` schema if needed in v1.4+.

### 11.2 Commodities

For commodity-producing entities:
- `mine/well/field` is upstream
- Multiple midstream processors compete
- Substitute relations dominate over supplier relations

### 11.3 Regulated Industries

For industries with strong regulators (pharma, financials, telecom, utilities):
- `regulator` edges are first-class
- Regulatory Signals cascade to `regulator`'s targets

---

## 12. Chain Coverage Targets

| Phase | Target coverage |
|---|---|
| Phase 1 | 1 chain (semiconductors) |
| Phase 2 | 5 chains (consumer electronics, software, semis, energy, financials-light) |
| Phase 5 | 20+ chains |
| Phase 6 | Full GICS sector coverage |

---

## 13. Worked Reasoning Example

### Input Signal

```yaml
signal:
  entity_ref: { kind: company, id: ACME.WA }
  type: operational
  claim: "ACME wafer fab utilization fell to 65% from 82% last quarter."
  direction: bearish
  evidence: [...]
```

### Chain Lookup

```
ACME.WA.industry_positions:
  - { node_id: "wafer-fab", share: 0.85 }
  - { node_id: "foundry-service", share: 0.15 }

"wafer-fab" outgoing edges:
  → "chip-designer" (supplier, primary)
  → "IDM" (substitute, secondary)

"chip-designer" outgoing edges:
  → "OEM-consumer" (supplier, primary)
  → "OEM-defense" (supplier, secondary)
```

### Generated CausalLinks

```yaml
causality:
  - to_entity: { kind: company, id: BETA.US }     # fabless designer using ACME
    mechanism: "ACME fab utilization cut implies capacity tightening; BETA's input supply may be constrained, raising wafer prices."
    likelihood: high
    time_horizon: short

  - to_entity: { kind: company, id: GAMMA.TW }    # another fab competing
    mechanism: "If ACME is losing customers, GAMMA may capture share; or sector-wide demand is weakening — direction depends on macro."
    likelihood: medium
    time_horizon: medium

  - to_entity: { kind: company, id: DELTA.KR }    # OEM-consumer
    mechanism: "Chip supply tightening could push chip prices higher; DELTA's COGS rises 1–3% within 2 quarters."
    likelihood: medium
    time_horizon: medium
```

The `analyst` agent produces this from the chain map + reasoning prompt.

---

## 14. Edge Cases

| Case | Handling |
|---|---|
| Company has no `industry_positions` entry | Skip cross-chain reasoning; reasoning only considers intra-entity effects |
| Two chains disagree on an edge | Take the more recent; flag the conflict in `metadata` |
| Edge strength is missing | Default to `secondary` |
| Cycle detected in chain | Drop the back-edge to prevent infinite traversal |
| Chain artifact corrupt | Fall back to industry-only reasoning (no Company-level CausalLinks) |

---

## 15. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold |

Adding new relationship types (§4), new level semantics (§11), or new traversal rules (§9) is MAJOR. Adding chain artifacts is tracked separately via chain YAML files. Wording fixes are PATCH.