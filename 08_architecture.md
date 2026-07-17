# 08 · System Architecture

> **Document role:** Technical architecture — concrete components, deployment topology, scaling, security, observability. Translates the conceptual pipeline in [00](00_project_context.md) and [03](03_workflow_constitution.md) into running systems.
>
> Requires: `00_project_context.md ≥ 0.2`, `02_agent_constitution.md ≥ 0.1`, `03_workflow_constitution.md ≥ 0.1`, `04_data_schema.md ≥ 1.0`.

---

## 1. Architecture Goals

| Goal | Target |
|---|---|
| Throughput | Sustain ≥ 500 raw docs/min during burst |
| Latency | Cycle wall time ≤ 60 min (target: 30 min) |
| Reproducibility | Every Signal regeneratable from provenance inputs |
| Cost | ≤ $0.30 per active Signal emitted (LLM + storage) |
| Uptime | ≥ 99.5% during market hours |
| Auditability | Every Signal fully traceable from claim → source → agent chain |

---

## 2. High-Level Topology

```
                       ┌──────────────────────┐
                       │   Operator / Curator  │
                       └───────────┬──────────┘
                                   │ HTTPS
                                   ▼
                       ┌──────────────────────┐
                       │   API Gateway        │
                       │  (auth, rate limit)  │
                       └─────┬──────────┬─────┘
                             │          │
                  ┌──────────▼───┐   ┌──▼──────────┐
                  │ Control Plane│   │ Read API    │
                  │ (write ops)  │   │ (queries)   │
                  └──────┬───────┘   └──┬──────────┘
                         │              │
              ┌──────────┴──────────────┴──────────────┐
              │                                        │
              ▼                                        ▼
   ┌────────────────────┐                  ┌────────────────────┐
   │  Pipeline Runner   │                  │   Query Service    │
   │  (W1–W5)           │                  │  (reports, UI)     │
   └─────────┬──────────┘                  └─────────┬──────────┘
             │                                       │
   ┌─────────┴──────────┐                            │
   ▼                    ▼                            │
┌─────────┐    ┌────────────────┐                   │
│  Hot    │    │   LLM Gateway  │                   │
│ Stores  │    │  (claude API)  │                   │
└─────────┘    └────────────────┘                   │
                                                    ▼
                                          ┌────────────────┐
                                          │ Warm/Cold Store │
                                          └────────────────┘
```

> Workflow inventory: W1 `ingest_cycle`, W2 `burst_cycle`, W3 `synthesis_cycle`, W4 `report_cycle`, W5 `replay_cycle`. See [03 §2](03_workflow_constitution.md) for the canonical list.

### 2.1 Component Responsibilities

| Component | Responsibility |
|---|---|
| **API Gateway** | Auth, rate limit, request routing |
| **Control Plane** | Workflow triggers, agent registry, prompt registry, override API |
| **Read API** | Query Signals, reports, watchlist (read-only) |
| **Pipeline Runner** | Executes W1–W5 workflows |
| **Hot Stores** | In-memory + Redis for active artifacts |
| **Warm/Cold Stores** | PostgreSQL + object storage for durable artifacts |
| **LLM Gateway** | Mediates all LLM calls; rate limits; cost tracking |
| **Query Service** | Composes responses for UI/reports |

---

## 3. Data Storage

### 3.1 Hot Tier (sub-second access)

| Store | Contents | Tech |
|---|---|---|
| `signal_cache` | Active Signals (last 7 days) | Redis |
| `watchlist_cache` | Current watchlist state | Redis |
| `cycle_state` | In-flight cycle state | Redis |
| `dedup_index` | MinHash signatures, last 7d | Redis Bloom filter + sets |

### 3.2 Warm Tier (< 1s access)

| Store | Contents | Tech |
|---|---|---|
| `signal_db` | All Signals, indexed by entity/type/date | PostgreSQL |
| `company_db` | Company master | PostgreSQL |
| `industry_db` | Industry chain graph | PostgreSQL (with graph extension) |
| `override_log` | All curator overrides | PostgreSQL |

### 3.3 Cold Tier (audit-only)

| Store | Contents | Tech |
|---|---|---|
| `raw_archive` | All RawDocuments, immutable | S3-compatible object store |
| `report_archive` | Generated reports | Object store |
| `prompt_archive` | All historical prompt versions | Git (immutable history) |
| `audit_log` | Append-only event log | Append-only DB or object store |

### 3.4 Schema Mapping

Each store uses the schemas defined in [04_data_schema.md](04_data_schema.md). PostgreSQL tables have JSONB columns for flexibility + GIN indexes on common query paths.

---

## 4. The Pipeline Runner

### 4.1 Runtime Model

A long-running process per workflow. Cycle triggered by:
- Cron (scheduled)
- Event (burst)
- API call (manual/replay)

### 4.2 Concurrency Model

```yaml
ingest_cycle:
  stage_parallelism:
    S1_harvest: 8 workers, per-source
    S2_normalize: 4 workers
    S3_dedup: 2 workers (CPU-bound)
    S4_detect: 16 workers, per-document
    S5_verify: 16 workers, per-signal
    S6_reason: 8 workers, per-signal (token-heavy)
    S7_score: 16 workers, per-signal
    S8_gate: 4 workers
    S9_persist: 4 workers (I/O bound)
  total_max_workers: 80
```

### 4.3 Implementation Targets

| Choice | Default | Alternative |
|---|---|---|
| Language | Python 3.12 | n/a (project standard) |
| Async runtime | asyncio | Celery for simpler deployments |
| LLM SDK | anthropic-sdk-python | LiteLLM for multi-provider |
| DB driver | asyncpg | psycopg (sync) |
| Object store | S3 | GCS, Azure Blob |
| Scheduler | cron + Redis ZSET | Temporal.io for complex orchestration |

### 4.4 Failure Isolation

Each stage runs in a sandboxed worker. A worker crash does **not** affect other workers. State is checkpointed after each stage ([03 §6.4](03_workflow_constitution.md)).

---

## 5. The LLM Gateway

### 5.1 Why a Gateway

Centralizing all LLM calls behind a single service enables:
- Cost tracking per agent per cycle
- Rate limiting per provider
- Fallback to alternative providers
- Caching of identical requests (within a cycle)
- Audit log of every call

### 5.2 Gateway Contract

```python
class LLMGateway(Protocol):
    async def complete(
        self,
        *,
        prompt_id: str,
        prompt_version: str,
        model_id: str,
        inputs: dict,
        temperature: float = 0.0,
        max_tokens: int,
        cache_key: Optional[str] = None,
        trace_id: str,
    ) -> LLMResponse
```

`LLMResponse` includes:
- `output_text` — the model's text output
- `input_tokens`, `output_tokens`
- `cost_usd`
- `latency_ms`
- `model_id_used` (may differ from request if fallback)
- `cache_hit` (bool)

### 5.3 Cost Tracking

Every call's cost is recorded in `CycleReport.llm_cost_actual`. Per-Signal cost is computed by apportioning cycle LLM cost by token count.

Cost budget enforcement:
- Per-cycle budget ([03 §7](03_workflow_constitution.md))
- Per-day budget (config)
- Per-agent budget (config)

When a budget is hit, the cycle enters **degrade mode** ([03 §6.3](03_workflow_constitution.md)).

### 5.4 Caching

Within a single cycle, identical `(prompt_id, prompt_version, model_id, inputs_hash)` requests return the cached response. This prevents redundant calls when the same document is processed by multiple agents.

Cross-cycle caching is opt-in and time-bounded (≤ 6h, since model outputs may be desired fresh).

---

## 6. Security

### 6.1 Threat Model

| Threat | Mitigation |
|---|---|
| Unauthorized API access | OAuth + RBAC at gateway |
| Prompt injection via source documents | Source content treated as **untrusted data**; structured fields extracted into a separate channel; never interpolated into instructions |
| Source poisoning | Verifier checks source reachability; curator can disable sources |
| LLM provider compromise | Pin model versions in provenance; replay detects divergence |
| Data exfiltration via LLM calls | Strip PII before LLM input; audit log every prompt sent |
| Insider threat (curator) | All overrides are append-only and audit-logged; sensitive actions require dual approval |

### 6.2 Prompt Injection Defense

The single most important security control. Rules:

1. Raw source content is **data**, not instructions
2. Structured fields (claim, entity_ref, evidence) are extracted via schema-constrained output
3. The detector prompt **never** sees raw source content directly — only structured fields after extraction
4. JSON-mode / structured-output is enforced at the LLM API
5. Output is validated against schema **before** any downstream use

### 6.3 Data Classification

| Class | Examples | Handling |
|---|---|---|
| Public | News, SEC filings, press releases | No restrictions |
| Internal | Signal scores, curator overrides | Role-restricted |
| Sensitive | Audit logs, replay inputs | Encryption at rest, audit-logged access |

PII (names of individuals, emails, etc.) is **never** stored in Signals. The detector prompt explicitly forbids emitting PII.

---

## 7. Observability

### 7.1 Three Pillars

| Pillar | Tooling | Use |
|---|---|---|
| **Logs** | Structured JSON to object store | Per-event debugging |
| **Metrics** | Prometheus + Grafana | Dashboards, alerts |
| **Traces** | OpenTelemetry | Cross-stage latency, cycle flow |

### 7.2 Key Metrics

| Metric | Source | Alert threshold |
|---|---|---|
| Cycle success rate | CycleReport | < 95% daily |
| Cycle wall time | CycleReport | p95 > 60 min |
| LLM cost per Signal | LLMGateway | > $0.50 over 1h window |
| Source error rate | SourceHealth | > 10% per source per hour |
| Active Signal rate | SignalStore | < 50% of historical baseline |
| Calibration (rolling) | decay_worker | < 60% corroboration rate |

### 7.3 Tracing

Every cycle emits a trace span tree:
```
cycle_root
├── harvest
│   ├── source: sec_edgar
│   ├── source: reuters
│   └── ...
├── detect
│   ├── doc_1234 (15s, 8k tokens in)
│   └── doc_1235 (...)
├── verify
│   └── ...
└── score
    └── ...
```

### 7.4 Alerting

| Severity | Trigger | Channel |
|---|---|---|
| Page | Pipeline down, calibration collapse, security event | PagerDuty / phone |
| Slack | Budget overrun, source degradation | Slack channel |
| Log | Any FailureEvent | Centralized log |

---

## 8. Deployment

### 8.1 Reference Deployment (Small, ≤ 200 entities)

```
1× Pipeline Runner (4 vCPU, 16 GB RAM)
1× PostgreSQL (small instance)
1× Redis (small instance)
1× Object store (S3 / MinIO)
1× LLM Gateway (proxy to Anthropic API)
```

Total cloud cost target: ≤ $500/month excluding LLM costs.

### 8.2 Production Deployment (200–2000 entities)

```
3× Pipeline Runner (8 vCPU, 32 GB RAM) — HA
PostgreSQL — primary + 2 replicas
Redis — primary + replica
Object store — S3
LLM Gateway — multi-region
Prometheus + Grafana
OpenTelemetry collector
```

### 8.3 Deployment Method

- **IaC**: Terraform or Pulumi
- **Containers**: Docker images for each service
- **Orchestration**: Kubernetes (EKS / GKE) or simpler VM-based for small deployment
- **CI/CD**: GitHub Actions, with prompt/schema change tests as gates

---

## 9. Disaster Recovery

| Scenario | RTO | RPO | Strategy |
|---|---|---|---|
| Pipeline crash | < 5 min | 0 | Auto-restart from last checkpoint |
| Database corruption | < 1 hour | < 1 hour | WAL + daily snapshot |
| Object store loss | < 24 hours | < 24 hours | Cross-region replication |
| LLM provider outage | < 30 min | 0 | Degrade mode ([03 §6.3](03_workflow_constitution.md)) |
| Total region loss | < 4 hours | < 1 hour | Multi-region active-passive |

---

## 10. Cost Model

### 10.1 Per-Signal Cost Breakdown (target)

| Component | Cost |
|---|---|
| Harvest | $0.00 (HTTP fetch) |
| Detect (LLM) | $0.10 |
| Verify (LLM + HTTP) | $0.02 |
| Reason (LLM) | $0.12 |
| Score (LLM + math) | $0.01 |
| Synthesize (LLM) | $0.03 (amortized) |
| Persist | $0.002 |
| **Total** | **$0.262** |

### 10.2 Optimization Levers

In order of effort-to-impact:

1. **Detector prompt tuning** — biggest LLM cost, easiest wins
2. **Caching** — second-pass detection often reuses prior calls
3. **Model tiering** — use Haiku where Opus adds no measurable quality
4. **Skip-LLM rules** — boilerplate detection without LLM
5. **Batching** — group multiple entities into one LLM call where possible

---

## 11. Scaling Strategies

| Dimension | Strategy | Trigger |
|---|---|---|
| **Vertical** | Bigger runners | Up to ~16 vCPU per runner |
| **Horizontal** | More runners | Cycle time > 30 min for 3 days |
| **Sharding** | Per-entity-shard runners | Watchlist > 1000 entities |
| **Multi-region** | Active-passive | Global coverage requirement |
| **LLM-side** | Higher rate limits, fallback providers | Provider rate-limit hits |

---

## 12. Open Architectural Questions

These are tracked but **not** resolved in v1.x:

| Question | Status | Resolution path |
|---|---|---|
| Real-time push (sub-minute latency)? | Open | RFC in v2.0 |
| Streaming outputs to UI? | Open | After UI v1 ships |
| Cross-portfolio contagion detection? | Open | v1.9 ([00 §10.3](00_project_context.md)) |
| Federated deployment across firms? | Open | v2.x, requires multi-tenancy spec |
| Embedding-based novelty (vs minhash)? | Open | v1.4 ([00 §10.1](00_project_context.md)) |

---

## 13. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-07-16 | Initial scaffold |

Topology changes (§2), storage tier changes (§3), or security model changes (§6) are MAJOR. New observability metrics (§7.2) are MINOR. Wording fixes are PATCH.