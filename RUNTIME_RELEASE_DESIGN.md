# Runtime Release System — Design Proposal

> **Document role:** Architectural design for the boundary between the Signal Project (developed and maintained by Claude Code) and the Hermes runtime agent (an independent third-party consumer).
>
> **Key invariant:** Hermes is **not** part of the Signal Project. Hermes consumes only the **Runtime Release Package**. Hermes cannot access the development repository.
>
> Status: design proposal. No implementation, no scripts, no automation.
>
> Read alongside: [OWNERSHIP.md](OWNERSHIP.md), [SPEC_VERSION.md](SPEC_VERSION.md), [GOVERNANCE.md](GOVERNANCE.md).

---

## 1. The Three-Party Model

```
   ┌─────────────────────────┐
   │  Signal Project         │
   │  Repository             │
   │  (developed and         │
   │   maintained by         │
   │   Claude Code)          │
   │                         │
   │  - 23 spec docs         │
   │  - ADRs, RFCs           │
   │  - Audit artifacts      │
   │  - scripts/             │
   └────────────┬────────────┘
                │
                │ builds & signs
                ▼
   ┌─────────────────────────┐         ┌─────────────────────────┐
   │  Runtime Release        │         │  Hermes                 │
   │  Package                │ ──────► │  (independent runtime   │
   │  (immutable,            │ package │   AI agent)             │
   │   signed, versioned)    │         │                         │
   └─────────────────────────┘         │  - Runs methodology     │
                                       │  - Produces daily       │
                                       │    signal intelligence  │
                                       │  - Records observations │
                                       │  - Never modifies       │
                                       │    project architecture │
                                       └────────────┬────────────┘
                                                    │
                                                    │ observations
                                                    │ (telemetry only,
                                                    │  not architecture)
                                                    ▼
                                          ┌──────────────────────┐
                                          │  Hermes Observation  │
                                          │  Store               │
                                          │  (owned by Hermes)   │
                                          └──────────────────────┘
                                                    │
                                                    │ shared with
                                                    ▼
                                          ┌──────────────────────┐
                                          │  Claude Code         │
                                          │  (Signal Project     │
                                          │  maintainer)         │
                                          │                      │
                                          │  Consumes observations│
                                          │  via agreed channel  │
                                          │  to evolve spec      │
                                          └──────────────────────┘
```

| Party | Owns | Boundary |
|---|---|---|
| **Signal Project** (Claude Code) | Spec set; release process; signing keys; roadmap | Source of truth |
| **Runtime Release Package** | Immutable, versioned, signed subset of the spec | **The interface** |
| **Hermes** | Its own runtime; its own observation store; its own deployment | Independent consumer |
| **Hermes Observation Store** | Telemetry data | Owned by Hermes; shared by agreement |

**The rule**: Hermes and the Signal Project communicate only through the Runtime Release Package (downward) and Hermes's observations (upward). They share no code, no files, no direct access.

---

## 2. Design Goals

| # | Goal | Why |
|---|---|---|
| G1 | Hermes receives only the Runtime Release Package | Eliminates Hermes's ability to read governance, audit, or process docs |
| G2 | The Package is the **only** interface | No side channels, no shared repo access |
| G3 | The Package is signed by the Signal Project | Hermes can verify provenance and integrity |
| G4 | Hermes's observations flow back via an agreed channel | Closes the feedback loop without breaking independence |
| G5 | Hermes's runtime is its own concern | Signal Project does not implement or maintain Hermes |
| G6 | Architecture changes are never initiated by Hermes | Hermes consumes methodology; humans (via Claude Code) evolve architecture |

---

## 3. The Boundary Rule

> **The Runtime Release Package is the only interface between the Signal Project and Hermes.**

This rule has three implications:

1. **Hermes cannot import anything from the development repository.** No path on Hermes's side may reference any file in `c:\Users\86173\Desktop\signal\` (the repo). Hermes only knows paths inside its own installation.

2. **Claude Code never ships Hermes's code.** The Signal Project produces specs. Hermes is built by someone else (presumably the Hermes team). The two codebases do not mix.

3. **All changes flow through the Package.** When Hermes wants a feature, it submits an observation or a request via the agreed channel. Claude Code decides whether to incorporate it, then ships a new Package version.

---

## 4. What's In the Runtime Release Package

A file belongs in the Runtime Release Package **if and only if** Hermes **needs its content to execute the methodology**.

### 4.1 Runtime Knowledge (Hermes Receives)

| Source doc (in development repo) | What Hermes uses it for |
|---|---|
| [01_signal_constitution.md](01_signal_constitution.md) | What constitutes a Signal; lifecycle; cardinality |
| [02_agent_constitution.md](02_agent_constitution.md) | Eight agent contracts; cost classes; failure modes |
| [03_workflow_constitution.md](03_workflow_constitution.md) | W1–W5 workflows; stages; budgets; failure policies |
| [04_data_schema.md](04_data_schema.md) | All canonical schemas (Signal, Evidence, Provenance, Score, …) |
| [05_reasoning_framework.md](05_reasoning_framework.md) | Analyst methodology |
| [06_scoring_framework.md](06_scoring_framework.md) | Five dimensions; composite formula; gating thresholds |
| [07_prompt_guidelines.md](07_prompt_guidelines.md) | Prompt structure; model selection; test standards |
| [08_architecture.md](08_architecture.md) | Deployment topology; storage tiers; LLM Gateway contract; observability metrics |
| [10_signal_taxonomy.md](10_signal_taxonomy.md) | Ten signal types and their typical patterns |
| [11_industry_mapping.md](11_industry_mapping.md) | Industry graph structure; traversal rules; CausalLink rules |
| [12_company_schema.md](12_company_schema.md) | Company entity schema |
| [13_report_template.md](13_report_template.md) | Report templates; banned words; citation format |
| [14_watchlist.md](14_watchlist.md) | Tier definitions; pipeline behavior per tier; coverage targets |

Plus **concrete artifacts**:

| Artifact | Purpose |
|---|---|
| `prompts/<agent>/<purpose>/v<X.Y.Z>.md` | Actual prompt files (registered per [07 §9](07_prompt_guidelines.md)) |
| `config/gates.yaml` | Composite thresholds |
| `config/scoring.yaml` | Composite weights |
| `config/budgets.yaml` | Per-cycle budgets |
| `config/sources.yaml` | Source registry |
| `config/models.yaml` | Model versions per task |
| `data/watchlist.yaml` | Current watchlist snapshot |
| `data/companies.yaml` | Company master snapshot |
| `data/industry-chains/*.yaml` | Industry chain graphs |
| `MANIFEST.yaml` | Package metadata + integrity signature |

**Total: 13 spec docs + ~10 concrete artifacts.**

### 4.2 What's NOT in the Package

These stay in the development repository. **Hermes never sees them.**

| Document | Why excluded |
|---|---|
| [00_project_context.md](00_project_context.md) | Charter for humans; Hermes doesn't need the mission statement at runtime |
| [09_development_roadmap.md](09_development_roadmap.md) | Implementation phases; Hermes doesn't need to know what's planned |
| [INVARIANTS.md](INVARIANTS.md) | Invariants are enforced by the runtime; the catalog is for humans |
| [SPEC_VERSION.md](SPEC_VERSION.md) | Versioning policy is a release-time concern, not a runtime concern |
| [GOVERNANCE.md](GOVERNANCE.md) | Process docs (RFC, ADR, Release Checklist) are human workflows |
| [GLOSSARY.md](GLOSSARY.md) | Term definitions; Hermes has its own internal model |
| [SCHEMA_EVOLUTION.md](SCHEMA_EVOLUTION.md) | Schema bump rules apply during release, not at runtime |
| [REVIEW_NOTES.md](REVIEW_NOTES.md) | Consistency audit log |
| [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) | Mission-alignment audit |
| [OWNERSHIP.md](OWNERSHIP.md) | Component ownership matrix |
| `ADR/` | Historical decisions; Hermes runs on the decisions, doesn't read them |
| `RFC/` | Active proposals; not yet adopted |
| `scripts/` | Spec-maintenance tooling |
| `release/` (other versions) | Older releases; Hermes uses only its current version |

### 4.3 The Invariant Edge Case

The 12 invariants in [INVARIANTS.md](INVARIANTS.md)) are a catalog of *rules that cannot be violated*. They are NOT runtime input.

The enforcement happens through:
- Agent postconditions (defined in [02](02_agent_constitution.md))
- Schema validators (defined in [04](04_data_schema.md))
- Lifecycle transition rules (defined in [01 §3](01_signal_constitution.md))

Hermes implements these enforcement points because they're described in the runtime docs. The catalog in INVARIANTS.md is for **the Signal Project maintainer** (Claude Code) to track what's enforced where. Hermes doesn't need to know the catalog exists.

If a future invariant cannot be expressed in a runtime doc (e.g., a policy that requires out-of-band checks), it would be added to the Package. Today, all 12 invariants map to existing runtime specs.

---

## 5. Release Package Structure

```
release/
└── hermes-runtime-v1.3.0/
    ├── MANIFEST.yaml
    ├── knowledge/
    │   ├── 01-signal-constitution.md
    │   ├── 02-agent-constitution.md
    │   ├── 03-workflow-constitution.md
    │   ├── 04-data-schema.md
    │   ├── 05-reasoning-framework.md
    │   ├── 06-scoring-framework.md
    │   ├── 07-prompt-guidelines.md
    │   ├── 08-architecture.md
    │   ├── 10-signal-taxonomy.md
    │   ├── 11-industry-mapping.md
    │   ├── 12-company-schema.md
    │   ├── 13-report-template.md
    │   └── 14-watchlist.md
    ├── prompts/
    │   ├── detector/
    │   │   └── extract_signals/v1.4.2.md
    │   ├── verifier/...
    │   ├── analyst/...
    │   ├── scorer/
    │   │   └── score_dimensions/v1.2.0.md
    │   ├── synthesizer/...
    │   └── reporter/...
    ├── config/
    │   ├── gates.yaml
    │   ├── scoring.yaml
    │   ├── budgets.yaml
    │   ├── sources.yaml
    │   └── models.yaml
    └── data/
        ├── watchlist.yaml
        ├── companies.yaml
        └── industry-chains/
            ├── semiconductors.yaml
            └── ...
```

### 5.1 MANIFEST.yaml

Hermes reads `MANIFEST.yaml` first. It must verify the package before loading anything else.

```yaml
package:
  name: hermes-runtime
  version: 1.3.0
  built_at: 2026-07-17T00:00:00Z
  built_by: signal-project
  publisher: claude-code
  source_commit: <git-sha>
  hermes_min_version: 1.3.0
  hermes_max_version: 1.3.x

contents:
  knowledge_docs:
    - path: knowledge/01-signal-constitution.md
      spec_doc: 01_signal_constitution.md
      version: 0.2
    # ... one entry per doc
  prompts:
    - path: prompts/detector/extract_signals/v1.4.2.md
      agent: detector
      purpose: extract_signals
      version: 1.4.2
    # ... one entry per prompt
  config_files:
    - path: config/gates.yaml
    # ...
  data_snapshots:
    - path: data/watchlist.yaml
      as_of: 2026-07-17T00:00:00Z
      record_count: 78
    # ...

content_hashes:
  # sha256 of every file in the package

integrity:
  signature_algorithm: ed25519
  signature: <signature of canonical manifest bytes>
  publisher_public_key_id: signal-project-2026
```

Hermes verifies:

1. Its own version is in `hermes_min_version ... hermes_max_version`.
2. Every `content_hashes` entry matches the file on disk.
3. `integrity.signature` validates against the embedded `publisher_public_key_id`.
4. Every `path` referenced in contents exists in the package.

If any check fails, **Hermes refuses to load** and logs the failure to its own observation store. It does not fall back to a partial load.

### 5.2 What Hermes Must NOT Do With the Package

Per the boundary rule, Hermes's obligations include:

| Rule | Why |
|---|---|
| Hermes reads the Package; it does not modify any file in it | The Package is immutable |
| Hermes does not request files outside the Package | The Package is complete |
| Hermes does not contact the development repository | No side channel |
| Hermes does not request git history or earlier Package versions from the Signal Project | Hermes is responsible for retaining its own Package archive |
| Hermes does not parse the MANIFEST's `source_commit` to look up other content | The Package is self-contained |
| Hermes does not attempt to import or reference any doc by its `spec_doc` name (e.g., `INVARIANTS.md`) | Names outside the Package are not part of the interface |

If Hermes needs something not in the Package, it must:
1. Document the gap in its observation store.
2. Notify the Signal Project maintainer (Claude Code) via the agreed observation channel.
3. Wait for a new Package version.

Hermes **does not** unilaterally extend the spec.

---

## 6. Release Workflow

```
   Signal Project           Runtime                Hermes              Observation
   (Repository)             Release                (Independent)        Store
        │                   Package                    │                   │
        │                                            │                   │
        │ 1. Build & sign                            │                   │
        ├───────────────────►                         │                   │
        │                                            │                   │
        │ 2. Ship                                    │                   │
        ├───────────────────────────────────────────►│                   │
        │                                            │                   │
        │                                            │ 3. Verify & load │
        │                                            │                   │
        │                                            │ 4. Run methodology
        │                                            │                   │
        │                                            │ 5. Produce Signal│
        │                                            │    intelligence  │
        │                                            │                   │
        │                                            │ 6. Record        │
        │                                            ├──────────────────►│
        │                                            │                   │
        │ 7. Ingest observations                     │                   │
        │◄───────────────────────────────────────────┴───────────────────┘
        │
        │ 8. Evolve spec
        │
   back to 1
```

### 6.1 Step 1 — Build & Sign

Claude Code decides the Signal Project has reached a releasable state (corresponding to a SPEC_VERSION bump per [SPEC_VERSION §3](SPEC_VERSION.md)).

The build operation:
1. Read the 13 runtime docs from the repo.
2. Inline references to development-only docs (so the Package is self-contained).
3. Read concrete artifacts: prompts, config, data snapshots.
4. Compute `MANIFEST.yaml` with content hashes.
5. Sign with the Signal Project's publisher key.
6. Place everything under `release/hermes-runtime-v<X.Y.Z>/`.

This step is manual or assisted; the design does not specify tooling.

### 6.2 Step 2 — Ship

The signed Package is delivered to Hermes. The delivery mechanism is out of scope (could be object storage, signed URL, file mount). The contract: Hermes receives a directory matching §5.

Hermes does **not** download from the development repository. It loads what it's given. Claude Code does not "push" to Hermes automatically; an Operator (or Hermes itself, if authorized) initiates the load.

### 6.3 Step 3 — Verify & Load

Hermes:
1. Reads `MANIFEST.yaml`.
2. Verifies integrity per §5.1.
3. Loads knowledge docs, prompts, config, data snapshots.
4. Records the loaded version in its own state.

If verification fails, Hermes logs the failure to its observation store and refuses to start a methodology cycle.

### 6.4 Step 4 — Run Methodology

Hermes executes the workflow defined in [03](03_workflow_constitution.md) using the schemas in [04](04_data_schema.md), the taxonomy in [10](10_signal_taxonomy.md), the prompts in `prompts/`, etc. Hermes implements the eight agents per [02](02_agent_constitution.md); this implementation is Hermes's own.

### 6.5 Step 5 — Produce Signal Intelligence

Hermes emits Signals, ThesisDeltas, and reports per [13](13_report_template.md). These are Hermes's **deliverable** — they go to whatever end-user Hermes serves, **not to Claude Code**.

### 6.6 Step 6 — Record Observations

Hermes records runtime observations in **its own observation store**:

| Observation | Format |
|---|---|
| CycleReport | Per [04 §10.5](04_data_schema.md) |
| FailureEvent | Per [04 §10.4](04_data_schema.md) |
| Calibration data | Per [05 §3.2](05_reasoning_framework.md), [06 §6](06_scoring_framework.md) |
| Coverage gaps | Hermes-defined format |
| Drift alerts | Per [06 §6.1](06_scoring_framework.md) |

Observations do **not** include:
- Signal content (Hermes's deliverable; not for the maintainer)
- Company master deltas (Hermes's runtime state)
- Curator override records (Hermes may have a curator equivalent; it's Hermes's)

Observations include:
- Aggregate operational metrics (latency, cost, error rates)
- Calibration outcomes (did high-confidence Signals get corroborated?)
- Coverage gaps (which watchlist entities got no Signals?)
- Spec ambiguities discovered at runtime (e.g., "the detector prompt is unclear about X")

### 6.7 Step 7 — Ingest Observations

Claude Code receives Hermes's observations via the agreed channel (out of scope of this proposal). Observations are stored in the development repo's observation tracking (not as repo files, but as maintainer-side data) and inform the next spec evolution.

Hermes's observations **never** directly modify any file in the Signal Project repository. They are input to human review, not automated commits.

### 6.8 Step 8 — Evolve Spec

Claude Code (or another human) reviews observations and decides what to change:
1. **Issue identified** (e.g., calibration drift, new signal type emerging, schema gap).
2. **RFC proposed** per [GOVERNANCE.md §2](GOVERNANCE.md).
3. **RFC accepted.**
4. **Spec updated** in affected docs.
5. **ADR written** per [GOVERNANCE.md §3](GOVERNANCE.md).
6. **New release cut** (back to Step 1).

---

## 7. Hermes Obligations Summary

Hermes, as the receiver of the Runtime Release Package, is bound by:

1. **Use the Package as the only interface.** Do not contact the Signal Project repository.
2. **Treat the Package as immutable.** Do not modify files in the Package.
3. **Verify integrity on load.** Use `MANIFEST.yaml` to confirm provenance.
4. **Respect version constraints.** Refuse packages outside `hermes_min_version` / `hermes_max_version`.
5. **Never modify project architecture.** Architectural changes are initiated only by the Signal Project maintainer (Claude Code).
6. **Record observations to your own store.** Do not write back into the Signal Project repo.
7. **Submit feature requests via the observation channel.** Not by extending the Package.
8. **Retain your own Package archive.** Hermes is responsible for storing older Package versions if it wants to roll back.
9. **Treat `spec_doc` names as opaque.** The names in `MANIFEST.yaml` are for traceability; Hermes should not interpret them as paths into the development repo.
10. **Never claim ownership of the methodology.** The methodology is owned by the Signal Project. Hermes runs it on behalf of someone.

Hermes's role is to **run the methodology, produce signal intelligence, record observations**. Nothing else.

---

## 8. Signal Project (Claude Code) Obligations

In turn, the Signal Project maintainer (Claude Code) is bound by:

1. **Produce Packages that are self-contained.** No references outside the Package should require resolution.
2. **Sign every Package.** Hermes must be able to verify provenance.
3. **Honor the version compatibility window.** Per [SPEC_VERSION §5](SPEC_VERSION.md), old packages must remain loadable for the declared window.
4. **Never read into Hermes's runtime.** The Signal Project does not have visibility into how Hermes implements its runtime; the maintainer knows only what the Package contains and what Hermes observes.
5. **Treat Hermes's observations as input, not commands.** The maintainer decides what to incorporate; Hermes cannot dictate changes.
6. **Maintain the boundary.** If a contributor accidentally adds a Hermes-specific concern to a runtime doc, that should be reverted.
7. **Document Hermes's expected behavior.** This proposal and similar artifacts describe what Hermes is allowed to do.

---

## 9. What the Signal Project Maintainer Receives From Hermes

The maintainer does **not** receive:
- Hermes's Signal content (it's Hermes's deliverable).
- Hermes's end-user data (PII, proprietary research views).
- Hermes's internal implementation details.

The maintainer does receive:
- Operational metrics (latency, cost, error rates).
- Calibration data (Signal outcomes measured against reality).
- Coverage gaps (entities lacking Signals).
- Spec ambiguities (places where the docs were unclear).
- Drift alerts (per [06 §6.1](06_scoring_framework.md)).

This input flows back into the spec evolution loop (Step 8 of §6).

---

## 10. Versioning

Per [SPEC_VERSION.md](SPEC_VERSION.md), every release is identified by SPEC_VERSION. Hermes corresponds:

| Hermes version | Compatible Package versions |
|---|---|
| 1.3.0 | 1.3.x (exact + within MINOR window) |
| 1.2.x | 1.2.x and 1.3.0 (forward-compatible) |
| 1.4.0 | Refuses 1.3.x (forward-incompatible) |

The compatibility matrix is declared in `MANIFEST.yaml` per release. Hermes refuses to load a package outside its supported range.

Per [SPEC_VERSION §5.1](SPEC_VERSION.md), old Package versions remain loadable for:
- 90 days after a schema MAJOR bump
- 180 days after a SPEC_VERSION MAJOR bump

Hermes is responsible for retaining older packages if it wants to roll back. The Signal Project retains older packages in `release/` for archival; Hermes should not expect to retrieve them on demand.

---

## 11. Cadence

The Package cadence is **event-driven**, not periodic. A new Package is cut when:

| Trigger | Bump type |
|---|---|
| New schema field required | MINOR |
| New signal type added | MINOR |
| Bug fix in spec | PATCH |
| Invariant change | MAJOR |
| Breaking schema change | MAJOR |
| New agent added | MINOR |

Hermes upgrade cadence is independent. Hermes can:
- Hold on Package N for as long as it wants.
- Skip to Package N+k if compatible.
- Roll back within the compatibility window.

The cadence is the maintainer's choice; it is not a release schedule.

---

## 12. What This Proposal Does NOT Cover

To be explicit about boundaries:

- **No Hermes implementation.** Hermes is independent; the Signal Project does not build it.
- **No Package build tooling.** How the Package is constructed (script, manual, CI) is unspecified.
- **No delivery mechanism.** Whether the Package arrives via object storage, signed URL, or file mount is out of scope.
- **No observation channel implementation.** How Hermes sends observations to Claude Code (webhook, scheduled export, API) is out of scope.
- **No key management.** Who holds the publisher key, how it's rotated, where Hermes gets the public key — all out of scope, but flagged as design questions (§13).
- **No multi-tenancy.** Each Hermes installation uses one Package at a time. Hermes-as-a-service with multiple tenants is out of scope.
- **No version of Hermes itself.** Hermes has its own version; how that corresponds to Package versions is the `hermes_min_version` / `hermes_max_version` field in MANIFEST.

---

## 13. Open Design Questions

These are flagged for the team's review before implementation:

| # | Question | Trade-off |
|---|---|---|
| DQ-1 | What is the **publisher key management** story? | Who holds the Signal Project signing key? How is rotation handled? How does Hermes obtain the public key initially? |
| DQ-2 | What is the **observation channel** between Hermes and Claude Code? | Webhook? Email? Shared file drop? Scheduled query? |
| DQ-3 | Should Hermes's observations be **encrypted in transit**? | Yes, for any production deployment; how is a separate question. |
| DQ-4 | Should the Package be **encrypted at rest** in Hermes's storage? | Protects against disk theft; requires KMS. |
| DQ-5 | What happens if Hermes wants a **schema field that's missing**? | It submits an observation; the maintainer decides. Hermes waits for the next Package. |
| DQ-6 | What happens if **Hermes finds a bug in the Package**? | Bug-fix PATCH release; Hermes upgrades. |
| DQ-7 | Can **multiple Hermes instances** share a Package? | Yes, the Package is identical across all consumers. But Hermes's runtime state (watchlist updates, observation store) is per-instance. |
| DQ-8 | Does Hermes ever need to **revert to an older Package** mid-stream? | Yes; the Signal Project retains older packages for 90/180 days. |
| DQ-9 | What if Hermes's load fails because of a known issue, but it must produce output? | Hermes logs the failure; doesn't run a partial methodology. This is the safest default. |

---

## 14. Summary

| Aspect | Decision |
|---|---|
| Three parties | Signal Project (Claude Code) — Package — Hermes (independent) |
| The interface | Runtime Release Package (immutable, signed, versioned) |
| What's in the Package | 13 runtime docs + 10 concrete artifacts + MANIFEST |
| What's NOT in the Package | Charter, roadmap, governance, ADRs, RFCs, scripts, audits |
| Communication | Downward: Package. Upward: observations. Nothing else. |
| Hermes obligations | 10 rules in §7 |
| Signal Project obligations | 7 rules in §8 |
| Versioning | Hermetic; corresponds to SPEC_VERSION |
| Cadence | Event-driven |
| Edges | INVARIANTS is enforcement catalog (not runtime); spec_doc names are opaque to Hermes |
| What's NOT here | Hermes implementation; Package build tooling; delivery mechanism; observation channel; key management |

**The boundary is the Package.** Hermes is an independent consumer. Claude Code is the maintainer. They share nothing except the signed Package and Hermes's observation stream.

---

## 15. Version History

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-17 | Initial runtime release system design (corrected: Hermes is independent of the Signal Project) |