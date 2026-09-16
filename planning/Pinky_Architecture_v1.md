# Pinky --- Canonical Architecture v1

**Status:** Design baseline for implementation\
**Scope:** Foundations → Event Subsystem → Task Subsystem → Scheduler\
**Implementation boundary:** Stop after Scheduler and validate Event →
Task → Occurrence → Scheduler before designing Execution.

------------------------------------------------------------------------

## 1. Purpose

Pinky is a **local, persistent, event-driven execution system** that can
use LLMs as reasoning resources.

The LLM is not the runtime. Pinky remains operational when no LLM is
active.

The core lifecycle is:

``` text
EVENT
  ↓
EVENT HANDLING
  ↓
TASK / OCCURRENCE
  ↓
ELIGIBILITY
  ↓
SCHEDULING
  ↓
ADMISSION
  ↓
DISPATCH
  ↓
EXECUTION
  ↓
RESULT EVENT
  ↓
EVENT STORE
```

Execution itself is outside the current implementation boundary.

------------------------------------------------------------------------

## 2. Architectural Principles

### 2.1 Event ≠ Task ≠ Execution

-   **Event:** something happened, became due, or changed.
-   **Task:** persistent responsibility/goal that may produce work.
-   **Occurrence:** one activation of a Task caused by a trigger/event.
-   **Execution:** one concrete attempt to perform an Occurrence.
-   **Attempt:** a retry/restart attempt within an Execution, where
    applicable.

Not every Event creates a Task.

Examples:

``` text
FILE_CHANGED      → may be ignored
TIMER_FIRED       → may create an Occurrence
USER_MESSAGE      → may create a Task
TOOL_COMPLETED    → may resume existing work
SYSTEM_STARTED    → may trigger recovery
```

### 2.2 Event infrastructure is durable; in-memory transport is not

SQLite is the durable source of truth.

An in-process queue is a transport/notification optimization.

``` text
SQLite Event Store = durable truth
asyncio.Queue      = fast in-process delivery
```

A crash must not cause an event that was already persisted to disappear.

### 2.3 Pinky owns domain scheduling semantics

The scheduler decides:

-   eligibility-to-run-now
-   priority
-   fairness/aging
-   resource admission
-   concurrency
-   backpressure
-   deadlines
-   dispatch eligibility

APScheduler, if used, is only a **Wake Scheduler/timer mechanism**. It
must not become the source of truth for Pinky's Task/Occurrence
scheduling state.

### 2.4 Deterministic does not mean trusted

Execution mode describes **how computation is performed**, not whether
an action is safe.

``` text
Capability authorization
        ≠
Human approval
        ≠
Execution
```

### 2.5 Phase 1 is single-machine and single-user

Initial deployment:

-   one machine
-   one user
-   one Pinky process
-   SQLite
-   asyncio

Interfaces should nevertheless avoid unnecessary assumptions that
prevent future worker processes.

------------------------------------------------------------------------

## 3. Execution Modes

Pinky has three sibling execution modes:

``` text
                    ACTIVE SYSTEM
                         │
             ┌───────────┼───────────┐
             ↓           ↓           ↓
       DETERMINISTIC INTERACTIVE AUTONOMOUS
```

### Deterministic

No LLM reasoning is required.

### Interactive

Human-facing work optimized for latency, conversation, intent
extraction, clarification, status, and task creation.

A smaller local model may be used.

### Autonomous

Background/task-facing reasoning and multi-step work.

A stronger model may be used.

The architecture must not hard-code:

``` text
human → small model
other → large model
```

Instead, execution mode is selected from task/event requirements and
policy. A small model may delegate to autonomous work; non-human events
may require deterministic handling; some background events may require
no LLM at all.

------------------------------------------------------------------------

## 4. Canonical Event Flow

``` text
External World
      │
      ▼
Event Sources
      │
      ▼
Event Readers
      │
      ▼
Event Intake
      │
      ▼
Event Store + Outbox
      │
      ├──────────────→ durable history
      │
      ▼
Event Router
      │
      ▼
Trigger Evaluation
      │
      ▼
Task / Occurrence creation
      │
      ▼
Eligibility
      │
      ▼
Scheduler
      │
      ▼
Dispatcher
      │
      ▼
Execution
      │
      ▼
Result / State Event
      │
      └──────────────→ Event Store
```

------------------------------------------------------------------------

## 5. Event Sources and Readers

An Event Source is anything capable of producing information relevant to
Pinky.

Examples:

-   human input
-   operating system
-   filesystem
-   applications
-   external services
-   devices
-   network
-   time
-   Pinky's own internal components

Readers adapt source-specific mechanisms into Pinky's canonical Event
format.

A reader may use:

-   push/listener APIs
-   OS callbacks
-   webhooks
-   sockets
-   polling
-   timers

Polling is a source implementation detail, not a special Event type.

### Reader Manager

The Reader Manager owns reader lifecycle.

Required properties:

-   isolated reader failures
-   restart policy
-   shutdown handling
-   reader health state
-   logging

A broken filesystem reader must not crash the entire Pinky runtime.

------------------------------------------------------------------------

## 6. Canonical Event

Every persisted Event should have, at minimum:

``` text
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

### occurred_at

When the source says the event happened.

### received_at

When Pinky accepted it.

Both are useful because source time and local receipt time can differ.

### causation_id

The immediate event/execution that caused this event.

### correlation_id

Groups events belonging to the same larger interaction/workflow.

Do not assume global ordering across all event sources.

If ordering matters, define ordering at the appropriate scope.

------------------------------------------------------------------------

## 7. Event Persistence and Delivery

The Event Store is the durable history.

The persist-before-publish rule is mandatory:

``` text
receive event
    ↓
validate
    ↓
BEGIN TRANSACTION
    ↓
insert event
insert outbox record
    ↓
COMMIT
    ↓
notify/publish
```

If Pinky crashes before publish, the persisted outbox entry remains
available for recovery.

These are different states:

1.  Event persisted.
2.  Event handed to an in-process router.
3.  Consumer successfully processed event.

An outbox alone does not guarantee that every consumer completed
processing.

For durable consumers, use a consumer cursor/offset or equivalent
durable acknowledgement.

``` text
consumer_offsets
    consumer_id
    last_processed_event_id
```

The in-memory queue can accelerate delivery, but replay from SQLite must
remain possible.

------------------------------------------------------------------------

## 8. Event Router, Trigger Engine, Eligibility Engine

These are separate responsibilities.

### Event Router

Answers:

> Which consumers should receive this event?

It performs routing only.

### Trigger Engine

Answers:

> Does this event activate any Task?

It may:

-   ignore the event
-   create an Occurrence for an existing Task
-   create a new Task when explicitly permitted
-   resume/continue an existing workflow
-   produce a deterministic action

### Eligibility Engine

Answers:

> Is this Occurrence logically allowed to become schedulable?

Examples:

-   Task is active.
-   Required trigger conditions are satisfied.
-   Dependencies are satisfied.
-   Occurrence is not cancelled.
-   Occurrence has not expired.

Eligibility must not decide resource capacity.

``` text
Eligibility:
    "May this work run?"

Scheduler:
    "Can this work run now?"
```

------------------------------------------------------------------------

## 9. Task Model

A Task represents persistent responsibility.

A Task should contain stable intent and policy, not transient scheduler
state.

Conceptually:

``` text
Task
├── task_id
├── name / description
├── goal
├── execution_mode
├── base_priority
├── trigger definition
├── eligibility policy
├── concurrency policy
├── deadline policy
├── backpressure policy
├── resource requirements
├── authorization policy
└── lifecycle state
```

Suggested Task lifecycle:

``` text
DRAFT
ACTIVE
PAUSED
CANCELLED
COMPLETED
```

Do not overload these values with meanings such as QUEUED or ADMITTED.

------------------------------------------------------------------------

## 10. Occurrence Model

An Occurrence is one activation of a Task.

An Occurrence should contain activation-specific information:

``` text
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

Suggested Occurrence lifecycle:

``` text
PENDING
ACTIVATED
COMPLETED
SKIPPED
CANCELLED
EXPIRED
```

Scheduler state must not be mixed into this lifecycle.

------------------------------------------------------------------------

## 11. Scheduler State Boundary

Scheduler state describes the relationship between an Occurrence and the
scheduling system.

Conceptually:

``` text
Occurrence
    │
    ▼
Schedulable Work
    │
    ├── WAITING
    ├── READY
    ├── QUEUED
    ├── ADMITTED
    └── DISPATCHED
```

These are not Task lifecycle states.

The scheduler-facing record may be implemented as a separate table or
equivalent persisted state associated with an Occurrence.

This boundary is mandatory because:

``` text
"Task is active"
```

and

``` text
"Task occurrence is currently waiting for a GPU"
```

are different facts.

------------------------------------------------------------------------

## 12. Wake Scheduler

The Wake Scheduler answers:

> When should Pinky reconsider something?

Examples:

-   exact timestamp
-   delay
-   interval
-   cron
-   deadline
-   retry time
-   timeout
-   scheduled condition evaluation

The canonical scheduling state remains in Pinky.

If APScheduler is used:

``` text
Pinky scheduling state
        ↓
APScheduler registration
        ↓
timer fires
        ↓
Pinky wake callback
        ↓
Pinky re-evaluates state
```

APScheduler must not own Pinky's priority/resource/admission decisions.

For Pinky, the recommended source-of-truth model is that Pinky owns
durable scheduling state and APScheduler, if used, acts as a timer
adapter.

------------------------------------------------------------------------

## 13. Run Scheduler

The Run Scheduler answers:

> Given all currently runnable work, what should be admitted next?

Decision pipeline:

``` text
WORK ARRIVES
     ↓
ELIGIBILITY
     ↓
PRIORITY
     ↓
QUEUE
     ↓
FAIRNESS / AGING
     ↓
RESOURCE ADMISSION
     ↓
DISPATCH
```

The scheduler should be deterministic for the same observable state.

------------------------------------------------------------------------

## 14. Priority Model

Base priority is Task policy.

Dynamic scheduling inputs belong to the Occurrence.

Recommended inputs:

``` text
base_priority
urgency
deadline_at
runnable_at
```

Effective priority is derived:

``` text
effective_priority =
    base_priority
    + urgency
    + deadline_pressure(deadline_at)
    + bounded_aging(now - runnable_at)
```

The exact numeric weights are configuration, not architecture.

### Aging

Aging exists to prevent indefinite starvation.

It should be bounded.

``` text
aging = min(max_aging, age_factor × waiting_time)
```

Do not let an old low-priority item acquire unlimited priority.

Do not make a persisted numeric effective priority the source of truth.

Persist the inputs and recalculate when scheduling decisions are made.

------------------------------------------------------------------------

## 15. Queue Topology

Pinky should use a logical unified scheduling model rather than
completely isolated resource pools.

Execution classes can be represented as lanes:

``` text
Interactive
Autonomous
Deterministic
```

but resources should remain shared unless explicitly configured
otherwise.

``` text
             Run Scheduler
                   │
        ┌──────────┼──────────┐
        ↓          ↓          ↓
 Interactive  Autonomous  Deterministic
        └──────────┼──────────┘
                   ↓
            Shared Resources
```

Lane caps can exist as safeguards, but they should not unnecessarily
prevent an otherwise admissible task from using idle capacity.

------------------------------------------------------------------------

## 16. Fairness

Phase 1 fairness is intentionally simple.

Implement:

-   priority
-   bounded aging
-   concurrency limits
-   resource admission
-   optional lane safeguards

Do not implement initially:

-   weighted fair-share accounting
-   per-user service guarantees
-   priority inheritance
-   complex queue scheduling algorithms

If real workload demonstrates starvation, expand the policy later.

------------------------------------------------------------------------

## 17. Resource Model

Resources represent scarce execution capacity.

Examples:

``` text
strong_llm
small_llm
gpu
browser
filesystem_worker
network_worker
```

A Task/Occurrence declares resource requirements.

The Scheduler must reserve resources before dispatch.

### Admission invariant

The critical operation is:

``` text
SELECT candidate
    ↓
CHECK resources
    ↓
RESERVE resources
    ↓
MARK ADMITTED
    ↓
COMMIT
    ↓
DISPATCH
```

The check + reservation + admission transition must be atomic.

For SQLite, this belongs inside a write transaction.

Never separate the check and reservation into independent commits,
because another scheduler decision could consume the capacity between
those operations.

------------------------------------------------------------------------

## 18. Concurrency

Concurrency constraints are policy.

Examples:

``` text
Task A:
    max_concurrent = 1

Interactive:
    max_concurrent = N

Autonomous:
    max_concurrent = M
```

Concurrency limits should distinguish:

-   logically eligible
-   runnable
-   admitted
-   executing

A task blocked only because its concurrency limit is reached is not
ineligible; it is waiting for scheduler capacity.

------------------------------------------------------------------------

## 19. Backpressure

Backpressure protects Pinky from event storms.

Examples:

``` text
1000 FILE_CHANGED
1000 TOOL_COMPLETED
1000 periodic events
```

Task policy should define what repeated activations mean.

Useful Phase 1 policies:

-   DROP
-   COALESCE
-   hard max_pending

Coalescing must be defined by Task semantics.

For example:

``` text
coalesce_key = file_path
strategy = latest
```

may mean multiple changes to the same file produce one pending
activation using the latest known state.

Do not assume every event type can safely be reduced to its latest
instance.

------------------------------------------------------------------------

## 20. Deadlines and Misfires

Deadlines belong to Occurrences.

The scheduler should distinguish:

-   no deadline
-   soft deadline
-   hard deadline
-   expired work

For temporal schedules, a misfire occurs when the scheduled time passes
without the expected activation/execution.

Phase 1 should implement a minimal policy set:

``` text
RUN
SKIP
```

More elaborate catch-up/coalescing policies can be added when real use
cases justify them.

------------------------------------------------------------------------

## 21. Preemption and Cancellation

Phase 1 scheduler policy:

> **Non-preemptive scheduling.**

Once admitted, an execution is not forcibly killed merely because a
higher-priority item appears.

A higher-priority item waits for capacity.

Cancellation should be cooperative:

``` text
cancel requested
      ↓
execution notified
      ↓
execution reaches safe cancellation point
      ↓
resources released
      ↓
state finalized
```

The Scheduler is responsible for deciding admission, not terminating
arbitrary work.

------------------------------------------------------------------------

## 22. Backfill

Phase 1 does not require a formal backfill planner.

If the highest-priority candidate is blocked by unavailable resources:

``` text
candidate A → GPU unavailable
candidate B → CPU only
candidate C → CPU only

try A
  blocked

try B
  admissible

admit B
```

This simple scan is sufficient.

Do not build reservation calendars or duration-prediction systems.

------------------------------------------------------------------------

## 23. Admission Decision Record

Every meaningful scheduler decision should be explainable.

A decision record should be able to answer:

``` text
Which occurrence?
What was its effective priority?
Why was it eligible?
What resources did it require?
What resources were available?
Why was it admitted/rejected/deferred?
What competing candidate was considered?
```

Conceptually:

``` text
decision_log
├── decision_id
├── occurrence_id
├── decision_type
├── timestamp
├── priority_snapshot
├── resource_snapshot
├── selected
└── reason / structured details
```

The decision log is diagnostic evidence, not domain state.

------------------------------------------------------------------------

## 24. Persistence and Recovery

Persistent state must survive a process crash.

At minimum, recovery must be able to reconstruct:

-   Events
-   Outbox records
-   Tasks
-   Occurrences
-   scheduler-facing work state
-   resource reservations
-   scheduling metadata
-   decision history

On startup:

``` text
load persistent state
      ↓
identify incomplete/stale scheduler state
      ↓
reconcile reservations
      ↓
rebuild in-memory indexes/queues
      ↓
restore wake timers
      ↓
resume scheduling
```

Never assume in-memory queue contents survived a crash.

------------------------------------------------------------------------

## 25. Resource Reservation Recovery

A reservation can become stale if Pinky crashes after reserving capacity
but before execution finishes.

Therefore reservations need enough metadata to determine whether they
belong to a live execution/scheduler state.

At startup:

``` text
reservation
   ↓
is owning work still valid/running?
   ├── yes → restore
   └── no  → release/reconcile
```

Do not allow stale reservations to permanently consume capacity.

------------------------------------------------------------------------

## 26. Idempotency

Any externally side-effecting operation may be retried after an
ambiguous failure.

Therefore idempotency must be based on the **logical operation**, not
the retry attempt.

Bad:

``` text
hash(tool, attempt_id, args)
```

because each retry has a new attempt ID.

Preferred conceptual identity:

``` text
execution_id
+
logical_step_id
+
tool
+
canonical_arguments
```

All retries of the same logical step share the same idempotency
identity.

The external system must support idempotency for this to provide full
protection; otherwise Pinky can only provide local
deduplication/recording.

------------------------------------------------------------------------

## 27. Safety Boundary

The architecture must distinguish:

### Authorization

May this Task use this capability?

### Approval

Does this particular action require explicit human confirmation?

### Execution

Perform the action.

This matters for:

-   deleting files
-   sending messages
-   external writes
-   financial actions
-   browser actions
-   other irreversible side effects

Execution mode does not determine safety.

------------------------------------------------------------------------

## 28. Configuration Resolution

Use layered configuration:

``` text
Global
   ↓
Execution class
   ↓
Task
   ↓
Occurrence
```

More specific configuration overrides less specific configuration.

Examples:

-   default scheduler tick
-   autonomous concurrency
-   Task-specific priority
-   Occurrence-specific deadline

The resolution mechanism should be explicit and deterministic.

Do not create a generic configuration DSL in Phase 1.

------------------------------------------------------------------------

## 29. SQLite

SQLite is the Phase 1 durable store.

Recommended properties:

-   WAL mode
-   foreign keys enabled
-   short transactions
-   explicit migrations
-   indexes on scheduler-critical queries
-   controlled write ownership

A single async writer task is a reasonable implementation strategy, but
it should not become a conceptual requirement that every future
component must route every write through one global queue.

Critical state transitions must still be atomic transactions.

------------------------------------------------------------------------

## 30. In-Process Bus

Use an in-process async queue/fan-out mechanism for fast delivery.

Its role:

``` text
"something changed in durable state;
wake interested components now"
```

It is not the persistence mechanism.

If the queue loses an item:

``` text
consumer must be able to recover by reading durable state
```

------------------------------------------------------------------------

## 31. Scheduler Main Loop

The conceptual Run Scheduler loop is:

``` text
while running:

    wait for:
        new runnable work
        resource change
        timer/wake signal
        cancellation
        recovery signal

    collect candidates

    remove stale/non-eligible candidates

    calculate effective priority

    order candidates

    for candidate in priority order:

        if concurrency unavailable:
            continue

        if resources unavailable:
            continue

        atomically:
            reserve resources
            mark scheduler state ADMITTED
            record decision

        dispatch/admit

        continue until:
            no candidate is admissible
            or capacity is exhausted
```

The actual implementation can be event-driven rather than a tight
polling loop.

------------------------------------------------------------------------

## 32. Scheduler Decision Order

The canonical decision order is:

``` text
1. Is the Occurrence valid?
2. Is the Task active?
3. Is the Occurrence eligible?
4. Is it runnable yet?
5. Has it expired?
6. Calculate effective priority.
7. Order candidates.
8. Check concurrency.
9. Check resources.
10. Atomically reserve/admit.
11. Emit decision record.
12. Hand admitted work to Dispatcher.
```

Resource availability must not silently mutate eligibility.

------------------------------------------------------------------------

## 33. Failure Semantics

A failure must be classified according to where it occurred.

Examples:

``` text
Reader failure
    → Reader Manager recovery

Event persistence failure
    → Event remains unaccepted

Router failure
    → durable event remains replayable

Trigger failure
    → event remains available for recovery/reprocessing

Scheduler failure
    → persistent scheduler state rebuilt on restart

Reservation failure
    → no admission

Dispatch failure
    → admitted work reconciled according to scheduler policy
```

Do not mark work complete merely because it was selected.

------------------------------------------------------------------------

## 34. What Phase 1--3 Must NOT Implement

Explicitly deferred:

-   Kafka
-   Redis
-   NATS
-   distributed locks
-   multi-node scheduling
-   Kubernetes-style scheduling
-   complex fair-share accounting
-   formal backfill planners
-   priority inheritance
-   resource deadlock graph analysis
-   predictive execution duration
-   reservation calendars
-   generic policy DSL
-   generalized workflow orchestration

The design should leave room for these later without implementing them
now.

------------------------------------------------------------------------

## 35. Recommended Phase Boundary

### Foundations

Implement:

-   project structure
-   configuration
-   SQLite
-   migrations
-   IDs
-   logging
-   startup/shutdown
-   supervision skeleton

### Event Subsystem

Implement:

-   Event schema
-   readers
-   Reader Manager
-   Event Intake
-   Event Store
-   Outbox
-   Router
-   durable consumer/recovery semantics

### Task Subsystem

Implement:

-   Task model
-   Occurrence model
-   Task Manager
-   Trigger Engine
-   Eligibility Engine
-   scheduler-facing work state

### Scheduler

Implement:

-   Wake Scheduler adapter
-   Run Scheduler
-   priority
-   bounded aging
-   deadlines
-   concurrency
-   resource accounting
-   atomic reservation/admission
-   simple backfill
-   cancellation semantics
-   backpressure limits
-   recovery
-   decision log
-   dispatcher boundary

Then STOP.

Do not implement the real Execution runtime yet.

------------------------------------------------------------------------

## 36. First End-to-End Milestone

Before Execution exists, Pinky should be able to demonstrate:

``` text
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
Trigger Engine
    ↓
Task
    ↓
Occurrence
    ↓
Eligibility
    ↓
Wake / Run Scheduler
    ↓
priority calculation
    ↓
resource admission
    ↓
DISPATCH INTENT
```

A test should prove:

1.  An Event is persisted.
2.  The Event survives restart.
3.  A trigger creates the correct Occurrence.
4.  Eligibility is evaluated correctly.
5.  Scheduler state is reconstructed after restart.
6.  Multiple Occurrences are ordered correctly.
7.  Aging changes ordering without becoming unbounded.
8.  Resource capacity is respected.
9.  Concurrent admission cannot over-reserve resources.
10. A blocked high-priority item does not prevent an admissible
    lower-priority item from running.
11. Cancellation/expiry are handled correctly.
12. Scheduler decisions are explainable from persisted records.
13. A crash does not permanently lose schedulable work.

------------------------------------------------------------------------

## 37. Canonical Architecture

``` text
                         PINKY
                           │
                 ┌─────────┴─────────┐
                 │                   │
            EVENT PLANE          WORK PLANE
                 │                   │
                 ▼                   ▼
          Event Sources            Tasks
                 │                   │
          Event Readers               │
                 │                   │
            Event Intake              │
                 │                   │
        Event Store + Outbox          │
                 │                   │
              Router                  │
                 │                   │
          Trigger Engine              │
                 │                   │
                 ▼                   ▼
             Occurrence ───────→ Eligibility
                                     │
                                     ▼
                               Wake Scheduler
                                     │
                                     ▼
                                Run Scheduler
                                     │
                         ┌───────────┴───────────┐
                         │                       │
                    Priority/Fairness       Resources
                         │                       │
                         └───────────┬───────────┘
                                     ▼
                                  Admission
                                     │
                                     ▼
                                 Dispatcher
                                     │
                                     ▼
                               [EXECUTION]
                                     │
                                     ▼
                                Result Event
                                     │
                                     └────→ Event Store
```

The central architectural invariant is:

> **Pinky is an event-driven persistent runtime. Events create or affect
> work; Tasks define responsibility; Occurrences represent activated
> work; the Scheduler decides when work may run; Execution performs
> it.**

------------------------------------------------------------------------

## 38. Decision Record

  Decision                                                 Status
  -------------------------------------------------------- ----------
  Event/Task/Occurrence/Execution separation               Fixed
  Three sibling execution modes                            Fixed
  SQLite as Phase 1 durable store                          Fixed
  In-process async transport                               Fixed
  Durable event store + outbox                             Fixed
  Durable consumer recovery/cursors                        Fixed
  Task lifecycle separate from scheduler state             Fixed
  Wake Scheduler separate from Run Scheduler               Fixed
  Pinky owns scheduling semantics                          Fixed
  APScheduler, if used, is Wake Scheduler implementation   Fixed
  Priority + bounded aging                                 Fixed
  Atomic resource reservation/admission                    Fixed
  Non-preemptive scheduling                                Fixed
  Simple backfill                                          Fixed
  Basic backpressure                                       Fixed
  Decision logging                                         Fixed
  Capability authorization separate from execution mode    Fixed
  Idempotency based on logical operation                   Fixed
  Full Execution runtime                                   Deferred
  Distributed infrastructure                               Deferred
  Complex fairness algorithms                              Deferred
  Priority inheritance                                     Deferred
  Formal backfill planner                                  Deferred

------------------------------------------------------------------------

## Implementation rule

If implementation pressure conflicts with these boundaries, do not
silently change the architecture.

Stop and update this document first.
