# GLOSSARY — SIGNAL Term Dictionary

> **Document role:** Single source of truth for every term used across the SIGNAL spec set. Each term has one canonical name, one definition, and one owner document. Other documents must use the canonical name.
>
> Read alongside: [INVARIANTS.md](INVARIANTS.md), [SPEC_VERSION.md](SPEC_VERSION.md), [GLOSSARY.md](GLOSSARY.md).

---

## 1. Reading Guide

Each entry below contains:

| Field | Meaning |
|---|---|
| **Term** | The canonical name (lowercase, single word or snake_case for multi-word) |
| **Aliases** | Other names that appear in the codebase or older docs — **do not use** |
| **Definition** | One or two sentences, falsifiable |
| **Owner doc** | The document where the authoritative definition lives |
| **First introduced** | SPEC_VERSION when this term first appeared |
| **Related** | Other terms to read together |

A term is added to this glossary when it appears in **three or more** documents OR is referenced as a single concept with specific semantics.

---

## 2. A–C

### Agent

A named, versioned software component that performs one well-defined transformation in the SIGNAL pipeline. Agents may invoke LLMs; deterministic functions are not agents (they are **functions** or **stages**).

- **Aliases:** none (avoid "worker", "module", "service" in spec docs)
- **Owner doc:** [02_agent_constitution.md](02_agent_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Function, Workflow, Stage, AgentRef

### ADR (Architecture Decision Record)

A short document that records a single significant design decision: context, decision, alternatives, trade-offs, consequences.

- **Aliases:** none
- **Owner doc:** [GOVERNANCE.md §3](GOVERNANCE.md)
- **First introduced:** SPEC_VERSION 1.3.0
- **Related:** RFC

### Authoritative Source

The single document where a schema, rule, or contract is defined. Other documents must reference, never redefine.

- **Aliases:** "canonical", "source of truth"
- **Owner doc:** [REVIEW_NOTES §7.3](REVIEW_NOTES.md)
- **First introduced:** SPEC_VERSION 1.1
- **Related:** Single Source of Truth, Authority Table

### Authority Table

The table in [REVIEW_NOTES §7.3](REVIEW_NOTES.md) listing which document owns which schema field.

- **Aliases:** "schema authority table"
- **Owner doc:** [REVIEW_NOTES.md](REVIEW_NOTES.md)
- **First introduced:** SPEC_VERSION 1.1
- **Related:** Authoritative Source

### Band

A categorical bucket for a Signal's composite score: `high`, `medium`, or `low`.

- **Aliases:** none
- **Owner doc:** [04 §7 Score](04_data_schema.md), [06 §5](06_scoring_framework.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Composite Score

### Burst Trigger

A high-priority workflow trigger fired by breaking-news heuristics. Drives W2 `burst_cycle`.

- **Aliases:** "event trigger"
- **Owner doc:** [03 §5.2](03_workflow_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Workflow, Trigger

### CausalLink

A structured claim in a `Reasoning.causality[]` array: downstream effect, mechanism, likelihood, time horizon.

- **Aliases:** none (avoid "downstream link")
- **Owner doc:** [04 §8 Reasoning.CausalLink](04_data_schema.md), [05 §2.2](05_reasoning_framework.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Reasoning, IndustryChain

### ChainEdge

A typed, weighted edge in an industry chain graph.

- **Aliases:** none
- **Owner doc:** [11 §2.2](11_industry_mapping.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** IndustryNode, IndustryChain

### Claim

The one-sentence falsifiable assertion that a Signal makes about an entity. The core content of a Signal.

- **Aliases:** "assertion", "signal claim"
- **Owner doc:** [01 §1](01_signal_constitution.md), [04 §4.1 Signal.claim](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Signal, Evidence

### Cluster

A group of Signals linked by a `cluster_id`. Used for both same-event clusters and `ThesisDelta` clusters.

- **Aliases:** "signal cluster"
- **Owner doc:** [04 §11 Cluster](04_data_schema.md), [01 §4](01_signal_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** ThesisDelta, cluster_id

### Cluster_ID

The ULID identifying a Cluster, attached to every Signal that is part of that cluster.

- **Aliases:** "clusterId" (deprecated)
- **Owner doc:** [04 §4.1 Signal.cluster_id](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Cluster, ThesisDelta

### Composite Score

The weighted-sum aggregate of the five Score dimensions, computed deterministically by `compute_composite()`. The single number that drives gating.

- **Aliases:** "composite", "score.composite"
- **Owner doc:** [06 §4](06_scoring_framework.md), [04 §7 Score.composite](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Score, Band

### Confidence

One of the five Score dimensions, measuring certainty about the claim itself (not its impact). Range [0, 1].

- **Aliases:** none (avoid "certainty")
- **Owner doc:** [06 §2.2](06_scoring_framework.md), [04 §7 Score.confidence](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Score, Composite Score

### Curator

The only agent that accepts human-generated input. Applies overrides; never blocks the pipeline.

- **Aliases:** "human override agent", "reviewer"
- **Owner doc:** [02 §A8](02_agent_constitution.md), [02 §11](02_agent_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** OverrideRecord, Watchlist

### Cycle

One execution of a Workflow, from trigger to completion. Identified by a ULID `cycle_id`. The unit of audit and replay.

- **Aliases:** "workflow run", "execution"
- **Owner doc:** [03 §8](03_workflow_constitution.md), [04 §10.5 CycleReport](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Workflow, CycleReport, cycle_id

### CycleReport

The structured artifact emitted by every cycle, containing durations, outcomes, cost, errors.

- **Aliases:** "cycle summary"
- **Owner doc:** [04 §10.5](04_data_schema.md), [03 §11](03_workflow_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Cycle, FailureEvent

### cycle_id

The ULID (26-char Crockford base32) identifying a Cycle. Appears in every artifact produced by that cycle.

- **Aliases:** "cycleId", "run_id"
- **Owner doc:** [03 §8.2](03_workflow_constitution.md), [04 §3.2](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Cycle, INV-9

---

## 3. D–F

### Direction

The directional implication of a Signal: `bullish`, `bearish`, or `neutral`. Set per Signal, not per type.

- **Aliases:** none
- **Owner doc:** [04 §4.1 Signal.direction](04_data_schema.md), [10 §4](10_signal_taxonomy.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Signal, Type

### Durability

A reasoning attribute describing how long the effect of a Signal is expected to persist: `transient`, `short`, or `structural`.

- **Aliases:** "duration"
- **Owner doc:** [04 §8 Reasoning.durability](04_data_schema.md), [05 §2.3](05_reasoning_framework.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Reasoning, Horizon

### EntityRef

The reference from a Signal (or CausalLink) to its target: `{ kind, id }` where kind is `company`, `industry`, `macro_variable`, or `sector`.

- **Aliases:** "entity reference", "entity_id" (deprecated)
- **Owner doc:** [04 §3.1](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Company, IndustryNode

### Evidence

A pointer to a primary source that supports a Signal's claim. Always non-empty; verified by the `verifier` agent.

- **Aliases:** "source", "citation"
- **Owner doc:** [01 §1](01_signal_constitution.md), [04 §5](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Signal, INV-1

### FailureEvent

A structured record of a failure (HTTP, LLM, schema, etc.). Linked from CycleReport.

- **Aliases:** "error event", "FailureEvent"
- **Owner doc:** [04 §10.4](04_data_schema.md), [02 §12](02_agent_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** CycleReport, error_code

### Function (Pipeline Function)

A deterministic transformation in the workflow that is not an Agent (e.g., `dedup()`, `gate()`, `compute_composite()`).

- **Aliases:** "stage function"
- **Owner doc:** [03 §3](03_workflow_constitution.md), [02 §1](02_agent_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Agent, Stage

---

## 4. G–L

### Gating

The S8 stage that decides a Signal's `status` (`active`, `held`, or `rejected`) based on its composite score and confidence.

- **Aliases:** "stage 8", "the gate"
- **Owner doc:** [03 §S8](03_workflow_constitution.md), [06 §5.1](06_scoring_framework.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Composite Score, Band

### Horizon

A Signal attribute describing how long the Signal's effect is expected to persist: `intraday`, `short`, `medium`, or `long`. Distinct from `durability`.

- **Aliases:** "time horizon"
- **Owner doc:** [04 §4.1 Signal.horizon](04_data_schema.md), [06 §3](06_scoring_framework.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Durability, Signal

### IndustryChain

A directed graph of IndustryNodes and ChainEdges representing one industry family (e.g., semiconductors).

- **Aliases:** "supply chain map", "value chain"
- **Owner doc:** [11 §6](11_industry_mapping.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** IndustryNode, ChainEdge

### IndustryNode

A position in the value chain (e.g., "wafer-fab"), not a company. Companies occupy one or more nodes.

- **Aliases:** "chain position"
- **Owner doc:** [11 §2.1](11_industry_mapping.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** IndustryChain, Company

### Invariant

A system-wide rule that can never be violated. See [INVARIANTS.md](INVARIANTS.md).

- **Aliases:** none
- **Owner doc:** [INVARIANTS.md](INVARIANTS.md)
- **First introduced:** SPEC_VERSION 1.3.0
- **Related:** Constraint, Rule

### Lifecycle (Signal Lifecycle)

The set of valid `status` values for a Signal and the allowed transitions between them.

- **Aliases:** "signal lifecycle", "status graph"
- **Owner doc:** [01 §3](01_signal_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Status, INV-6

---

## 5. M–R

### Magnitude

One of the five Score dimensions, measuring the size of the Signal's impact. Range [0, 1].

- **Aliases:** none
- **Owner doc:** [06 §2.1](06_scoring_framework.md), [04 §7 Score.magnitude](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Score, Composite Score

### Metadata

The free-form but typed bag attached to a Signal for fields not in the core schema.

- **Aliases:** none
- **Owner doc:** [04 §9](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Signal, OverrideRecord

### OverrideRecord

An append-only record of a Curator action. Attached to a Signal's `Provenance.override_records[]` or a Company's provenance edits.

- **Aliases:** "override entry", "curator action"
- **Owner doc:** [04 §6](04_data_schema.md), [02 §A8](02_agent_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Curator, INV-11

### Phase

A milestone in the development roadmap. Eight phases (0–7) per [09 §2](09_development_roadmap.md).

- **Aliases:** "milestone"
- **Owner doc:** [09_development_roadmap.md](09_development_roadmap.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Roadmap, Release

### PrecedentRef

A reference to a prior Signal with a similar type/direction/entity context, used by the analyst agent.

- **Aliases:** none
- **Owner doc:** [04 §8 PrecedentRef](04_data_schema.md), [05 §3](05_reasoning_framework.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Reasoning

### Prompt

A versioned markdown file in `prompts/<agent>/<purpose>/vX.Y.Z.md` that drives an LLM call.

- **Aliases:** "LLM prompt", "prompt template"
- **Owner doc:** [07_prompt_guidelines.md](07_prompt_guidelines.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Agent, Prompt Registry

### Provenance

The audit metadata attached to every Signal: agent chain, versions, timestamps, overrides.

- **Aliases:** "audit trail", "Provenance"
- **Owner doc:** [04 §6](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Signal, INV-3

### RawDocument

The cleaned, normalized form of a source document before any signal extraction. Has `document_hash` for dedup.

- **Aliases:** "raw doc"
- **Owner doc:** [04 §10.1](04_data_schema.md), [03 §S2](03_workflow_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Dedup, Source

### Reasoning

The structured output of the analyst agent: significance, causality, durability, reversibility, precedents, one-liner.

- **Aliases:** none
- **Owner doc:** [04 §8](04_data_schema.md), [05_reasoning_framework.md](05_reasoning_framework.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Analyst, CausalLink

### Reporter

The agent that renders Signals + ThesisDeltas into user-facing reports.

- **Aliases:** "report agent"
- **Owner doc:** [02 §A7](02_agent_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Report, Template

### Reversibility

A reasoning attribute describing how easily the Signal's effect could be undone: `irreversible`, `hard`, or `easy`.

- **Aliases:** none
- **Owner doc:** [04 §8 Reasoning.reversibility](04_data_schema.md), [05 §2.4](05_reasoning_framework.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Durability, Reasoning

### RFC (Request for Comments)

A proposal document describing a planned change to the spec. Goes through `Discussion → Accepted → Spec Update → Migration → Release`.

- **Aliases:** "proposal"
- **Owner doc:** [GOVERNANCE.md §2](GOVERNANCE.md), [RFC/README.md](RFC/README.md)
- **First introduced:** SPEC_VERSION 1.3.0
- **Related:** ADR, Spec Update

---

## 6. S–Z

### Score

The five-dimension evaluation of a Signal's significance, plus its composite. Set by the `scorer` agent.

- **Aliases:** none
- **Owner doc:** [04 §7](04_data_schema.md), [06_scoring_framework.md](06_scoring_framework.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Composite Score, Magnitude, Confidence, Timeliness, Novelty, Actionability

### Signal

The atomic unit of value in the SIGNAL system: a structured, evidence-backed claim about a change to an entity.

- **Aliases:** none (avoid "alert", "notification")
- **Owner doc:** [01_signal_constitution.md](01_signal_constitution.md), [04 §4](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Evidence, Provenance, Status, Lifecycle

### Significance

A reasoning attribute (and the corresponding analyst score, [0, 1]) measuring how material the change is.

- **Aliases:** none
- **Owner doc:** [05 §2.1](05_reasoning_framework.md), [04 §8 Reasoning.significance](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Reasoning, Magnitude

### SPEC_VERSION

The global version number for the entire spec set. See [SPEC_VERSION.md](SPEC_VERSION.md).

- **Aliases:** "spec version"
- **Owner doc:** [SPEC_VERSION.md](SPEC_VERSION.md)
- **First introduced:** SPEC_VERSION 1.3.0
- **Related:** Document Version, Schema Version

### Stage

A step in a Workflow's directed graph. Stages may be Agents or Functions.

- **Aliases:** "step"
- **Owner doc:** [03 §3](03_workflow_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Workflow, Agent, Function

### Status (Signal Status)

The current lifecycle state of a Signal: `draft`, `verified`, `active`, `held`, `rejected`, `decayed`, or `superseded`.

- **Aliases:** "state" (deprecated for Signal; OK for workflow)
- **Owner doc:** [04 §4.1 Signal.status](04_data_schema.md), [01 §3](01_signal_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Lifecycle, INV-6

### Synthesizer

The agent that aggregates multiple Signals into a `ThesisDelta`.

- **Aliases:** none
- **Owner doc:** [02 §A6](02_agent_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** ThesisDelta, Cluster

### ThesisDelta

A cluster of ≥ 3 Signals on the same entity within 24h, summarized as a single thesis change.

- **Aliases:** "delta", "thesis change"
- **Owner doc:** [04 §10.2](04_data_schema.md), [03 §9 W3](03_workflow_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Cluster, Synthesis

### Tier

The watchlist level of a Company: `tier_1` (core), `tier_2` (active), `tier_3` (radar), or `tier_4` (event-driven).

- **Aliases:** "watchlist tier" (avoid just "level")
- **Owner doc:** [14 §3](14_watchlist.md), [12 §10](12_company_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Watchlist, Company

### Timeliness

One of the five Score dimensions, measuring urgency. Range [0, 1].

- **Aliases:** "urgency"
- **Owner doc:** [06 §2.3](06_scoring_framework.md), [04 §7 Score.timeliness](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Score, Horizon

### Trigger

The condition that starts a Workflow run: `scheduled`, `burst`, `manual`, or `replay`.

- **Aliases:** none
- **Owner doc:** [03 §5](03_workflow_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Workflow, Cycle

### Type (Signal Type)

The category of a Signal: `earnings`, `guidance`, `capital_action`, `management`, `operational`, `industry`, `macro`, `regulatory`, `sentiment`, or `catalyst`.

- **Aliases:** "signal type", "category"
- **Owner doc:** [10_signal_taxonomy.md](10_signal_taxonomy.md), [04 §4.1 Signal.type](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Taxonomy, Signal

### ULID

26-character Crockford base32 identifier; lexicographically sortable by creation time.

- **Aliases:** none
- **Owner doc:** [04 §3.2](04_data_schema.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** cycle_id, INV-9

### Watchlist

The curated subset of Company master entities that the pipeline actively monitors. Has tiers.

- **Aliases:** none
- **Owner doc:** [14_watchlist.md](14_watchlist.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Tier, Company

### Workflow

A directed acyclic graph of stages (agents and functions) that produces outputs from inputs. One of W1–W5.

- **Aliases:** "pipeline"
- **Owner doc:** [03 §2](03_workflow_constitution.md)
- **First introduced:** SPEC_VERSION 0.1
- **Related:** Stage, Trigger, Cycle

---

## 7. Deprecated Aliases (Do Not Use)

These names appeared in earlier drafts and are deprecated. The linter warns if they appear in spec docs.

| Deprecated | Use instead | Reason |
|---|---|---|
| `Signal.lifecycle` | `Signal.status` | "lifecycle" is the graph of valid transitions, "status" is a node in it |
| `entity_id` | `EntityRef.id` | EntityRef is the full reference |
| `clusterId` | `cluster_id` | snake_case convention |
| `cycleId` | `cycle_id` | snake_case convention; also INV-9 requires ULID format |
| `worker` | `agent` (when LLM/integration) or `function` (when deterministic) | Overloaded |
| `module` | `agent`, `function`, or `script` | Too vague |
| `service` | `component` (in [08 §2.1](08_architecture.md)) | Overloaded |
| `alert` | `Signal` | "alert" implies urgency; Signals are evidence-backed claims |
| `notification` | `Signal` or report | Notification is delivery mechanism, not content |
| `score.composite` | `composite` (in prose) or `Score.composite` (in schema) | Shorter in prose, full form in schema |
| `certainty` | `confidence` | Domain-standard term |
| `magnitude_band` | `band` | Shorter is fine |
| `change_tier` (in OverrideRecord context) | `change_tier` (correct) — was sometimes miswritten as `demote_tier` | demote is one direction; change_tier is general |

---

## 8. Adding a Term

To add a new term:

1. The term appears in **3+ documents** OR is referenced as a single concept.
2. Add an entry here with all required fields.
3. Cross-reference the owner document.
4. Run `lint_spec.py::check_glossary_consistency` — must pass.

If a term's meaning changes, do **not** redefine silently. Update the entry, bump the SPEC_VERSION MINOR, and add a deprecation note for old usage.

---

## 9. Version History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-16 | Initial glossary; ~50 terms defined |