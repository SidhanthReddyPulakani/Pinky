# Pinky — System Design Specification v1

**Status:** Canonical system-design baseline  
**Purpose:** Master design contract for Pinky implementation  
**Scope:** Local-first personal AI agent/runtime  
**Primary design basis:** Current Pinky architecture, database schema, domain/state-machine, event subsystem, package architecture, and technology-stack specifications.

---

## 0. How to Use This Document

This document is the **canonical map for implementation**.

It consolidates the current Pinky system design into one specification so implementation can proceed subsystem-by-subsystem without repeatedly rediscovering architectural decisions.

### Normative language

- **MUST** — binding requirement or invariant.
- **SHOULD** — preferred design unless a documented reason exists to deviate.
- **MAY** — permitted option.
- **OUT OF SCOPE** — intentionally not implemented in the relevant phase.
- **UNSPECIFIED** — the current design documents do not define the behavior; do not invent a decision silently.

### Source-of-truth rule

This document consolidates the current Pinky design. The detailed subsystem specifications remain authoritative for details that belong specifically to those subsystems.

When a conflict is discovered:

1. Identify the conflicting statements.
2. Do not silently reconcile them.
3. Resolve the conflict as an explicit design decision.
4. Update this document and the affected subsystem specification.

---

# 1. Product Definition

## 1.1 What Pinky Is

Pinky is a **local-first personal AI agent/runtime** designed to receive events, represent responsibilities as Tasks, create Occurrences from triggers, determine eligibility, schedule work, manage scarce resources, and eventually dispatch work for execution.

The runtime identity of Pinky is the **Core runtime**, not the LLM.

The LLM is a replaceable computational capability used by future execution paths.

## 1.2 Initial Operating Model

Phase 1 assumes:

- one machine,
- one user,
- one Pinky Core runtime process,
- one separate Tauri desktop process,
- SQLite as the durable store,
- local API communication between the desktop shell and Core,
- no distributed infrastructure.

## 1.3 Architectural Philosophy

Pinky separates:

- deterministic behavior,
- interactive behavior,
- autonomous behavior,

while keeping these as execution classes/lane concepts rather than turning them into unrelated runtimes.

Pinky also separates:

- facts from responsibilities,
- responsibility from activation,
- activation from scheduling,
- scheduling from execution,
- authorization from approval,
- approval from execution.

---

# 2. System Context

```text
                    User
                     |
                     v
             Tauri Desktop App
             React + TypeScript
                     |
              Local HTTP/API
                     |
                     v
              +-------------+
              | Pinky Core  |
              | Python      |
              | asyncio     |
              +-------------+
                |    |    |
                |    |    +--> Scheduler
                |    |
                |    +-------> Task / Occurrence / Trigger
                |
                +-----------> Event subsystem
                |
                +-----------> SQLite
                |
                +-----------> Future Dispatcher / Execution
```

The Core owns domain and application behavior.

The UI does not directly manipulate SQLite.

The API exposes domain/application operations rather than raw CRUD.

---

# 3. Requirements

## 3.1 Functional Requirements

### FR-01 — Event Ingestion

Pinky MUST accept events from heterogeneous sources through source-specific readers/adapters.

### FR-02 — Event Normalization

Pinky MUST convert source-specific input into a canonical Event representation before domain processing.

### FR-03 — Durable Event History

Accepted Events MUST be durably persisted as immutable historical facts.

### FR-04 — Event Deduplication

Pinky MUST prevent duplicate logical Events when source identity or a deduplication key is available.

Deduplication MUST remain correct under concurrent ingestion.

### FR-05 — Event Delivery and Replay

Persisted Events MUST be recoverable for internal consumers.

Consumer progress MUST be durable.

Replay MUST be possible after failure.

### FR-06 — Task Management

Pinky MUST persist Tasks and support their lifecycle:

`DRAFT → ACTIVE → PAUSED → CANCELLED / COMPLETED`

Transitions MUST be controlled by the Task Manager.

### FR-07 — Task Triggering

Tasks MUST support:

- SCHEDULE triggers,
- EVENT triggers,
- CONDITION triggers,
- MANUAL triggers.

A Task MAY have multiple triggers.

### FR-08 — Occurrence Creation

Each logical Task activation MUST create an Occurrence representing one activation instance.

### FR-09 — Idempotent Activation

Repeated processing of the same logical trigger MUST NOT create duplicate Occurrences.

`activation_key` is the durable logical idempotency key.

### FR-10 — Eligibility Evaluation

Pinky MUST determine whether an Occurrence is logically eligible to become schedulable.

Eligibility covers concerns such as:

- Task lifecycle,
- dependencies,
- cancellation,
- conditions,
- runnable time,
- expiration.

Eligibility MUST remain separate from resource capacity.

### FR-11 — Temporal Scheduling

Pinky MUST support the temporal mechanisms required by the current design, including:

- exact timestamps,
- delays,
- intervals,
- cron-style schedules,
- deadlines,
- retry-related timing,
- timeouts,
- scheduled condition evaluation.

The Wake Scheduler determines when work should be reconsidered.

The Run Scheduler determines whether runnable work can proceed.

### FR-12 — SchedulerWork

Pinky MUST maintain scheduler state separately from Task and Occurrence lifecycle.

SchedulerWork lifecycle:

`WAITING → READY → ADMITTED → DISPATCHED`

Exceptional/terminal states:

`CANCELLED`, `EXPIRED`

`QUEUED` MUST NOT be a durable SchedulerWork state.

### FR-13 — Priority Scheduling

Scheduling priority MUST be derived from:

- Task base priority,
- Occurrence urgency,
- deadline pressure,
- bounded aging.

Effective priority is derived state, not the authoritative stored identity of work.

### FR-14 — Starvation Prevention

The scheduler MUST prevent indefinite starvation using bounded aging and/or the explicitly defined fairness mechanisms.

Phase 1 uses simple, bounded mechanisms rather than a complex fair-share scheduler.

### FR-15 — Resource-Aware Admission

Pinky MUST admit work only when required resources and concurrency capacity are available.

### FR-16 — Atomic Resource Reservation

Resource availability checking, reservation, and transition to `ADMITTED` MUST be atomic.

Concurrent scheduler decisions MUST NOT over-reserve resources.

### FR-17 — Backpressure

Pinky MUST provide Task-level backpressure policies capable of limiting excessive activation.

Supported policy concepts include:

- DROP,
- COALESCE,
- hard `max_pending`.

Coalescing semantics MUST be task-specific.

### FR-18 — Deadline and Expiration Handling

Pinky MUST distinguish runnable work from expired work.

Misfire behavior MUST support the defined policy of:

- RUN,
- SKIP.

### FR-19 — Cancellation

Tasks and Occurrences MUST support cancellation.

Cancellation of dispatched work is cooperative in Phase 1.

### FR-20 — Dispatch Boundary

Admitted work MUST be handed to a Dispatcher boundary.

`ADMITTED` MUST NOT mean executed.

`DISPATCHED` MUST NOT mean completed.

Execution success/failure belongs to the execution subsystem.

### FR-21 — Scheduler Explainability

Pinky MUST retain sufficient scheduler decision information to explain meaningful scheduling outcomes.

Decision records include:

- decision ID,
- SchedulerWork ID,
- decision type,
- creation time,
- effective priority,
- priority components,
- resource snapshot,
- reason code,
- details.

### FR-22 — Crash Recovery

Pinky MUST reconstruct authoritative operational state after Core restart.

In-memory queues and timers MUST NOT be the sole source of truth.

### FR-23 — Reservation Recovery

Pinky MUST detect and reconcile stale or incomplete resource reservations during recovery.

### FR-24 — Replay-Safe Processing

Consumers, trigger processing, Occurrence creation, and scheduler recovery MUST tolerate replay.

### FR-25 — Safety Policy Separation

Pinky MUST distinguish:

- authorization,
- approval,
- execution.

Execution mode describes computation/execution class; it does not by itself establish trust or safety.

---

# 4. Non-Functional Requirements

## NFR-01 — Durability

Authoritative accepted state MUST survive Core crash/restart.

## NFR-02 — Crash Recoverability

Operational state MUST be reconstructible from durable state.

## NFR-03 — Consistency

Domain invariants MUST hold under concurrency and failure.

## NFR-04 — Atomicity

Operations that establish authoritative multi-record state MUST be atomic.

## NFR-05 — Deterministic Scheduling

Given the same observable scheduling state and policy inputs, the scheduler SHOULD make the same decision.

## NFR-06 — Bounded Resource Usage

Where finite limits are defined, the implementation MUST prevent unbounded accumulation.

## NFR-07 — Fault Isolation

Failure of an individual reader MUST NOT bring down the Core runtime.

## NFR-08 — Local-First Operation

Phase 1 MUST operate without distributed infrastructure.

## NFR-09 — Low Idle Overhead

The Core SHOULD operate without requiring an LLM merely to remain idle or maintain scheduler state.

## NFR-10 — LLM Independence

The Event subsystem and Core startup MUST NOT depend on a configured LLM runtime.

## NFR-11 — Maintainability

Subsystem boundaries MUST prevent unnecessary coupling.

## NFR-12 — Observability

The system MUST expose sufficient logs, metrics, correlation information, and tracing to diagnose failures and scheduling decisions.

## NFR-13 — No Hidden Authoritative Runtime State

In-memory queues, caches, and timers MUST NOT be the only authoritative representation of durable work.

## NFR-14 — Idempotent Recovery

Repeating recovery MUST be safe.

## NFR-15 — External Side-Effect Safety

Scheduling or execution classification MUST NOT automatically imply that external side effects are safe.

---

# 5. Constraints

- **C-01:** One machine.
- **C-02:** One user.
- **C-03:** Exactly one Pinky Core process in Phase 1.
- **C-04:** SQLite is the Phase 1 durable database.
- **C-05:** No distributed infrastructure in Phase 1.
- **C-06:** Execution is outside the initial implementation boundary.
- **C-07:** Tauri is a separate process from Core.

---

# 6. Domain Model

## 6.1 Event

An Event is an immutable historical fact entering Pinky.

Canonical fields include:

- `event_id`
- `event_seq`
- `event_type`
- `source`
- `source_event_id`
- `dedupe_key`
- `occurred_at`
- `received_at`
- `payload`
- `metadata`
- `causation_id`
- `correlation_id`
- `schema_version`

`source_event_id` and `dedupe_key` are optional at the source boundary.

`event_id` is Pinky-generated.

`event_seq` is a durable SQLite log position used for replay and processing order; it is not semantic event ordering.

`occurred_at` is source-reported time.

`received_at` is Pinky's acceptance/persistence time.

Both are stored in UTC.

## 6.2 Task

A Task is a persistent responsibility, intent, and policy.

A Task defines things such as:

- name,
- description,
- goal,
- execution mode,
- base priority,
- triggers,
- eligibility rules,
- concurrency policy,
- deadline policy,
- backpressure policy,
- resource requirements,
- authorization,
- lifecycle.

A Task is not an individual execution attempt.

## 6.3 Trigger

A Trigger defines how a Task becomes activated.

Types:

- SCHEDULE,
- EVENT,
- CONDITION,
- MANUAL.

Triggers are separate from Task lifecycle and Occurrence lifecycle.

## 6.4 Occurrence

An Occurrence represents one activation of a Task.

Conceptual fields include:

- `occurrence_id`
- `task_id`
- `trigger_id`
- `trigger_event_id`
- `activation_key`
- `created_at`
- `activated_at`
- `runnable_at`
- `deadline_at`
- `urgency`
- `status`
- `coalesce_key`
- `metadata`
- `updated_at`
- `finished_at`

Occurrence lifecycle:

`PENDING → ACTIVATED → COMPLETED / SKIPPED / CANCELLED / EXPIRED`

## 6.5 SchedulerWork

SchedulerWork is the scheduler's representation of work that may compete for execution resources.

Lifecycle:

`WAITING → READY → ADMITTED → DISPATCHED`

Exceptional terminal states:

`CANCELLED`, `EXPIRED`

Scheduler state MUST remain separate from Occurrence state.

## 6.6 Resource

A Resource represents scarce execution capacity.

Examples:

- `strong_llm`
- `small_llm`
- `GPU`
- `browser`
- `filesystem_worker`
- `network_worker`

Resources have capacity and state.

Resource availability is derived from active reservations.

## 6.7 Reservation

A Reservation reserves a resource for a SchedulerWork item.

Phase 1 uses one reservation row per resource per SchedulerWork item.

Reservations are active or released.

Invariant:

`sum(active reserved quantity) <= resource capacity`

---

# 7. State Machines

## 7.1 Task

```text
DRAFT
  |
 ACTIVE
  | \
  |  PAUSED
  |     |
  |   ACTIVE
  |
  +--> CANCELLED
  |
  +--> COMPLETED
```

No arbitrary reopening is assumed in Phase 1.

## 7.2 Occurrence

```text
PENDING
   |
ACTIVATED
 /   |    |      \
COMPLETED SKIPPED CANCELLED EXPIRED
```

## 7.3 SchedulerWork

```text
WAITING
   |
 READY
   |
ADMITTED
   |
DISPATCHED
```

Exceptional paths:

```text
WAITING / READY -> CANCELLED
WAITING / READY -> EXPIRED
```

`QUEUED` is an in-memory scheduling structure, not durable state.

## 7.4 Event Processing

Event processing stages are:

`RECEIVED → VALIDATED → NORMALIZED → DEDUPLICATED → PERSISTED → ROUTED`

These are **processing stages**, not Event lifecycle states.

An Event remains an immutable historical fact.

## 7.5 Reader

Reader lifecycle must support:

- startup,
- active listening/polling,
- failure isolation,
- restart according to policy,
- health reporting,
- graceful shutdown.

---

# 8. Event Subsystem

## 8.1 Reader Manager

The Reader Manager owns:

- reader lifecycle,
- source connections/listening/polling,
- parsing ownership boundaries,
- restart policy,
- health,
- shutdown,
- reader-level logging.

A reader owns source-specific listening/polling, parsing, and source checkpoints.

A reader MUST NOT own:

- database persistence,
- global deduplication policy,
- Task activation,
- Scheduler behavior,
- Execution,
- LLM invocation.

## 8.2 Reader Types

Readers MAY be listener-based or polling-based.

Polling is a source implementation detail, not a separate Event type.

## 8.3 Event Intake

`EventIntake.accept(incoming)` conceptually performs:

1. validation,
2. normalization,
3. identity/dedupe derivation or checking,
4. durable persistence,
5. result reporting.

Possible results:

- `ACCEPTED`
- `DUPLICATE`
- `REJECTED`

Temporary database failure is an error, not a duplicate or rejection.

Database uniqueness constraints are the final deduplication authority.

Application-level lookup is preliminary optimization only.

## 8.4 Event Store

The Event Store contract includes operations conceptually equivalent to:

- append,
- get,
- exists,
- query.

Queries need to support useful access by:

- Event ID,
- dedupe key,
- source Event ID,
- source,
- event type,
- time range,
- pagination.

## 8.5 Event Routing

Routing initially occurs in-process.

Persist-before-publish is required.

In-process routing alone is not durable messaging.

## 8.6 Outbox

The Outbox provides durable delivery/recovery semantics.

Phase 1 stores one Outbox record per Event.

States:

- `PENDING`
- `PUBLISHED`

An Event is uniquely associated with its Outbox record.

## 8.7 Consumer Offsets

Consumer state includes:

- `consumer_id`
- `last_processed_event_seq`
- `updated_at`

Processing rule:

```text
read event
  -> process event
  -> persist consumer-owned state
  -> advance offset
```

Where possible, consumer state persistence and offset advancement SHOULD occur in the same transaction.

If a crash occurs before offset advancement, replay is expected.

Consumers MUST therefore be replay-safe.

## 8.8 Backpressure

The initial implementation SHOULD begin with direct asynchronous intake and benchmarking.

If required, use a bounded asyncio queue with Intake workers.

Do not introduce an external broker merely to solve theoretical scale.

---

# 9. Task and Trigger System

## 9.1 Task Semantics

A Task expresses persistent intent and execution policy.

It is not:

- an event,
- an occurrence,
- scheduler queue state,
- an execution result.

## 9.2 Multiple Triggers

A Task MAY have multiple triggers.

Each trigger independently defines an activation mechanism.

## 9.3 Activation Idempotency

`activation_key` MUST identify the logical activation.

Examples:

```text
event trigger:
hash(trigger_id, event_seq)

schedule trigger:
hash(trigger_id, scheduled_for)

manual trigger:
hash(trigger_id, request_id)
```

These examples establish the design pattern; exact hashing representation remains an implementation detail.

## 9.4 Dependencies

Dependencies are represented separately from trigger types.

In Phase 1, a dependency is satisfied when the referenced Task reaches `COMPLETED`.

Dependency is an eligibility condition, not a trigger type.

## 9.5 Backpressure and Coalescing

Backpressure policy MAY:

- drop activations,
- coalesce activations,
- enforce a maximum pending count.

Coalescing MUST have task-specific semantics.

Pinky MUST NOT assume that every event type can safely be reduced to "latest."

---

# 10. Eligibility

Eligibility answers:

> **May this work run?**

Eligibility considers:

- valid Occurrence,
- Task lifecycle,
- dependencies,
- conditions,
- cancellation,
- runnable time,
- expiration.

Eligibility does NOT answer:

> **Can the machine run it right now?**

Resource availability and concurrency capacity belong to admission.

---

# 11. Scheduler

## 11.1 Scheduler Responsibilities

The Scheduler consumes schedulable work.

It does not care where the work originated.

The conceptual decision pipeline is:

```text
Work Arrives
    ↓
Eligibility
    ↓
Priority Model
    ↓
Queue Model
    ↓
Fairness / Aging
    ↓
Resource Admission
    ↓
Dispatch
```

## 11.2 Decision Order

The Run Scheduler should evaluate in this order:

1. Occurrence is valid.
2. Task is active.
3. Occurrence is eligible.
4. Work is runnable now.
5. Work has not expired.
6. Effective priority is calculated.
7. Queue ordering is established.
8. Concurrency limits are checked.
9. Resources are checked.
10. Reservation + admission are committed atomically.
11. Decision evidence is recorded.
12. Work is handed to Dispatcher.

## 11.3 Priority

Conceptually:

```text
effective_priority =
    task_base_priority
    + occurrence_urgency
    + deadline_pressure
    + bounded_aging
```

Exact weights are configuration.

The derived value MUST NOT become the authoritative identity of the work item.

## 11.4 Aging

Aging MUST be bounded.

The purpose is starvation prevention, not unlimited priority escalation.

## 11.5 Queue Topology

Phase 1 uses a logically unified scheduling model with execution-class/lane safeguards:

- Interactive,
- Autonomous,
- Deterministic.

Resources remain shared unless a specific resource is explicitly configured otherwise.

Do not isolate resource pools without a concrete requirement.

## 11.6 Fairness

Phase 1 intentionally avoids:

- complex fair-share scheduling,
- quotas,
- priority inheritance,
- elaborate tenant-style scheduling.

The initial model uses:

- priority,
- bounded aging,
- concurrency,
- resource admission,
- optional lane safeguards.

## 11.7 Concurrency

Concurrency policy is separate from eligibility.

Pinky MUST distinguish:

- logically eligible,
- runnable,
- admitted,
- executing.

## 11.8 Resource Admission

Admission means:

> the scheduler has successfully reserved the resources and concurrency capacity required by the work.

Admission does not mean execution has begun.

## 11.9 Atomic Admission

The following MUST be one authoritative database transaction:

```text
check capacity
+
create/update reservation
+
transition SchedulerWork -> ADMITTED
```

The transaction MUST be short.

It MUST NOT remain open while external work executes.

## 11.10 Preemption

Phase 1 is non-preemptive.

Once dispatched, cancellation is cooperative.

## 11.11 Backfill

Phase 1 does not require a formal planning optimizer.

A simple backfill policy MAY scan blocked high-priority candidates and admit an admissible lower-priority candidate.

A blocked high-priority work item MUST NOT unnecessarily prevent admissible lower-priority work from running.

## 11.12 Wake Scheduler

The Wake Scheduler answers:

> When should the system reconsider work?

The Run Scheduler answers:

> What work can run now?

Timer infrastructure such as APScheduler MAY act as a timer adapter, but it MUST NOT become the domain source of truth.

---

# 12. Persistence Architecture

## 12.1 Database

SQLite is the Phase 1 durable store.

## 12.2 SQLite Configuration

The design expects:

- WAL mode,
- foreign keys enabled,
- short transactions,
- explicit migrations,
- scheduler-critical indexes,
- controlled write ownership.

## 12.3 Authoritative State

The database is authoritative for durable domain and scheduler state.

In-memory structures are derived runtime state.

## 12.4 Migrations

Schema changes MUST be represented as explicit migrations.

Alembic is the migration mechanism.

## 12.5 Critical Invariants

At minimum:

- Event IDs are unique.
- Source Event identity uniqueness is enforced where provided.
- Dedupe uniqueness is enforced where provided.
- Activation keys prevent duplicate Occurrences.
- Foreign-key relationships remain valid.
- Active resource reservations cannot exceed capacity.
- SchedulerWork state remains consistent with its authoritative records.

---

# 13. Concurrency Model

Pinky Core uses Python `asyncio`.

Multiple readers MAY concurrently submit Events.

The architecture MUST NOT depend on a global Python lock for correctness unless explicitly chosen and justified.

SQLite provides an important durable serialization boundary.

A single async writer task MAY be used as an implementation strategy, but it is not itself a domain requirement.

Correctness MUST come from:

- transactions,
- database constraints,
- state-machine validation,
- idempotency,
- recovery logic.

---

# 14. Failure and Recovery Model

## 14.1 General Principle

Anything required after restart MUST be reconstructible from durable state.

## 14.2 Reader Failure

A failing reader MUST be isolated.

The Reader Manager determines restart and health behavior.

## 14.3 Database Failure

Database failures MUST surface as operational errors.

The system MUST NOT classify inability to persist as successful Event acceptance.

## 14.4 Crash During Event Processing

If processing occurs before durable consumer progress is advanced, the Event may be replayed.

Consumers MUST tolerate this.

## 14.5 Crash During Admission

Admission MUST be atomic so the system cannot persist a partial reservation/admission decision.

## 14.6 Crash After Admission

Startup recovery MUST reconcile SchedulerWork and Reservations.

## 14.7 Stale Reservations

Recovery MUST identify reservations that no longer correspond to valid live work and reconcile them according to the recovery policy.

## 14.8 Scheduler Recovery

Startup recovery must:

1. load persistent state,
2. identify stale/incomplete scheduler state,
3. reconcile reservations,
4. rebuild in-memory queues/indexes,
5. restore wake timers,
6. resume scheduling.

Recovery MUST be idempotent.

---

# 15. Safety, Authorization, and Side Effects

These concepts are deliberately separate.

```text
Authorization
     ↓
Approval
     ↓
Execution
```

Authorization answers whether an actor is allowed to request an operation.

Approval answers whether an operation may proceed where explicit approval is required.

Execution performs the operation.

Scheduling an operation MUST NOT be treated as equivalent to approving its side effects.

Execution mode MUST NOT itself be considered a safety boundary.

Detailed future approval and credential semantics are **UNSPECIFIED** unless defined by a later execution/security specification.

---

# 17. Safety Architecture

Safety is a cross-cutting property of Pinky. The runtime MUST NOT rely on the LLM, Task author, scheduler, or execution class alone to establish whether an action is safe or authorized.

## 16.1 Trust Boundaries

The system MUST distinguish:

```text
External / untrusted data
        ↓
Event
        ↓
Task / Occurrence
        ↓
Reasoning / proposal
        ↓
Authorization
        ↓
Approval (when required)
        ↓
Admission
        ↓
Dispatch
        ↓
Execution
        ↓
External side effect
```

A lower-trust input MUST NOT be able to elevate its own authority merely by being included in an Event, Task, prompt, or LLM context.

## 16.2 Safety Invariants

1. **Untrusted data MUST NOT grant authority.**
2. **LLM output MUST be treated as a proposal, not authority.**
3. **Scheduling MUST NOT imply authorization.**
4. **Admission MUST NOT imply authorization.**
5. **Execution mode MUST NOT imply trust.**
6. **External side effects MUST occur behind an explicit capability/authorization boundary.**
7. **Secrets MUST NOT be embedded in ordinary Events, Tasks, Occurrences, or logs.**
8. **Execution MUST occur behind an explicit execution/capability boundary.**
9. **Approval state MUST be durable whenever approval is required.**
10. **A crash MUST NOT silently convert an unapproved operation into an approved operation.**
11. **Replay MUST NOT duplicate an external side effect without an explicit idempotency strategy.**
12. **Untrusted external content MUST remain data even when interpreted by an LLM.**

## 16.3 Capability Model

Future execution should use explicit capabilities rather than implicit authority.

Examples include:

```text
filesystem.read
filesystem.write
filesystem.delete
network.request
browser.navigate
browser.interact
process.execute
llm.invoke
```

A Task or execution request MAY declare required capabilities.

The runtime MUST independently determine whether those capabilities are authorized.

A capability requirement is not itself permission.

## 16.4 Capability Resolution

The conceptual flow is:

```text
Requested operation
      ↓
Required capability
      ↓
Authorization policy
      ↓
Approval policy
      ↓
Admission
      ↓
Execution
```

The LLM MUST NOT be able to grant itself a capability.

External content MUST NOT be able to grant itself a capability.

## 16.5 Execution Class vs Trust

Execution classes:

- Deterministic
- Interactive
- Autonomous

are scheduling/execution characteristics.

They MUST NOT automatically become authorization levels.

For example, an Autonomous Task requiring `filesystem.delete` MUST still pass the applicable authorization and approval policies.

## 16.6 External Content and Prompt Injection

External content may contain instructions intended to manipulate an LLM.

Pinky MUST treat such content as **data**, not as a source of authority.

For example:

```text
Email / File / Web content
        ↓
Event payload
        ↓
LLM context
```

does not permit:

```text
Event payload
        ↓
new permission
```

Any action proposed from untrusted content MUST still pass normal authorization, approval, admission, and execution controls.

## 16.7 Secrets

Secrets include credentials, API keys, tokens, passwords, and similar sensitive material.

Secrets MUST NOT be stored directly in ordinary Event, Task, Occurrence, SchedulerWork, or diagnostic payloads.

Future execution design should use references to a dedicated secret/credential provider:

```text
Task
  ↓
Credential reference
  ↓
Secret provider
  ↓
Execution
```

The detailed secret-storage mechanism is UNSPECIFIED for Phase 1.

## 16.8 External Side-Effect Idempotency

Event deduplication and Occurrence idempotency do NOT guarantee external side-effect idempotency.

Example failure:

```text
External operation succeeds
        ↓
Pinky crashes
        ↓
Success result is not durably recorded
        ↓
Pinky retries
        ↓
External operation occurs twice
```

Phase 2 execution design MUST explicitly address this class of failure.

Possible mechanisms include:

- idempotency keys,
- durable operation records,
- provider-side idempotency,
- transactional outbox patterns,
- explicit non-idempotent operation handling.

No particular mechanism is mandated yet.

## 16.9 Approval Durability

Where an operation requires human approval, approval MUST be represented as durable state.

A transient UI state MUST NOT be treated as authoritative approval.

The approval record must be associated with the operation it authorizes.

Detailed approval semantics remain UNSPECIFIED until the execution/interactive design is defined.

## 16.10 Side-Effect Boundary

The system MUST make the transition into external side effects explicit.

Conceptually:

```text
Deterministic domain decision
        ↓
Authorized execution request
        ↓
Capability checks
        ↓
Approval checks
        ↓
Execution adapter
        ↓
External side effect
```

No scheduler optimization may bypass this boundary.

---

# 17. API Architecture

## 16.1 Boundary

The Tauri application communicates with Core through the local API.

FastAPI is the Phase 1 API framework.

## 16.2 Separation

The API layer MUST NOT contain domain logic that belongs in domain/application services.

The domain MUST NOT depend on HTTP.

## 16.3 API Style

The API SHOULD expose meaningful domain operations rather than simply exposing database tables as CRUD endpoints.

## 16.4 UI Boundary

The UI MUST NOT directly access SQLite.

The UI communicates with Core through the API.

---

# 18. Observability

Pinky SHOULD use:

- Python logging,
- OpenTelemetry,
- correlation IDs,
- structured diagnostic information,
- scheduler decision records,
- health information.

Observability MUST allow investigation of:

- Event ingestion,
- Event deduplication,
- reader failures,
- trigger activation,
- Occurrence creation,
- eligibility,
- scheduling decisions,
- resource admission,
- reservation state,
- recovery behavior.

---

# 19. Security

The current system design establishes the following principles:

- local-first operation,
- explicit authorization boundary,
- explicit approval boundary,
- explicit execution boundary,
- no assumption that scheduling equals authorization.

The following require a future explicit security specification if they become necessary:

- credential vault design,
- secret storage,
- authentication details,
- OS-level privilege model,
- network exposure policy,
- sandboxing of execution,
- external account authorization.

Do not invent these behaviors during Phase 1 implementation.

---

# 20. Performance and Capacity

The current design intentionally does **not** invent quantitative targets for:

- events/second,
- scheduling latency,
- startup time,
- recovery time,
- memory usage,
- database size.

These MUST be established before performance-sensitive optimization is treated as a requirement.

Phase 1 performance engineering should focus on:

- short SQLite transactions,
- bounded queues where needed,
- correct indexing,
- avoiding unnecessary global locks,
- measuring scheduler behavior,
- measuring Event intake under bursts,
- measuring restart/recovery behavior.

---

# 21. Configuration Model

Configuration precedence:

```text
Global
  ↓
Execution Class
  ↓
Task
  ↓
Occurrence
```

More-specific configuration overrides less-specific configuration.

Phase 1 SHOULD NOT introduce a generic policy DSL.

---

# 22. Package Architecture

The Core is divided conceptually into:

```text
domain
application
infrastructure
interfaces
```

### Domain

Owns:

- entities,
- value concepts,
- state machines,
- invariants,
- domain rules.

Domain MUST NOT depend on HTTP, SQLite implementation details, or external UI.

### Application

Owns:

- use cases,
- orchestration,
- coordination of domain operations,
- transaction-level workflows.

### Infrastructure

Owns:

- SQLite,
- SQLAlchemy,
- Alembic,
- readers,
- external adapters,
- timer adapters,
- persistence implementations,
- future execution integrations.

### Interfaces

Owns:

- FastAPI/API boundary,
- external-facing input/output translation,
- Tauri-facing protocol concerns.

Dependency direction SHOULD point toward domain concepts rather than allowing infrastructure concerns to leak inward.

---

# 23. Technology Stack

## Desktop

- Tauri 2
- React
- TypeScript

## Core

- Python 3.12
- `asyncio`

## API

- FastAPI
- Uvicorn

## Validation

- Pydantic

## Persistence

- SQLite
- SQLAlchemy 2
- Alembic

## Tooling

- `uv`
- Ruff
- pytest
- pytest-asyncio

## Observability

- OpenTelemetry
- Python logging

## LLM Runtime

The LLM runtime is intentionally replaceable.

Possible future runtimes include:

- Ollama,
- llama.cpp,
- vLLM,
- other compatible local runtimes.

The Event subsystem MUST NOT require an LLM.

---

# 24. Explicitly Avoided Phase 1 Technologies

The current design intentionally does not introduce:

- Kafka,
- Redis,
- NATS,
- Temporal,
- PostgreSQL,
- Kubernetes,
- Docker-based distributed deployment,
- microservices,
- GraphQL,
- gRPC,
- external message brokers.

These are not forbidden forever.

They are excluded because Phase 1 does not require their complexity.

---

# 25. Phase Plan

This section is intentionally explicit so an implementation agent can determine **what to build now, what not to build now, and what completion means**.

## Phase 0 — System Design Baseline

### Goal

Freeze a coherent system model before implementation.

### Deliverables

- canonical system-design specification,
- architecture specification,
- database schema,
- domain model/state machines,
- event subsystem design,
- package architecture,
- technology decisions,
- requirements,
- invariants,
- acceptance criteria.

### Exit Criteria

No major subsystem is being implemented without an understood responsibility and boundary.

---

## Phase 1 — Event → Scheduling Foundation

### Goal

Build the durable input-to-scheduling pipeline and stop at the dispatch-intent boundary.

### Build

1. Core process skeleton.
2. SQLite database and migrations.
3. Event domain model.
4. Event Store.
5. Event Intake.
6. deduplication.
7. Event outbox.
8. Event routing.
9. consumer offsets.
10. Reader Manager.
11. Synthetic Event Reader.
12. Task model.
13. Trigger model.
14. Occurrence creation.
15. activation idempotency.
16. eligibility.
17. SchedulerWork.
18. Wake Scheduler.
19. Run Scheduler.
20. priority calculation.
21. bounded aging.
22. concurrency admission.
23. resource reservations.
24. atomic admission.
25. scheduler decision records.
26. crash recovery.
27. Dispatcher boundary / dispatch intent.

### Do Not Build

- real autonomous execution engine,
- sophisticated agent loop,
- distributed broker,
- distributed scheduler,
- Kubernetes,
- multi-user architecture,
- complex fair-share scheduler,
- preemptive scheduler,
- generic policy DSL,
- LLM-dependent Event processing.

### Recommended Reader Sequence

1. Synthetic Event Reader.
2. First real filesystem-oriented reader to exercise bursts, duplicates, and backpressure.

### Phase 1 Acceptance

The implementation must demonstrate:

```text
Event Reader
    ↓
Event Intake
    ↓
SQLite Event Store
    ↓
Outbox
    ↓
Router
    ↓
Trigger
    ↓
Task
    ↓
Occurrence
    ↓
Eligibility
    ↓
Wake / Run Scheduler
    ↓
Priority
    ↓
Resource Admission
    ↓
DISPATCH INTENT
```

And demonstrate:

- Event survives restart.
- Duplicate logical Events are rejected safely.
- Trigger replay does not create duplicate Occurrences.
- Scheduler state reconstructs after restart.
- Priority ordering works.
- Aging is bounded.
- Resource capacity is never exceeded.
- Blocked high-priority work does not unnecessarily prevent admissible work.
- Cancellation works.
- Expiration works.
- Scheduler decisions are explainable.
- Crash recovery is safe and repeatable.

### Phase 1 Definition of Done

The system can reliably transform an external or synthetic Event into a durable, idempotent, eligible Occurrence and schedule it through atomic resource admission to a durable dispatch intent, while surviving restart and preserving domain invariants.

---

## Phase 2 — Execution Foundation

### Goal

Introduce actual execution behind the Dispatcher boundary.

### Expected Areas

- execution abstraction,
- execution workers,
- process/resource lifecycle,
- execution result model,
- success/failure handling,
- retry behavior,
- timeout behavior,
- cooperative cancellation,
- reservation release,
- execution observability.

### Boundary

Phase 2 MUST preserve the Phase 1 distinction:

`DISPATCHED != COMPLETED`

Execution is responsible for producing execution outcomes.

---

## Phase 4 — Capability and Authorization Foundation

### Goal

Establish explicit capability, authorization, approval, and side-effect controls before Pinky is allowed to perform meaningful external actions autonomously.

### Expected Areas

- capability model,
- capability-to-operation mapping,
- authorization policy,
- durable approval state,
- execution permission checks,
- secret/credential references,
- external side-effect idempotency strategy,
- prompt-injection/untrusted-content boundary,
- execution audit records.

### Exit Criteria

No future execution path can obtain authority merely from:

- LLM output,
- Event content,
- Task text,
- execution class,
- scheduler admission.

External side effects have an explicit authorization boundary.

---

## Phase 5 — Local AI/LLM Capabilities

### Goal

Introduce replaceable local LLM capabilities.

### Expected Areas

- model runtime adapter,
- small/strong model resource identities,
- model selection,
- prompt/context construction,
- structured outputs,
- tool invocation,
- model failure handling,
- model resource accounting.

### Constraint

The LLM MUST remain a capability used by Pinky rather than becoming Pinky's runtime identity.

---

## Phase 5 — Interactive Agent

### Goal

Add user-facing conversational behavior.

### Expected Areas

- conversational input,
- intent interpretation,
- Task creation/update,
- user interaction,
- approval requests,
- execution requests,
- UI state,
- conversational context.

Interactive behavior MUST ultimately map onto the existing domain/runtime boundaries rather than bypassing the scheduler and safety model.

---

## Phase 6 — Autonomous Agent

### Goal

Enable autonomous background behavior.

### Expected Areas

- autonomous triggers,
- planning,
- background reasoning,
- goal decomposition,
- stronger LLM usage,
- autonomous Task generation,
- autonomous scheduling.

Autonomous behavior MUST still use the same Task → Occurrence → Eligibility → Scheduler → Admission → Dispatch architecture.

---

## Phase 7 — Advanced Intelligence

### Goal

Add advanced agent capabilities only after the runtime foundation is proven.

Potential areas:

- richer planning,
- long-running workflows,
- memory systems,
- context management,
- multi-step tool use,
- learned prioritization,
- advanced condition evaluation,
- richer approval workflows.

Each capability must be evaluated against existing domain boundaries before being added.

---

## Phase 8 — Hardening and Expansion

### Goal

Improve reliability, security, performance, and integration breadth.

Potential areas:

- additional event readers,
- additional execution adapters,
- performance optimization,
- stronger sandboxing,
- credential management,
- backup/export,
- advanced observability,
- migration tooling,
- optional distributed capabilities if future requirements justify them.

---

# 26. Architectural Invariants

These statements are non-negotiable unless the design is explicitly revised.

1. **Event ≠ Task**
2. **Task ≠ Occurrence**
3. **Occurrence ≠ SchedulerWork**
4. **SchedulerWork ≠ Execution**
5. **Admission ≠ Execution**
6. **Dispatch ≠ Completion**
7. **Authorization ≠ Approval ≠ Execution**
8. Event history is durable.
9. In-memory queues are not authoritative.
10. In-memory timers are not authoritative.
11. Scheduler state is separate from Task lifecycle.
12. Effective priority is derived.
13. Resource check + reservation + admission are atomic.
14. Consumer offsets advance only after successful processing.
15. Replay is expected and consumers must be replay-safe.
16. Activation is idempotent.
17. Stale reservations are recoverable.
18. Recovery is idempotent.
19. Readers do not own scheduling or execution.
20. The Event subsystem does not decide Task execution.
21. The Scheduler does not execute work.
22. The Dispatcher does not imply successful execution.
23. External execution MUST NOT occur while holding the database transaction used for admission.
24. The LLM is not the runtime identity of Pinky.
25. Untrusted data cannot grant authority.
26. LLM output cannot grant itself capabilities or approval.
27. External side effects require an explicit execution/capability boundary.

---

# 27. Error and Failure Semantics

The system MUST distinguish at least:

- invalid input,
- duplicate input,
- persistence failure,
- temporary infrastructure failure,
- eligibility failure,
- blocked resource,
- blocked concurrency,
- cancellation,
- expiration,
- dispatch failure,
- execution failure,
- recovery reconciliation.

A failure MUST NOT be represented as success merely because the system intends to retry.

Where behavior is not yet defined, mark it as UNSPECIFIED rather than inventing semantics.

---

# 28. Testing Strategy

## Unit Tests

Cover:

- domain validation,
- state transitions,
- normalization,
- deduplication,
- activation keys,
- priority calculation,
- aging,
- eligibility,
- backpressure policy,
- serialization.

## Persistence Tests

Cover:

- insertion,
- retrieval,
- uniqueness constraints,
- foreign keys,
- transactions,
- migrations,
- restart reconstruction,
- queries,
- reservation invariants.

## Integration Tests

Cover:

```text
Reader
 -> Intake
 -> Event Store
 -> Outbox
 -> Router
 -> Trigger
 -> Occurrence
 -> Scheduler
```

## Failure Tests

Inject failures during:

- Event persistence,
- routing,
- consumer processing,
- activation,
- admission,
- reservation creation,
- Core restart,
- recovery.

## Concurrency Tests

Verify:

- concurrent Event ingestion,
- concurrent deduplication,
- concurrent activation,
- concurrent scheduler decisions,
- resource capacity limits.

## Acceptance Tests

The Phase 1 acceptance suite must verify every Phase 1 exit criterion.

---

# 29. Decision Records and Explainability

Important decisions SHOULD be recorded with:

- what decision was made,
- when,
- for which SchedulerWork,
- effective priority,
- priority components,
- resource state,
- reason code,
- relevant details.

This is intended to make scheduler behavior inspectable without reconstructing it from logs alone.

---

# 30. What Is Not Yet Defined

The following areas should remain explicitly open until requirements are established:

- quantitative performance targets,
- exact user-facing UI behavior,
- detailed authentication/security architecture,
- credential vault implementation,
- execution sandbox design,
- exact LLM prompting strategy,
- long-term memory architecture,
- advanced planning architecture,
- multi-user behavior,
- remote/distributed operation,
- exact production packaging/distribution,
- backup/restore policy.

These are **not missing implementation tasks** for Phase 1. They are deferred design areas.

---

# 31. Implementation Rules for AI Coding Agents

Any AI agent implementing Pinky SHOULD follow this sequence:

1. Read this specification.
2. Read the detailed subsystem specification relevant to the requested change.
3. Identify the requirement(s) being implemented.
4. Identify affected domain invariants.
5. Identify affected state machines.
6. Identify persistence implications.
7. Identify concurrency implications.
8. Identify failure/recovery implications.
9. Implement the smallest change satisfying the requirement.
10. Add tests for normal behavior.
11. Add failure/concurrency tests where relevant.
12. Verify migrations and restart behavior where persistence changes.
13. Do not introduce new infrastructure without a requirement.
14. Do not move domain rules into UI/API layers.
15. Do not make in-memory state authoritative.
16. Do not collapse Event, Task, Occurrence, SchedulerWork, and Execution into one abstraction merely for convenience.
17. Do not introduce LLM dependencies into deterministic infrastructure.
18. Do not silently change architectural decisions.
19. If a requirement is genuinely unspecified, stop and mark it as a design decision rather than inventing behavior.
20. Update the relevant design documentation when an intentional architectural decision changes.

---

# 32. Definition of System-Design Complete

The system-design phase is complete enough for implementation when:

- requirements are explicit,
- constraints are explicit,
- domain entities are explicit,
- state machines are explicit,
- invariants are explicit,
- persistence ownership is explicit,
- concurrency semantics are explicit,
- failure/recovery behavior is explicit,
- subsystem boundaries are explicit,
- Phase 1 scope is explicit,
- Phase 1 exit criteria are testable,
- unresolved decisions are explicitly listed.

System design is **not** considered complete merely because a diagram exists.

---

# 33. Final Architectural Model

The intended Pinky flow is:

```text
SOURCE
  |
  v
READER
  |
  v
EVENT INTAKE
  |
  v
EVENT STORE
  |
  +--> OUTBOX --> ROUTER --> CONSUMERS
                              |
                              v
                           TRIGGER
                              |
                              v
                             TASK
                              |
                              v
                         OCCURRENCE
                              |
                              v
                         ELIGIBILITY
                              |
                              v
                       SCHEDULER WORK
                              |
                    +---------+---------+
                    |                   |
                    v                   v
             WAKE SCHEDULER      RUN SCHEDULER
                                        |
                                        v
                                    PRIORITY
                                        |
                                        v
                                     FAIRNESS
                                        |
                                        v
                                  CONCURRENCY
                                        |
                                        v
                              RESOURCE ADMISSION
                                        |
                                        v
                                   RESERVATION
                                        |
                                        v
                                    DISPATCH
                                        |
                                        v
                                  EXECUTION
                                        |
                                        v
                                     RESULT
```

The critical boundary for the initial implementation is:

```text
... -> RESOURCE ADMISSION -> DISPATCH INTENT
```

Execution begins only in the later execution phase.

---

# 34. Change Management

This document is versioned.

When a fundamental architectural assumption changes:

1. record the change,
2. identify affected requirements,
3. identify affected invariants,
4. identify affected schema/state machines,
5. identify affected tests,
6. update the phase plan,
7. update detailed subsystem specifications.

Avoid silently editing one subsystem document and leaving the canonical specification inconsistent.

---

# 35. Summary

Pinky is designed as a durable local runtime in which:

```text
Events describe facts.
Tasks describe responsibilities.
Triggers activate responsibilities.
Occurrences represent activations.
Eligibility determines whether work may run.
SchedulerWork represents schedulable competition.
Priority and fairness determine ordering.
Admission reserves scarce capacity.
Dispatch crosses into execution.
Execution produces outcomes.
Recovery reconstructs authoritative state.
Safety boundaries control authorization, approval, capabilities, and external side effects.
```

The architecture intentionally keeps these concepts separate so Pinky can evolve from a deterministic local runtime into an interactive and autonomous AI system without allowing the LLM, UI, scheduler, or execution engine to become an accidental monolith.
