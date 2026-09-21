# Pinky — Domain Model and State Machines v1

**Status:** Design specification  
**Depends on:** `Pinky_Architecture_v1.md`  
**Scope:** Domain objects, relationships, lifecycle/state machines, invariants, ownership, and transition rules  
**Implementation boundary:** This document defines the domain contract that the SQLite schema and subsystem interfaces will implement.

---

# 1. Purpose

This document turns the Pinky architecture into an explicit domain model.

The objective is to answer four questions before implementation:

1. **What entities exist?**
2. **What does each entity mean?**
3. **What states can each entity occupy?**
4. **Which subsystem is allowed to change those states?**

The central distinction remains:

```text
Event
    ↓ may trigger
Task
    ↓ may activate
Occurrence
    ↓ becomes schedulable
Scheduler Work
    ↓ may be admitted
Execution
```

Execution is not implemented in the current phase, but the domain model must leave a clean boundary for it.

---

# 2. Core Domain Concepts

Pinky contains several different kinds of state.

## 2.1 Historical facts

These describe things that happened.

```text
Event
DecisionRecord
```

They should generally be append-oriented and should not be treated as mutable workflow state.

## 2.2 Persistent intent

These describe what Pinky is responsible for doing.

```text
Task
```

A Task can live for a long time and can generate multiple Occurrences.

## 2.3 Activated work

These represent a particular activation of persistent responsibility.

```text
Occurrence
```

An Occurrence is not the Task itself.

## 2.4 Scheduling state

This describes the relationship between an Occurrence and the Scheduler.

```text
SchedulerWork
Reservation
```

Scheduling state is operational state and is therefore distinct from Task lifecycle.

## 2.5 Delivery state

This describes reliable delivery of persisted Events to internal consumers.

```text
OutboxEntry
ConsumerOffset
```

Delivery state must not redefine Event history.

## 2.6 Execution

Execution is the eventual concrete performance of an Occurrence.

It is intentionally outside the current implementation boundary.

---

# 3. Entity Overview

```text
                         EVENT
                           │
                 ┌─────────┴─────────┐
                 │                   │
          causation /          correlation
                 │                   │
                 ▼                   │
              TASK ◄────────────────┘
                 │
                 │ activation
                 ▼
            OCCURRENCE
                 │
                 ▼
          SCHEDULER WORK
                 │
                 ├──────────→ RESERVATION
                 │
                 ▼
             EXECUTION
                 │
                 ▼
            RESULT EVENT
```

Additional infrastructure:

```text
EVENT
  │
  └──→ OUTBOX ENTRY
          │
          ▼
       CONSUMER
          │
          └──→ CONSUMER OFFSET
```

---

# 4. Entity: Event

## 4.1 Meaning

An Event is a durable record that something:

- happened,
- became due,
- changed,
- was received,
- or was produced by Pinky's own runtime.

An Event is a **fact**, not an instruction to execute something.

An Event may cause work, but does not inherently require work.

## 4.2 Required fields

```text
event_id
event_type
source
occurred_at
received_at
payload
causation_id
correlation_id
schema_version
```

### Event Source and Deduplication Metadata

The Event model includes durable source-level identifiers used by Event Intake and Event Store for deduplication.

```text
source_event_id
dedupe_key

## 4.3 Event identity

`event_id` uniquely identifies the persisted Event.

An Event ID identifies a fact in Pinky's event history.

It must not be reused for a separate Event.

## 4.4 Event timestamps

```text
occurred_at
received_at
```

`occurred_at` represents source-reported event time.

`received_at` represents Pinky's local acceptance time.

They must not be conflated.

An event can therefore be:

```text
occurred_at < received_at
```

because a source may report something after it actually happened.

## 4.5 Event causation

`causation_id` identifies the immediate upstream object/event responsible for producing the Event when such a relationship exists.

Example:

```text
USER_MESSAGE
    ↓
Task creation
    ↓
TASK_CREATED event
```

The Task-created event can point to the originating user event as its cause.

## 4.6 Event correlation

`correlation_id` groups related events across a larger interaction.

Example:

```text
User request
   │
   ├── task created
   ├── occurrence activated
   ├── scheduler decision
   ├── execution
   └── result
```

All can share one correlation ID while having different immediate causes.

## 4.7 Event lifecycle

Events are historical facts.

They do not have a mutable business lifecycle such as:

```text
PENDING → RUNNING → COMPLETE
```

Instead, delivery/processing state belongs to consumers.

Conceptually:

```text
CREATED
   ↓
PERSISTED
   ↓
AVAILABLE FOR DELIVERY
```

After persistence, the Event remains historical even after every consumer has processed it.

## 4.8 Event invariants

1. `event_id` is immutable.
2. Event payload is immutable after persistence.
3. `occurred_at` is immutable.
4. `received_at` is immutable.
5. An Event can exist without creating a Task.
6. Delivery failure does not delete the Event.
7. Consumer processing state does not modify the Event itself.

---

# 5. Entity: Task

## 5.1 Meaning

A Task represents persistent responsibility, intent, and policy.

It answers:

> What does Pinky know it is responsible for doing?

A Task may be activated zero, one, or many times.

## 5.2 Task fields

Conceptually:

```text
task_id
name
description
goal
execution_mode

base_priority

trigger_definition
eligibility_policy

concurrency_policy
deadline_policy
backpressure_policy

resource_requirements
authorization_policy

lifecycle_state

created_at
updated_at
```

The exact representation of policy objects is a later schema/API decision.

## 5.3 Task identity

`task_id` identifies persistent responsibility.

It remains stable across Occurrences.

Example:

```text
Task #42
"Check my calendar every morning"
```

may produce:

```text
Occurrence #100
Occurrence #101
Occurrence #102
...
```

## 5.4 Task lifecycle

Canonical Phase 1 states:

```text
DRAFT
ACTIVE
PAUSED
CANCELLED
COMPLETED
```

### DRAFT

Task exists but is not active.

It cannot normally produce new runnable Occurrences.

### ACTIVE

Task is enabled and may be triggered.

### PAUSED

Task remains defined but does not currently activate/run new work according to normal trigger processing.

Existing work requires an explicit policy.

### CANCELLED

Task has been intentionally disabled permanently.

New Occurrences should not normally be created.

Existing work may require cancellation according to policy.

### COMPLETED

Task's responsibility has been fulfilled.

This is primarily useful for finite Tasks.

Recurring Tasks will normally remain `ACTIVE` until explicitly paused/cancelled.

## 5.5 Task transition authority

The Task Manager owns Task lifecycle transitions.

Other components may request a transition, but should not directly mutate Task lifecycle state.

```text
User / Trigger / System
        ↓
    Task Manager
        ↓
     Task state
```

## 5.6 Task transition graph

```text
             ┌──────────────┐
             │    DRAFT     │
             └──────┬───────┘
                    │ activate
                    ▼
             ┌──────────────┐
       ┌────→│    ACTIVE    │←────┐
       │     └───┬──────┬───┘     │
       │         │      │         │
     resume     pause  cancel    complete
       │         │      │         │
       │         ▼      ▼         ▼
       │     ┌───────┐ ┌────────────┐
       └─────│PAUSED │ │ CANCELLED │
             └───────┘ └────────────┘

                    ACTIVE
                      │
                      │ complete
                      ▼
                 COMPLETED
```

Allowed transitions should be explicitly enforced.

Suggested transition rules:

```text
DRAFT     → ACTIVE
ACTIVE    → PAUSED
ACTIVE    → CANCELLED
ACTIVE    → COMPLETED
PAUSED    → ACTIVE
PAUSED    → CANCELLED
DRAFT     → CANCELLED
```

Avoid arbitrary transitions such as:

```text
CANCELLED → ACTIVE
COMPLETED → ACTIVE
```

in Phase 1.

If restoration/reopening is required later, introduce explicit semantics rather than silently allowing reverse transitions.

## 5.7 Task invariants

1. `task_id` is immutable.
2. Task policy is distinct from scheduler state.
3. A Task can have many Occurrences.
4. A Task may exist without any Occurrence.
5. A paused/cancelled/completed Task must not silently create new normal activations.
6. Changing Task priority affects future scheduler decisions unless an Occurrence contains an explicit override.
7. Task lifecycle cannot be used to represent whether an individual Occurrence is queued or executing.

---

# 6. Entity: Occurrence

## 6.1 Meaning

An Occurrence represents **one activation of a Task**.

It answers:

> This particular instance of the Task has been activated; what should happen to this activation?

This distinction is central to Pinky.

## 6.2 Why Occurrence exists

Without Occurrence, recurring Tasks become ambiguous.

Example:

```text
Task:
    "Check calendar every morning"

Monday 08:00
    ↓
Occurrence A

Tuesday 08:00
    ↓
Occurrence B

Wednesday 08:00
    ↓
Occurrence C
```

The Task remains one persistent responsibility.

Each activation is a separate Occurrence.

## 6.3 Occurrence fields

Conceptually:

```text
occurrence_id
task_id
trigger_event_id

created_at
runnable_at
deadline_at

urgency

status

coalesce_key
metadata
```

Potential future fields:

```text
activation_sequence
parent_occurrence_id
```

These should only be introduced when required by concrete workflow semantics.

## 6.4 Occurrence identity

`occurrence_id` identifies one activation.

It must remain stable for the lifetime of the activation.

Retries of execution do not create a new Occurrence unless the semantics explicitly define the retry as a new activation.

## 6.5 Occurrence lifecycle

Canonical Phase 1 lifecycle:

```text
PENDING
ACTIVATED
COMPLETED
SKIPPED
CANCELLED
EXPIRED
```

### PENDING

The activation record exists but has not completed trigger activation processing.

### ACTIVATED

The Task activation has been accepted as a concrete Occurrence.

It may then become eligible/runnable.

### COMPLETED

The Occurrence's responsibility has completed successfully.

### SKIPPED

The activation was intentionally not performed.

Examples:

- misfire policy says skip,
- coalescing removes redundant work,
- policy explicitly suppresses the activation.

### CANCELLED

The activation was explicitly cancelled.

### EXPIRED

The Occurrence passed a hard validity/deadline boundary and can no longer run.

## 6.6 Occurrence lifecycle graph

```text
                 ┌─────────┐
                 │ PENDING │
                 └────┬────┘
                      │ activate
                      ▼
                 ┌───────────┐
                 │ ACTIVATED │
                 └─────┬─────┘
                       │
          ┌────────────┼─────────────┐
          │            │             │
       complete      cancel        expire
          │            │             │
          ▼            ▼             ▼
     COMPLETED     CANCELLED      EXPIRED

ACTIVATED
    │
    └── skip ───────────────→ SKIPPED
```

The exact point at which `SKIPPED`, `CANCELLED`, or `EXPIRED` becomes terminal must be enforced consistently.

## 6.7 Occurrence versus scheduler state

An Occurrence being `ACTIVATED` does **not** mean:

```text
queued
admitted
executing
```

Those are scheduler/execution concerns.

For example:

```text
Occurrence = ACTIVATED
SchedulerWork = READY
```

or:

```text
Occurrence = ACTIVATED
SchedulerWork = WAITING_FOR_RESOURCE
```

This separation is mandatory.

---

# 7. Entity: SchedulerWork

## 7.1 Meaning

SchedulerWork is the Scheduler's operational representation of an Occurrence.

It answers:

> What is the Scheduler currently doing with this activation?

It must not redefine the business meaning of the Occurrence.

## 7.2 Conceptual fields

```text
scheduler_work_id
occurrence_id

state

enqueued_at
admitted_at
dispatched_at

last_evaluated_at

priority_snapshot
```

The persisted representation may instead use derived state plus timestamps; the final schema should be chosen after the scheduler contract is finalized.

## 7.3 Scheduler states

Recommended conceptual states:

```text
WAITING
READY

ADMITTED
DISPATCHED
```

These describe scheduling progress, not Task lifecycle.

### WAITING

The Occurrence exists but is waiting for some scheduler-relevant condition.

Examples:

- `runnable_at` is in the future,
- dependency is unresolved,
- resource/concurrency condition prevents admission.

### READY

The Occurrence is eligible and runnable.

### 

The Scheduler has accepted the work into its active scheduling set.

### ADMITTED

The Scheduler has atomically reserved the required capacity and committed the work for dispatch.

### DISPATCHED

The work has been handed to the Dispatcher.

Execution then owns the execution lifecycle.

## 7.4 Important distinction

`` and `ADMITTED` must not be collapsed.

Example:

```text
READY
  ↓

  ↓
ADMITTED
```

A queued item does not necessarily own resources.

An admitted item does.

## 7.5 Scheduler state authority

Only the Scheduler should perform Scheduler state transitions.

Other subsystems may:

```text
create work
request cancellation
signal resource changes
```

but should not arbitrarily mutate Scheduler state.

---

# 8. Entity: Resource

## 8.1 Meaning

A Resource represents finite or constrained capacity required to perform work.

Examples:

```text
strong_llm
small_llm
gpu
browser
filesystem_worker
network_worker
```

## 8.2 Resource fields

Conceptually:

```text
resource_id
name
resource_type
capacity
available_capacity
policy
state
```

The exact distinction between static capacity and current availability should be resolved in the database design.

## 8.3 Resource invariant

At all times:

```text
reserved_capacity <= total_capacity
```

and:

```text
available_capacity =
    total_capacity - active_reserved_capacity
```

if availability is materialized.

If availability is derived instead, the same invariant must hold logically.

## 8.4 Resource identity

A Resource identifies a scheduling capability, not a specific physical execution object.

For example:

```text
strong_llm
capacity = 1
```

does not imply a particular model process.

The Execution layer can later map that resource to actual runtime infrastructure.

---

# 9. Entity: Reservation

## 9.1 Meaning

A Reservation represents capacity claimed by admitted work.

It exists because resource checking and resource ownership are separate concepts.

## 9.2 Fields

Conceptually:

```text
reservation_id
resource_id
occurrence_id

quantity

created_at
released_at

status
```

A later Execution design may attach the reservation to an Execution ID.

## 9.3 Reservation lifecycle

```text
ACTIVE
  ↓
RELEASED
```

Potential recovery state:

```text
STALE
```

but Phase 1 may instead reconcile stale active reservations directly during startup.

## 9.4 Reservation invariant

A Reservation must never cause total reserved quantity to exceed resource capacity.

## 9.5 Atomic admission invariant

The following must be one transactional operation:

```text
candidate selection
    +
resource check
    +
reservation creation
    +
scheduler admission
```

Another scheduler decision must not be able to interleave between these operations.

---

# 10. Entity: OutboxEntry

## 10.1 Meaning

An OutboxEntry guarantees that a persisted Event can later be delivered to internal consumers.

It is a delivery mechanism, not an Event.

## 10.2 Relationship

```text
Event
  │
  └──→ OutboxEntry
```

One Event may result in one or more delivery operations, depending on implementation.

## 10.3 Conceptual fields

```text
outbox_id
event_id

created_at
published_at

attempt_count
last_attempt_at

status
```

Potential states:

```text
PENDING
PUBLISHED
FAILED
```

The exact retry model belongs to the event delivery implementation.

## 10.4 Important invariant

Deleting an OutboxEntry must never delete its Event.

The Event remains the durable historical source.

---

# 11. Entity: ConsumerOffset

## 11.1 Meaning

A ConsumerOffset records durable progress for a consumer.

It answers:

> How far has this consumer processed the durable event stream?

## 11.2 Conceptual fields

```text
consumer_id
last_processed_event_id
updated_at
```

The final ordering/cursor mechanism must not assume that all consumers require identical ordering semantics.

## 11.3 Consumer processing rule

Conceptually:

```text
read Event
    ↓
process successfully
    ↓
advance consumer offset
```

The offset must not advance before the consumer has successfully completed the operation whose completion it represents.

## 11.4 Crash behavior

If Pinky crashes before the offset is committed:

```text
Event may be processed again
```

Therefore consumer operations must be idempotent or otherwise tolerate replay.

---

# 12. Entity: DecisionRecord

## 12.1 Meaning

A DecisionRecord explains an important Scheduler decision.

It is diagnostic evidence, not authoritative domain state.

## 12.2 Conceptual fields

```text
decision_id
occurrence_id

decision_type
timestamp

priority_snapshot
resource_snapshot

selected
reason
details
```

## 12.3 DecisionRecord invariant

Deleting diagnostic records must not change the actual Task, Occurrence, Scheduler, or Resource state.

The decision log explains state; it does not define it.

---

# 13. Entity Relationship Model

The core relationships are:

```text
EVENT
  │
  ├── may cause ──────────────→ TASK
  │
  ├── may activate ───────────→ OCCURRENCE
  │
  └── may cause ──────────────→ EVENT


TASK
  │
  └── 1:N ────────────────────→ OCCURRENCE


OCCURRENCE
  │
  └── 1:1 ────────────────────→ SCHEDULER_WORK


SCHEDULER_WORK
  │
  └── 0:N ────────────────────→ RESERVATION


RESOURCE
  │
  └── 1:N ────────────────────→ RESERVATION


EVENT
  │
  └── 1:N / delivery ─────────→ OUTBOX_ENTRY


CONSUMER
  │
  └── 1:1 ────────────────────→ CONSUMER_OFFSET


OCCURRENCE
  │
  └── 1:N ────────────────────→ DECISION_RECORD
```

The exact cardinality of OutboxEntry depends on whether the implementation uses one outbox record per Event or per delivery target.

---

# 14. Ownership Model

Every mutable domain state should have one primary owner.

```text
EVENT
    Owner: Event Store / Event Intake

TASK
    Owner: Task Manager

OCCURRENCE
    Owner: Trigger/Task subsystem

SCHEDULER WORK
    Owner: Scheduler

RESOURCE
    Owner: Resource Manager / Scheduler

RESERVATION
    Owner: Scheduler

OUTBOX
    Owner: Event Store + Outbox publisher

CONSUMER OFFSET
    Owner: Consumer

DECISION RECORD
    Owner: Scheduler
```

This is an architectural rule.

A component should not directly modify another subsystem's state merely because it has access to the database.

Prefer:

```text
request
  ↓
owning subsystem
  ↓
validated transition
```

rather than:

```text
any component
  ↓
UPDATE database row
```

---

# 15. State Separation

Pinky has at least four distinct state dimensions.

## 15.1 Task state

```text
DRAFT
ACTIVE
PAUSED
CANCELLED
COMPLETED
```

## 15.2 Occurrence state

```text
PENDING
ACTIVATED
COMPLETED
SKIPPED
CANCELLED
EXPIRED
```

## 15.3 Scheduler state

```text
WAITING
READY

ADMITTED
DISPATCHED
```

## 15.4 Resource reservation state

```text
ACTIVE
RELEASED
```

These must not be collapsed into one universal status field.

A legitimate combination can be:

```text
Task:
    ACTIVE

Occurrence:
    ACTIVATED

Scheduler:
    WAITING

Reservation:
    none
```

Another:

```text
Task:
    ACTIVE

Occurrence:
    ACTIVATED

Scheduler:
    ADMITTED

Reservation:
    ACTIVE
```

The state dimensions answer different questions.

---

# 16. Cross-State Invariants

These are more important than individual state names.

## Invariant 1 — Task ownership

Every Occurrence must reference exactly one existing Task.

```text
occurrence.task_id → tasks.task_id
```

## Invariant 2 — Occurrence activation

A normal schedulable Occurrence must be `ACTIVATED`.

## Invariant 3 — Cancelled Task

A `CANCELLED` Task must not create new normal Occurrences.

Existing Occurrences require explicit cancellation policy.

## Invariant 4 — Completed Task

A `COMPLETED` Task must not create new normal recurring activations.

## Invariant 5 — Scheduler ownership

Only the Scheduler changes Scheduler state.

## Invariant 6 — Resource ownership

A Reservation must reference an existing Resource and an owning work item.

## Invariant 7 — Capacity

At no point may:

```text
sum(active reservations)
>
resource capacity
```

## Invariant 8 — Admission

A Scheduler Work item cannot become `ADMITTED` without successful resource/concurrency admission according to policy.

## Invariant 9 — Reservation release

Released capacity must become available to future Scheduler decisions.

## Invariant 10 — Historical Event

An Event must not be deleted simply because all consumers have processed it.

## Invariant 11 — Consumer replay

Consumer processing must tolerate replay when the offset was not committed before a crash.

## Invariant 12 — Execution boundary

`DISPATCHED` means work was handed to the Dispatcher.

It does not mean execution succeeded.

## Invariant 13 — Completion

Scheduler selection/admission cannot mark an Occurrence `COMPLETED`.

Completion requires the downstream execution/result lifecycle.

## Invariant 14 — Cancellation

Cancellation of a Task/Occurrence must not silently leave resources permanently reserved.

## Invariant 15 — Expiration

An expired Occurrence cannot later become runnable without an explicit new activation.

---

# 17. Trigger-to-Occurrence Contract

The Trigger Engine consumes Events and determines whether a Task should be activated.

Conceptually:

```text
Event
  ↓
Trigger matching
  ↓
Task selection
  ↓
Activation policy
  ↓
Occurrence creation
```

The Trigger Engine must answer:

```text
Which Task?
Should it activate?
How many Occurrences?
With what runnable_at?
With what deadline?
With what urgency?
With what coalesce semantics?
```

The Trigger Engine must not perform Scheduler admission.

---

# 18. Eligibility Contract

Eligibility evaluates logical conditions.

Input:

```text
Task
Occurrence
current time
dependencies
policy
```

Output:

```text
eligible / ineligible
```

Eligibility must not inspect resource availability as if resource shortage were a logical invalidity.

Example:

```text
GPU unavailable
```

does not mean:

```text
Occurrence is ineligible
```

It means:

```text
Occurrence is eligible
Scheduler cannot currently admit it
```

---

# 19. Scheduler Contract

The Scheduler consumes eligible/runnable work.

Conceptually:

```text
Occurrence
   ↓
Eligibility
   ↓
Scheduler Work
   ↓
Priority calculation
   ↓
Candidate ordering
   ↓
Concurrency check
   ↓
Resource check
   ↓
Atomic reservation + admission
   ↓
Dispatch
```

The Scheduler owns:

- queue state
- effective priority calculation
- aging
- concurrency admission
- resource admission
- backpressure enforcement
- dispatch eligibility
- scheduling recovery

The Scheduler does not own:

- Task business meaning
- Event history
- LLM reasoning
- actual execution

---

# 20. Wake Scheduler Contract

The Wake Scheduler is concerned with time.

It produces a signal:

```text
"reconsider this work now"
```

It does not directly decide:

```text
"run this task"
```

A wake event causes the Run Scheduler to reevaluate durable state.

Conceptually:

```text
wake timer
    ↓
scheduler wake signal
    ↓
read durable state
    ↓
eligibility / priority / admission
```

This ensures that timer state and scheduling authority remain separate.

---

# 21. Cancellation Model

Cancellation has two levels.

## 21.1 Cancellation request

A request to cancel:

```text
Task
Occurrence
or future work
```

## 21.2 Actual cancellation transition

The owning subsystem performs the validated state transition.

For already-dispatched work:

```text
cancel request
    ↓
Execution notified
    ↓
cooperative cancellation
    ↓
resource release
    ↓
final state
```

The Scheduler must not assume that a cancellation request means execution stopped immediately.

---

# 22. Completion Model

Completion must originate from the execution/result side.

Conceptually:

```text
Occurrence
    ↓
Scheduler
    ↓
Dispatch
    ↓
Execution
    ↓
Result
    ↓
Result Event
    ↓
Task/Occurrence state update
```

This prevents:

```text
Scheduler selected work
    =
work completed
```

which is incorrect.

---

# 23. Recovery Model

Recovery must reconstruct operational state from durable facts.

Startup sequence:

```text
Pinky starts
    ↓
load Tasks
    ↓
load Occurrences
    ↓
load Scheduler Work
    ↓
load Resources
    ↓
load Reservations
    ↓
identify stale/incomplete state
    ↓
reconcile
    ↓
rebuild in-memory indexes
    ↓
restore wake timers
    ↓
resume scheduling
```

The recovery process must be idempotent.

Running recovery twice should not create duplicate work or duplicate resource reservations.

---

# 24. Crash Scenarios

## Scenario A — Crash before Event commit

```text
source
  ↓
Event Intake
  ↓
CRASH
```

Result:

```text
Event was never accepted.
```

The source must retry if its delivery semantics require guaranteed delivery.

## Scenario B — Crash after Event + Outbox commit

```text
Event
  ↓
SQLite commit
  ↓
CRASH
```

Result:

```text
Event survives.
Outbox survives.
Publisher resumes later.
```

## Scenario C — Crash after consumer processing but before offset commit

```text
process event
  ↓
CRASH
  ↓
offset not committed
```

Result:

```text
event may be processed again
```

Therefore consumer handling must tolerate replay.

## Scenario D — Crash after resource reservation

```text
reserve
  ↓
CRASH
```

Startup recovery must detect and reconcile the reservation.

## Scenario E — Crash after dispatch

This is intentionally deferred to the Execution design.

The domain model must eventually distinguish:

```text
dispatch accepted
```

from:

```text
execution actually started
```

and:

```text
execution completed
```

---

# 25. Ordering Model

Pinky must not assume one universal chronological ordering of all Events.

Different sources can produce events concurrently.

Instead, ordering should be defined where required.

Examples:

```text
Events from one source:
    source-local ordering

Occurrences for one Task:
    activation ordering

Scheduler decisions:
    decision timestamp / sequence

Causality:
    causation_id
```

If strict ordering becomes necessary, an explicit sequence mechanism should be introduced rather than relying on timestamps.

---

# 26. Idempotency Boundaries

Idempotency is required at boundaries where retries can occur.

Important boundaries:

```text
Event ingestion
Trigger processing
Occurrence creation
Consumer processing
Scheduler admission
Dispatch
External side effects
```

The exact idempotency keys belong to the implementation contracts.

The key principle is:

> Retry identity must represent the logical operation, not the attempt.

---

# 27. Database Implications

The domain model implies at least the following logical tables:

```text
events
outbox
consumer_offsets

tasks
occurrences

scheduler_work

resources
reservations

scheduler_decisions
```

Potential additional tables should not be introduced until a concrete requirement demands them.

The next schema design must determine:

- primary keys
- foreign keys
- unique constraints
- indexes
- transaction boundaries
- state constraints
- JSON fields
- timestamps
- retention strategy

---

# 28. What Is Intentionally Not Defined Yet

The following are deliberately deferred:

- Execution schema
- Execution lifecycle
- Retry/attempt schema
- Tool invocation model
- LLM session model
- model routing implementation
- worker process architecture
- distributed scheduling
- advanced workflow graphs
- complex fairness algorithms
- formal resource dependency graphs
- advanced misfire strategies

This document should not silently absorb Execution architecture merely because Scheduler needs a clean boundary.

---

# 29. Canonical State Summary

```text
TASK
────────────────────────────────────────
DRAFT → ACTIVE → PAUSED → ACTIVE
           │
           ├────────→ CANCELLED
           │
           └────────→ COMPLETED


OCCURRENCE
────────────────────────────────────────
PENDING → ACTIVATED
              │
              ├────→ COMPLETED
              ├────→ SKIPPED
              ├────→ CANCELLED
              └────→ EXPIRED


SCHEDULER WORK
────────────────────────────────────────
WAITING → READY →  → ADMITTED → DISPATCHED


RESERVATION
────────────────────────────────────────
ACTIVE → RELEASED


EVENT
────────────────────────────────────────
PERSISTED → DELIVERED/REPLAYABLE
```

These state machines are intentionally separate.

---

# 30. Canonical Ownership Summary

```text
Event Store
    → Event history

Task Manager
    → Task lifecycle

Trigger Engine
    → Task activation / Occurrence creation

Eligibility Engine
    → logical schedulability

Scheduler
    → scheduling state + admission

Resource Manager / Scheduler
    → resource capacity

Dispatcher
    → dispatch boundary

Execution
    → actual work and result

Consumer
    → delivery progress

Decision Log
    → scheduling explanation
```

---

# 31. Design Rules

The following rules should be treated as hard architectural constraints for Phase 1:

1. Never use Event as a substitute for Task.
2. Never use Task as a substitute for Occurrence.
3. Never use Occurrence status as Scheduler state.
4. Never use Scheduler state as execution state.
5. Never infer completion from admission.
6. Never infer authorization from execution mode.
7. Never treat in-memory queues as durable state.
8. Never make APScheduler the source of truth for domain scheduling.
9. Never separate resource checking from resource reservation when admitting work.
10. Never allow stale reservations to survive recovery indefinitely.
11. Never advance a consumer cursor before the represented processing has succeeded.
12. Never make a diagnostic decision record authoritative over actual state.
13. Never assume global event ordering without an explicit ordering contract.
14. Never silently add distributed infrastructure during Phase 1.
15. Never add Execution-specific abstractions before the Scheduler boundary has been validated.

---

# 32. Readiness for Database Design

The domain model is considered ready to feed the SQLite design when these questions have explicit answers:

```text
✓ What is an Event?
✓ What is a Task?
✓ What is an Occurrence?
✓ What is Scheduler Work?
✓ What is a Resource?
✓ What is a Reservation?
✓ What is an Outbox Entry?
✓ What is a Consumer Offset?
✓ What is a Decision Record?

✓ What state does each entity own?
✓ Who may change each state?
✓ What transitions are allowed?
✓ What invariants cross entity boundaries?
✓ What survives a crash?
✓ What can be replayed?
✓ What must be idempotent?
✓ Where must transactions be atomic?
```

The next design artifact should therefore be:

**`Pinky_Database_Schema_v1.md`**

That document should derive the SQLite schema from this domain model rather than introducing new domain concepts.
