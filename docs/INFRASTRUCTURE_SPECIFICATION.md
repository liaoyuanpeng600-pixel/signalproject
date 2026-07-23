# Infrastructure Specification

> **Document role:** Defines the long-running runtime infrastructure for Hermes — the autonomous Research Operating System that consumes the SIGNAL Runtime Release Package. Establishes topology, job lifecycle, scheduled jobs, runtime states, notification pipeline (transport-agnostic), command readiness, failure handling, logging, and deployment assumptions.
>
> **Status:** Design specification. No implementation in this checkpoint.
>
> **Scope boundary:** This document describes **Hermes infrastructure**, not the SIGNAL project itself. SIGNAL emits the Runtime Release Package; Hermes is the consumer that runs it 24/7. Nothing in this spec requires changes to the SIGNAL repository.
>
> Requires: `RUNTIME_RELEASE_DESIGN.md` (three-party model), `00_ARCHITECTURE_PRINCIPLES.md`, `03_RUNTIME_MODEL.md`.

---

## Document Metadata

| Field | Value |
|---|---|
| **Status** | Frozen |
| **Version** | 1.0 |
| **Effective Date** | 2026-07-21 |
| **Next Review** | TBD |
| **Owner** | Hermes Architecture |

---

## 1. Runtime Topology

Hermes runs as a single-node service composed of five cooperating components. Each component has a single responsibility and communicates through well-defined interfaces. No component embeds knowledge of another's internal implementation.

### 1.1 Architecture Diagram

```
                ┌──────────────────────────────────┐
                │   Scheduler                       │
                │   (cron + event-driven triggers)  │
                └──────────────┬───────────────────┘
                               │ enqueues Jobs
                               ▼
┌─────────────────────────────────────────────────────┐
│                       Queue                         │
│   bounded, persistent (post-MVP), priority-ordered  │
└──────────────────────────┬──────────────────────────┘
                           │ dequeue
                           ▼
┌─────────────────────────────────────────────────────┐
│                       Worker                        │
│   owns one Job at a time; coordinates the cycle     │
└────┬───────────────┬─────────────────┬───────────────┘
     │               │                 │
     │ invokes       │ invokes         │ invokes
     ▼               ▼                 ▼
┌──────────┐  ┌────────────────┐  ┌────────────────┐
│ Report   │  │ Persistence    │  │ Research       │
│ Generator│  │ Interface      │  │ Subsystem      │
│          │  │ (Store)        │  │ (calibration,  │
│          │  │                │  │ conflicts)     │
└────┬─────┘  └────────┬───────┘  └────────┬───────┘
     │                 │                   │
     │                 │                   │
     └────────────────┴───────────────────┘
                       │
                       │ emits Reports
                       ▼
                ┌──────────────────────┐
                │ Notification          │
                │ Dispatcher            │
                │ (transport-agnostic)  │
                └──────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   Telegram         WeChat        Email / Webhook / Discord
```

### 1.2 Component Responsibilities

| Component | Responsibility | MUST NOT |
|---|---|---|
| **Scheduler** | Decide WHEN a job runs (cron schedules, burst events, manual triggers). Produce Job descriptors. | Know what the job does; know about Report content; know about Notification targets. |
| **Queue** | Hold pending Jobs in priority order with bounded capacity. Persist across restarts (post-MVP). | Schedule jobs; execute jobs; modify job contents. |
| **Worker** | Pull one Job at a time from the Queue; orchestrate the cycle; invoke Report Generator, Persistence, Research subsystems. | Know about Notification transports; embed Report rendering policy; bypass Scheduler. |
| **Report Generator** | Compose and render Reports per the SIGNAL Report Specification. | Schedule reports; push to Notifications directly. |
| **Notification Dispatcher** | Deliver composed Reports to one or more transport adapters. | Compose Reports; perform retries with its own policy (delegated to Scheduler/Worker retry). |

### 1.3 Topology Invariants

1. All component-to-component communication is via the documented interfaces (no shared mutable state, no direct DB access from the Notification Dispatcher).
2. The Scheduler is the only producer of Jobs. Manual triggers go through the Scheduler.
3. The Worker is the only consumer of Jobs.
4. The Report Generator and Persistence Interface are siblings under the Worker, not sequential. Each may be invoked independently when the Worker's orchestration logic requires.

---

## 2. Job Lifecycle

Every Job passes through a finite set of states. State transitions are explicit and recorded in the runtime log.

### 2.1 Lifecycle Diagram

```
                   ┌─────────┐
       enqueue     │         │   dequeue
   ─────────────►  │ QUEUED  │  ─────────────►
                   │         │                │
                   └────┬────┘                ▼
                        │                ┌─────────┐
                        │  cancel        │         │
                        └────────────►   │ RUNNING │
                                         │         │
                                         └────┬────┘
                                              │
                          ┌───────────────────┼───────────────────┐
                          │                   │                   │
                          ▼                   ▼                   ▼
                    ┌──────────┐       ┌──────────┐         ┌──────────┐
                    │SUCCEEDED │       │  FAILED  │         │CANCELLED │
                    │ terminal │       │          │         │ terminal │
                    └──────────┘       └────┬─────┘         └──────────┘
                                             │
                                             │ retry-policy says retry
                                             ▼
                                        ┌─────────┐
                                        │  RETRY  │
                                        └────┬────┘
                                             │ re-enqueue
                                             ▼
                                        ┌─────────┐
                                        │ QUEUED  │
                                        └─────────┘
```

### 2.2 State Definitions

| State | Description | Transitions Allowed |
|---|---|---|
| **QUEUED** | Job is in the Queue, awaiting a Worker. | → RUNNING (dequeue), → CANCELLED (operator) |
| **RUNNING** | A Worker has claimed the Job and is executing. | → SUCCEEDED, → FAILED, → CANCELLED (operator) |
| **SUCCEEDED** | Job completed without error. Report (if any) emitted. **Terminal.** | — |
| **FAILED** | Job completed with an error. May be retried per policy. | → RETRY, → CANCELLED (operator) |
| **CANCELLED** | Operator cancelled. **Terminal.** No output emitted. | — |
| **RETRY** | Retry policy decided to re-attempt. Job is re-queued with attempt counter incremented. | → QUEUED |

### 2.3 State Invariants

1. A Job is in exactly one state at any point in time.
2. SUCCEEDED, CANCELLED are terminal. FAILED is terminal unless retried.
3. The transition RUNNING → CANCELLED must interrupt the Worker gracefully (SIGTERM with grace period).
4. State transitions are written to the runtime log before the transition is committed.

---

## 3. Scheduled Jobs

Hermes runs four canonical job schedules. Schedules are configurable; the defaults below are the baseline.

### 3.1 Morning Brief

| Field | Value |
|---|---|
| **Schedule** | 06:30 local time, weekdays |
| **Job Kind** | `daily_brief` |
| **Inputs** | Previous US close → 06:25 local window |
| **Output** | Daily Brief Report (Markdown + JSON companion) |
| **Notification** | Default subscriber list (configurable) |
| **Timeout** | 5 minutes wall-clock |
| **Retry policy** | Manual (operator decides) |

### 3.2 Evening Brief

| Field | Value |
|---|---|
| **Schedule** | 16:30 local time, weekdays |
| **Job Kind** | `daily_brief` (extended window) |
| **Inputs** | 06:25 → 16:25 local window |
| **Output** | Daily Brief Report (end-of-day variant) |
| **Notification** | Default subscriber list |
| **Timeout** | 5 minutes |
| **Retry policy** | Manual |

### 3.3 Weekend Review

| Field | Value |
|---|---|
| **Schedule** | Friday 17:00 local time |
| **Job Kind** | `weekly_review` |
| **Inputs** | Monday 06:30 → Friday 16:30 window |
| **Output** | Weekly Review Report (Markdown + JSON) |
| **Notification** | Default subscriber list |
| **Timeout** | 15 minutes |
| **Retry policy** | Manual |

### 3.4 Future Scheduled Research

A general `research_job` kind is reserved for future use cases:

- Ad-hoc scheduled scans ("scan watchlist every 6 hours")
- Sectoral sweeps
- Event-driven research ("FOMC day → trigger sectoral review")

The Job descriptor carries a generic payload; the Worker dispatches based on `job_kind`. Adding new scheduled research does NOT require changes to the Scheduler or Queue.

---

## 4. Runtime State

Hermes has a top-level runtime state that reflects its operational posture. State transitions are observable and trigger Notification messages.

### 4.1 State Diagram

```
                  ┌───────┐
        startup   │       │   shutdown
   ────────────►  │ IDLE  │  ────────────►  (process exit)
                  │       │
                  └───┬───┘
                      │ job dequeued
                      ▼
                  ┌───────┐
                  │       │   job done
                  │ BUSY  │  ─────────────►  IDLE
                  │       │
                  └───┬───┘
                      │ error / partial failure
                      ▼
                  ┌───────────┐
                  │ DEGRADED  │
                  │           │  recovery
                  └─────┬─────┘  ─────────►  BUSY or IDLE
                        │
                        │ operator command
                        ▼
                  ┌─────────────┐
                  │ MAINTENANCE │  operator command
                  └─────┬───────┘  ─────────►  IDLE
                        │
                        │ network / API loss
                        ▼
                  ┌─────────┐
                  │ OFFLINE │   recovery
                  └────┬────┘  ────────►  DEGRADED
```

### 4.2 State Definitions

| State | Description | Notifications |
|---|---|---|
| **IDLE** | Queue empty, Worker idle, Scheduler ticking. | None (silent). |
| **BUSY** | Worker is processing a Job. | None (silent; report emissions are separate). |
| **DEGRADED** | One or more subsystems failing non-fatally. Reports may be partial. | Send "degraded mode" notice to operator channel. |
| **MAINTENANCE** | Operator-initiated pause. No new Jobs dequeued. | Send "maintenance mode" notice. |
| **OFFLINE** | Cannot reach Notification transports AND/OR cannot reach required external APIs (LLM, source feeds). Queue continues to accept jobs but Worker does not dequeue. | Send "offline" notice on entry; retry notice on recovery. |

### 4.3 State Transitions

| From | To | Trigger |
|---|---|---|
| (process start) | IDLE | Worker thread ready, Queue accessible |
| IDLE | BUSY | Worker dequeues a Job |
| BUSY | IDLE | Job reaches SUCCEEDED / FAILED / CANCELLED |
| BUSY | DEGRADED | Subsystem reports partial failure (e.g., one source feed unreachable) |
| DEGRADED | BUSY / IDLE | All subsystems healthy again |
| (any) | MAINTENANCE | Operator command |
| MAINTENANCE | IDLE | Operator command |
| (any) | OFFLINE | Reachability check fails for ≥ N consecutive probes |
| OFFLINE | DEGRADED | Reachability restored |

### 4.4 State Invariants

1. Runtime state is observable via the (future) `/status` remote command.
2. Runtime state transitions are logged with timestamp and trigger reason.
3. DEGRADED state does NOT block Job execution; partial outputs are emitted with a "degraded" provenance flag (already supported by SIGNAL Report Specification §6).
4. MAINTENANCE blocks Worker dequeue but does not stop the Scheduler (so scheduled jobs accumulate in the Queue and run when maintenance ends).

---

## 5. Notification Pipeline

The Notification subsystem delivers composed Reports to one or more transports. The architecture is transport-agnostic: Hermes must be able to add a new transport without modifying the Dispatcher or the Report Generator.

### 5.1 Notification Architecture

```
┌─────────────────────┐
│ Report Generator     │
│ (Markdown + JSON)    │
└──────────┬──────────┘
           │ produces a Notification envelope:
           │ { report_kind, format, payload,
           │   produced_at, recipients, priority }
           ▼
┌─────────────────────┐
│ Notification         │   applies routing rules:
│ Dispatcher           │   - per-recipient preferences
│                      │   - format selection (markdown vs json)
│                      │   - rate limiting
│                      │   - aggregation (multiple reports → one message)
└──────────┬──────────┘
           │ dispatches to N transports concurrently
           │
           ├──► ┌─────────────────┐
           │    │ Telegram Adapter│  ─► Telegram Bot API
           │    └─────────────────┘
           ├──► ┌─────────────────┐
           │    │ WeChat Adapter   │  ─► WeChat Work API
           │    └─────────────────┘
           ├──► ┌─────────────────┐
           │    │ Discord Adapter  │  ─► Discord Webhook
           │    └─────────────────┘
           ├──► ┌─────────────────┐
           │    │ Email Adapter    │  ─► SMTP / SES
           │    └─────────────────┘
           └──► ┌─────────────────┐
                │ Webhook Adapter  │  ─► HTTP POST (generic)
                └─────────────────┘
```

### 5.2 Notification Envelope

The Dispatcher consumes a single `Notification` object:

```
Notification:
  id:                 ULID
  produced_at:        ISO8601 UTC
  report_kind:        daily_brief | weekly_review | per_entity_brief | alert
  format:             markdown | json | text
  payload:            Report object (domain model) OR rendered Markdown/JSON
  subject:            short subject line (for email / push)
  recipients:         list of recipient descriptors (per-transport routing)
  priority:           low | normal | high
  correlation_id:     ULID linking back to the Job that produced this Report
```

### 5.3 Adapter Contract

Every transport adapter implements a single interface:

```python
class NotificationAdapter(Protocol):
    name: str  # "telegram", "wechat", etc.
    def send(self, notification: Notification) -> DeliveryResult: ...
```

`DeliveryResult` indicates: `delivered`, `failed_retryable`, `failed_terminal`, `skipped_disabled`.

### 5.4 Adapter Independence

- Adapters are stateless across calls; configuration (tokens, channel IDs, etc.) is loaded at startup.
- Adapters do NOT know about each other; multi-channel delivery is the Dispatcher's concern.
- Adding a new transport requires writing a new Adapter; no Dispatcher or Generator changes.

### 5.5 Supported Transports (MVP)

| Transport | Status | Notes |
|---|---|---|
| Telegram | MVP | Bot API; Markdown supported |
| WeChat | MVP | Work API; Markdown stripped to plain text on free-form channels |
| Discord | MVP | Webhook; Markdown supported |
| Email | MVP | SMTP; both text and HTML bodies |
| HTTP Webhook | MVP | Generic POST with JSON body; HMAC signing optional |

### 5.6 Routing and Preferences

- Per-recipient preferences control: enabled transports, format (markdown / json), quiet hours, language.
- Operator channel (`#ops`) receives all DEGRADED / OFFLINE / MAINTENANCE transitions automatically.
- Reader channels (per subscriber) receive scheduled reports only.

---

## 6. Command Readiness

Hermes will eventually accept remote commands from operators and readers. This checkpoint defines the command surface area but does NOT implement the gateway. Commands are namespaced with a leading `/`.

### 6.1 Reserved Command Surface

| Command | Purpose | Required scope |
|---|---|---|
| `/daily` | Trigger an ad-hoc Daily Brief cycle. | operator |
| `/status` | Return current Runtime State + queue depth + last cycle result. | operator, reader |
| `/queue` | List pending and recent Jobs. | operator |
| `/research` | Trigger an ad-hoc research job (synthesis, theme evolution). | operator |
| `/scan` | Trigger an ad-hoc watchlist scan (pulls from sources, generates Signals). | operator |

### 6.2 Command Gateway (Future)

- Accepts commands over HTTPS (TLS 1.3+).
- Authentication: per-recipient token; rate limiting per recipient.
- Commands are translated into Jobs and enqueued via the same Scheduler path (no privileged code path).
- Command results delivered as Notifications to the requesting recipient.

### 6.3 Readiness Invariants

1. The command surface is reserved; no other component may use these command names.
2. Command gateway MUST go through the same Scheduler → Queue → Worker path. There is no "direct execution" path.
3. Command authorization is checked BEFORE the Job is enqueued. Unauthorized commands are logged and silently dropped (or returned as an error to the requester).

---

## 7. Failure Handling

Hermes must remain operational under partial failure. The design uses four orthogonal failure-handling mechanisms.

### 7.1 Retry Policy

- Configurable per Job Kind (default: Manual for scheduled briefs; Exponential for ad-hoc scans).
- Retry parameters: `max_attempts`, `base_delay_seconds`, `max_delay_seconds`, `jitter_ratio`.
- Retries transition the Job through `FAILED → RETRY → QUEUED` with `attempt` counter incremented.

### 7.2 Timeout Policy

- Every Job has a wall-clock timeout (defaults in §3).
- On timeout, the Worker is interrupted with SIGTERM; a 30-second grace period follows; then SIGKILL.
- Timed-out Jobs transition to FAILED with reason=`timeout`.

### 7.3 Partial Report Generation

- If a Report's data is incomplete (e.g., one source feed timed out), the Report is still emitted with a `degraded` provenance flag (already supported by the SIGNAL Report Specification §6 — `Report.degrade_mode`).
- Subscribers to the affected Report receive it with a note in the provenance footer indicating which subsystem was degraded.
- Degraded Reports do NOT auto-retry. The operator may `/scan` to re-trigger.

### 7.4 Graceful Degradation

When a subsystem fails non-fatally:

1. Runtime State transitions to DEGRADED (per §4).
2. Worker continues accepting Jobs but annotates outputs with the degradation.
3. Notification Dispatcher queues failure notices for the operator channel.

When a fatal failure occurs:

1. Worker stops dequeueing new Jobs.
2. In-flight Jobs are interrupted per the timeout policy.
3. Runtime State transitions to OFFLINE.
4. Process exits non-zero (system supervisor restarts it).

---

## 8. Logging

Hermes emits three classes of logs. Logs are JSON-structured (one event per line) for downstream aggregation.

### 8.1 Runtime Logs

- Process lifecycle (start, stop, signal received).
- State transitions (per §4).
- Scheduler ticks, queue depth over time.
- Worker pool sizing.

### 8.2 Execution Logs

- Per-Job: enqueue, dequeue, intermediate stage events, completion.
- Per-Job: subsystem calls (which APIs were hit, latencies).
- Per-Job: retry decisions and reasons.

### 8.3 Audit Logs

- Append-only log of every Notification dispatched (recipient, transport, status).
- Append-only log of every Job state transition (immutable; signed per Hermes governance).
- Append-only log of operator commands received.

### 8.4 Log Retention

- Default retention: 90 days for runtime and execution logs; indefinite for audit logs.
- Logs are NOT shipped off-device by Hermes itself. A sidecar (e.g., journald, fluent-bit, vector) is responsible for forwarding to aggregation storage.

---

## 9. Deployment Assumptions

The MVP infrastructure is designed for three deployment targets, in order of priority.

### 9.1 Single-Machine Deployment (MVP)

- Hermes runs as a single OS process.
- All state (Queue, runtime logs) lives in local files / SQLite.
- One Worker thread; one Scheduler thread; one Notification Dispatcher thread.
- Process supervisor (systemd, supervisord, or launchd) restarts on crash.

### 9.2 WSL2 Compatibility

- Hermes runs under Windows Subsystem for Linux 2 (Ubuntu 22.04 LTS or later).
- Filesystem paths: use POSIX paths internally; WSL2 interop (`/mnt/c/...`) is supported but not the default.
- Notifications to Windows-native channels (Windows Mail, Windows Toast) are deferred.
- Cron is unreliable under WSL2; the Scheduler uses an in-process timer instead of system cron.

### 9.3 Docker Compatibility

- Hermes ships a `Dockerfile` based on a slim Python 3.12 image.
- Configuration via environment variables (12-factor style).
- Logs to stdout/stderr in JSON format.
- Single-process container; the orchestrator handles restarts.
- Volume mounts for: runtime data dir, audit log dir, configuration dir.

### 9.4 Future Linux Server Compatibility

- Hermes will run on bare-metal Linux (Ubuntu LTS) once the MVP is stable.
- Systemd unit file ships with the deployment package.
- Configuration: TOML file in `/etc/hermes/config.toml`.
- Logs: journald (forwarded by the OS) and a sidecar.

### 9.5 Network Assumptions

- Outbound HTTPS to: LLM provider, source feeds, Notification transport APIs.
- Inbound HTTPS: future command gateway (post-MVP).
- No inbound ports in the MVP.
- Outbound-only simplifies firewall rules and reduces attack surface.

---

## 10. Future Extension Points

The architecture explicitly accommodates the following future extensions without breaking the MVP.

| Extension | Where it plugs in |
|---|---|
| Multi-Worker parallelism | Queue (already supports concurrent dequeue with per-Job locking) |
| Distributed Hermes | Replace local Queue with a queue broker (e.g., NATS); Worker is stateless |
| Persistent Queue | Queue interface gains a `durable` backend implementation |
| Additional Notification transports | New adapter under `NotificationDispatcher` |
| Command gateway | New `CommandGateway` component behind the Scheduler |
| Remote source pull | New `SourceConnector` component invoked by Worker |
| LLM provider rotation | LLM client is injected; multiple providers behind a single interface |
| Per-reader personalization | Notification envelope gains `reader_profile`; Generator emits reader-specific content |

---

## 11. Conformance

This spec is binding for the next checkpoint (Phase 7 implementation). The implementation must:

1. Match the topology in §1 (no extra components; no missing components).
2. Implement the Job lifecycle states in §2 with the documented transitions.
3. Honor the four scheduled jobs in §3 with the documented defaults.
4. Implement the runtime states in §4 with the documented transitions.
5. Implement at least the five MVP Notification transports (§5.5) behind the Adapter contract.
6. Implement the retry, timeout, partial-report, and graceful-degradation behaviors in §7.
7. Emit the three log classes in §8.
8. Support the three MVP deployment targets in §9 (single-machine, WSL2, Docker).

A future change to this spec requires an RFC.

---

## 12. Open Questions

These questions are NOT resolved by this spec. They require operator input or future checkpoints.

1. **Notification rate limits.** What is the per-recipient-per-hour maximum? The MVP defaults to "no limit" with the understanding that the operator will configure sensible limits.
2. **Audit log signing.** HMAC-SHA256 vs. detached Ed25519 signature? The MVP defaults to HMAC-SHA256 (simpler key management); Ed25519 is a future option.
3. **Worker pool sizing.** Single Worker is the MVP. The Queue is already concurrent-safe; multi-Worker is a post-MVP scaling step.
4. **Job cancellation grace period.** 30 seconds is the MVP default; the operator may override per Job Kind.
5. **Notification aggregation window.** When multiple Reports land within a short window, the Dispatcher MAY aggregate them into a single message. The MVP does not aggregate; the aggregation policy is a future setting.
6. **Time-zone policy.** All schedules use the operator's local time. Is that the right default, or should they use UTC with operator-override?
7. **Offline detection threshold.** §4.3 says "≥ N consecutive probes". What is N? The MVP defaults to 3 (≈ 90 seconds at 30s probe interval); operator can override.

---

## 13. Versioning of This Document

| Version | Date | Change |
|---|---|---|
| 1.0 | 2026-07-21 | Initial infrastructure specification: topology, job lifecycle, scheduled jobs, runtime states, notification pipeline, command readiness, failure handling, logging, deployment assumptions, extension points. |

Adding a component or a new state is MAJOR. Adjusting defaults is MINOR. Wording fixes are PATCH.