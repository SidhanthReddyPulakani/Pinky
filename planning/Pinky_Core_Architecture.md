Let's lock down the **Core package architecture and dependency rules** before creating the skeleton.

The goal here is not to create dozens of abstractions. It is to establish boundaries that prevent the Event, Task, and Scheduler systems from becoming coupled together.

# Pinky Core — Package Architecture v1

```text
apps/core/
│
├── src/
│   └── pinky_core/
│
│       ├── runtime/
│       ├── config/
│       ├── common/
│       │
│       ├── event/
│       ├── task/
│       ├── scheduler/
│       │
│       ├── persistence/
│       └── api/
│
└── tests/
```

The dependency direction should be:

```text
                    ┌──────────────┐
                    │   Runtime    │
                    └──────┬───────┘
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
          Event           Task       Scheduler
             │             │             │
             └─────────────┼─────────────┘
                           │
                           ▼
                    Persistence
                           │
                           ▼
                       SQLite
```

However, there's an important refinement:

**Event, Task, and Scheduler should not directly depend on persistence implementations.**

They depend on interfaces/contracts.

---

# 1. `common/`

This is deliberately tiny.

```text
common/
├── ids.py
├── errors.py
├── time.py
└── types.py
```

Potential responsibilities:

### `ids.py`

Common identifier types and generation.

For example:

```text
EventID
TaskID
OccurrenceID
SchedulerWorkID
ExecutionID
```

### `errors.py`

Core-level errors that cross subsystem boundaries.

For example:

```text
PinkyError
ValidationError
NotFoundError
ConflictError
StateTransitionError
```

### `time.py`

Time abstractions.

This becomes particularly important for the Scheduler because we don't want scheduler tests depending on the actual system clock.

### `types.py`

Only genuinely shared primitive/domain types.

**Rule:**

> If something belongs conceptually to Event, Task, or Scheduler, it does not go here merely because another subsystem needs it.

---

# 2. `event/`

The Event subsystem owns the **historical fact pipeline**.

```text
event/
├── models.py
├── intake.py
├── store.py
├── router.py
└── readers/
```

Conceptually:

```text
Reader
   ↓
Intake
   ↓
Validation / normalization
   ↓
Event Store
   ↓
Routing
```

### `readers/`

Source-specific event readers.

Eventually:

```text
readers/
├── filesystem.py
├── timer.py
├── application.py
├── device.py
└── ...
```

But **don't implement these now**.

### `models.py`

Event domain representation.

It includes the canonical fields from Database Schema v2, including:

```text
event_id
event_type
source
source_event_id
dedupe_key
occurred_at
received_at
payload
schema_version
```

### `intake.py`

Responsible for:

* accepting incoming events
* validation
* normalization
* assigning intake metadata
* deduplication decisions
* handing events to persistence

### `store.py`

The Event subsystem's persistence-facing abstraction.

Something like:

```text
EventStore
    append()
    get()
    exists()
```

The actual SQLite implementation should live underneath `persistence/`.

### `router.py`

Takes accepted Events and determines which application/domain subsystem should receive them.

It should **not execute Tasks**.

---

# 3. `task/`

Task owns **persistent intent and activation**.

```text
task/
├── models.py
├── service.py
├── triggers.py
├── dependencies.py
└── occurrences.py
```

The key relationship is:

```text
Task
 │
 ├── Trigger
 ├── Dependency
 │
 └── Occurrence
```

### `models.py`

Domain representations of:

```text
Task
Trigger
Dependency
Occurrence
```

### `service.py`

Task lifecycle operations.

For example:

```text
create_task()
update_task()
pause_task()
resume_task()
cancel_task()
```

### `triggers.py`

Determines how Events/temporal conditions activate Tasks.

Important distinction:

```text
Event
   ↓
Trigger matching
   ↓
Task activation
   ↓
Occurrence
```

A Trigger doesn't itself become an Event.

### `dependencies.py`

Handles Task dependency semantics.

### `occurrences.py`

Responsible for creating/managing concrete Occurrences.

This is important because:

```text
Task ≠ Occurrence
```

A recurring Task can produce many Occurrences.

---

# 4. `scheduler/`

This deserves the most strict boundary.

```text
scheduler/
├── models.py
├── eligibility.py
├── priority.py
├── fairness.py
├── resources.py
├── admission.py
├── dispatcher.py
└── scheduler.py
```

The Scheduler receives **schedulable work**.

It does not care where that work originated.

```text
Occurrence
    ↓
SchedulerWork
    ↓
Scheduler
```

### `models.py`

Scheduler-specific representations:

```text
SchedulerWork
Resource
Reservation
SchedulerDecision
```

### `eligibility.py`

Answers:

> Can this work be considered right now?

It handles things such as:

```text
activation state
dependencies
time constraints
conditions
cancellation
expiration
```

### `priority.py`

Computes effective priority.

Importantly:

```text
effective_priority
```

is **derived**, not the authoritative stored value.

### `fairness.py`

Prevents starvation.

This is where concepts like:

```text
aging
fairness adjustments
class quotas
```

eventually belong.

### `resources.py`

Defines resource availability and capacity.

For example:

```text
CPU
GPU
LLM slot
network
exclusive resource
```

The actual resource model can remain minimal in Phase 1.

### `admission.py`

The critical Scheduler boundary:

```text
candidate
   ↓
resource check
   ↓
reservation
   ↓
ADMITTED
```

### `dispatcher.py`

Takes admitted work and crosses into the Execution boundary.

For Phase 1, this should probably be an interface/stub.

```text
Scheduler
   ↓
Dispatcher
   ↓
[Execution — Phase 2]
```

### `scheduler.py`

The orchestrator.

It coordinates:

```text
Eligibility
Priority
Fairness
Resource Admission
Dispatch
```

It should **not implement all of those algorithms itself**.

---

# 5. `persistence/`

This is where we need to be disciplined.

```text
persistence/
├── database.py
├── models/
└── repositories/
```

### `database.py`

Owns:

```text
SQLite engine
connection/session management
transactions
database lifecycle
```

### `models/`

SQLAlchemy persistence models corresponding to Schema v2.

These are **database models**, not necessarily the same objects as domain models.

For example:

```text
EventDomainModel
        ↕
EventRepository
        ↕
EventORM
```

We don't necessarily need a separate object for every tiny structure, but the architectural boundary should exist.

### `repositories/`

For example:

```text
repositories/
├── event.py
├── task.py
├── occurrence.py
└── scheduler.py
```

The Event/Task/Scheduler services interact with repository interfaces rather than issuing SQL themselves.

---

# 6. `api/`

The API is the Core's external application boundary.

```text
api/
├── app.py
├── dependencies.py
└── routes/
    ├── events.py
    ├── tasks.py
    └── scheduler.py
```

The flow is:

```text
HTTP
 ↓
API route
 ↓
Application/domain service
 ↓
Repository
 ↓
SQLite
```

Never:

```text
HTTP
 ↓
SQLAlchemy
```

The API should expose **operations**, not database tables.

---

# 7. `config/`

```text
config/
├── settings.py
└── defaults.py
```

Configuration should cover things like:

```text
database path
API port
logging level
Core runtime options
development/test settings
```

Secrets should not be committed.

---

# 8. `runtime/`

This is the Core's bootstrap/orchestration layer.

```text
runtime/
├── app.py
├── lifecycle.py
└── health.py
```

Its responsibility is essentially:

```text
start
 ↓
load configuration
 ↓
initialize database
 ↓
initialize repositories
 ↓
initialize Event subsystem
 ↓
initialize Task subsystem
 ↓
initialize Scheduler
 ↓
start API
 ↓
ready
```

Runtime **wires components together**.

It should not contain Event or Scheduler business logic.

---

# Dependency Rules

These are more important than the folders.

## Rule 1 — Domain logic never imports FastAPI

Never:

```text
scheduler → api
task → api
event → api
```

API depends on the domain/application layer.

---

## Rule 2 — Domain logic never imports SQLAlchemy

Never:

```text
event → sqlalchemy
task → sqlalchemy
scheduler → sqlalchemy
```

Instead:

```text
domain
  ↓
repository interface
  ↓
persistence implementation
  ↓
SQLAlchemy
```

---

## Rule 3 — Event doesn't own Task

Event can **produce information that causes Task activation**, but:

```text
Event ≠ Task
```

The Event subsystem should not directly manipulate Task internals.

---

## Rule 4 — Task doesn't own Scheduler

Task creates Occurrences.

Scheduler consumes schedulable Occurrences.

```text
Task
 ↓
Occurrence
 ↓
Scheduler
```

---

## Rule 5 — Scheduler doesn't know about Event Readers

The Scheduler should never care whether something came from:

```text
filesystem
calendar
keyboard
timer
network
user
```

By the time work reaches Scheduler, its origin should be irrelevant to scheduling.

---

## Rule 6 — Scheduler doesn't invoke an LLM directly

Eventually:

```text
Scheduler
   ↓
Dispatcher
   ↓
Execution
   ↓
LLM / tool / process
```

The Scheduler decides **when and whether** work can run.

Execution decides **how** it runs.

---

# The resulting architecture

This gives us a very clean separation:

```text
                 ┌───────────────┐
                 │    Readers    │
                 └───────┬───────┘
                         ↓
                 ┌───────────────┐
                 │ Event Intake  │
                 └───────┬───────┘
                         ↓
                 ┌───────────────┐
                 │ Event Store   │
                 └───────┬───────┘
                         ↓
                 ┌───────────────┐
                 │ Event Router  │
                 └───────┬───────┘
                         ↓
                 ┌───────────────┐
                 │     Task      │
                 └───────┬───────┘
                         ↓
                 ┌───────────────┐
                 │  Occurrence   │
                 └───────┬───────┘
                         ↓
                 ┌───────────────┐
                 │ SchedulerWork │
                 └───────┬───────┘
                         ↓
             ┌────────────────────────┐
             │       Scheduler        │
             │                        │
             │ Eligibility             │
             │ Priority                │
             │ Fairness                │
             │ Admission               │
             └───────────┬────────────┘
                         ↓
                 ┌───────────────┐
                 │  Dispatcher   │
                 └───────┬───────┘
                         ↓
                  Execution Phase 2
```

And underneath:

```text
             Event / Task / Scheduler
                       │
                       ▼
                Repository APIs
                       │
                       ▼
                  Persistence
                       │
                       ▼
                    SQLite
```

## What we should do next

I would **not start implementing individual subsystems yet**.

Next we should turn this into a short **`Pinky_Core_Architecture_v1.md`** document and lock it down.

Then we can create the actual repository skeleton and make the first milestone:

> **Pinky Core boots successfully, initializes SQLite, exposes a health endpoint, and shuts down cleanly.**

Once that works, we have a real foundation to build the Event subsystem on rather than developing architecture and implementation simultaneously.
