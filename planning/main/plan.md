Yes. I looked at the repository and the canonical design now present there. The repo is still essentially at the planning/foundation stage, and `apps/core` is already set up as a Python 3.12 project with the `src/pinky_core` layout and the basic FastAPI/SQLAlchemy/Alembic stack.

I would build Pinky in a very deliberate order. The biggest mistake would be to start with `Task`, then jump to the scheduler, then retrofit persistence, because the scheduler and recovery semantics depend on the database model and domain contracts underneath it.

## The implementation order I'd use

Think of the project as a sequence of **vertical foundations**:

```text
0. Repository / tooling
        ↓
1. Core runtime foundation
        ↓
2. Persistence foundation
        ↓
3. Common domain primitives
        ↓
4. Event domain + persistence
        ↓
5. Event intake
        ↓
6. Event delivery/replay
        ↓
7. Task domain
        ↓
8. Trigger + Occurrence
        ↓
9. Eligibility
        ↓
10. SchedulerWork
        ↓
11. Priority / fairness
        ↓
12. Resources / reservations
        ↓
13. Scheduler
        ↓
14. Recovery
        ↓
15. API integration
        ↓
16. Phase 1 end-to-end validation
        ↓
STOP
```

That order is based on the architecture in the repo: Event → Task → Occurrence → SchedulerWork → Admission → Dispatch, with SQLite as durable truth and execution deliberately outside the current boundary.

---

# Phase 0 — Freeze the implementation baseline

Before writing domain code, make the repository itself predictable.

### Step 0.1 — Fix the Python packaging

You've already got the important part in `apps/core/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

So keep the `src/` layout and always develop through:

```powershell
uv run ...
```

The package is named `pinky-core`, Python 3.12 is required, and the current dev dependencies include pytest, pytest-asyncio and Ruff.

### Step 0.2 — Establish test/lint commands

These should work before we proceed:

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Then add CI so a bad architectural change doesn't quietly land.

### Step 0.3 — Establish package structure

I'd create:

```text
apps/core/src/pinky_core/
├── common/
├── config/
├── runtime/
├── event/
├── task/
├── scheduler/
├── persistence/
└── api/
```

This matches the package architecture you've already designed.

---

# Phase 1 — Core runtime foundation

Don't start with Events yet.

First make the application capable of **starting and stopping correctly**.

## Models to implement first

Not domain models yet.

Implement these infrastructure concepts first:

```text
Settings
Runtime
Lifecycle
Health
Clock
ID generation
Error hierarchy
```

### 1. `common/ids.py`

Create strong-ish aliases/types for:

```text
EventID
TaskID
TriggerID
OccurrenceID
SchedulerWorkID
ResourceID
ReservationID
DecisionID
```

The exact runtime representation can remain UUID-backed.

Why first?

Because these IDs appear everywhere.

---

### 2. `common/time.py`

This is more important than it looks.

Create a clock abstraction:

```python
class Clock(Protocol):
    def now(self) -> datetime: ...
```

and a production implementation plus fake/test clock.

The scheduler absolutely should not call:

```python
datetime.now(...)
```

everywhere.

You want tests like:

```text
clock = FakeClock("2026-09-17T10:00Z")
```

then advance time deterministically.

Your architecture explicitly called out time abstraction because scheduler tests must not depend on wall-clock behavior.

---

### 3. `common/errors.py`

Create only the errors that actually cross subsystem boundaries:

```text
PinkyError
ValidationError
NotFoundError
ConflictError
StateTransitionError
PersistenceError
```

Don't create 70 custom exception classes.

---

### 4. `runtime/`

Implement:

```text
Runtime
Lifecycle
Health
```

The runtime should:

```text
load config
→ initialize dependencies
→ initialize DB
→ start subsystems
→ serve
→ shutdown cleanly
```

Your current architecture explicitly puts bootstrap/orchestration here rather than business logic.

### Exit condition

You should be able to start Core and get:

```text
READY
```

and shut it down without leaked tasks.

---

# Phase 2 — Persistence foundation

Now build the database infrastructure **before** Event/Task implementations.

This is one of the most important ordering decisions.

## Implement:

```text
Database
Session/transaction management
Alembic
Base ORM model
Repository base patterns
```

### 2.1 SQLite setup

Configure:

* WAL
* foreign keys
* short transactions

The database design explicitly makes SQLite the durable source of truth rather than a cache.

### 2.2 Alembic

Create the initial migration structure.

Do not manually create tables at runtime.

### 2.3 Transaction abstraction

You need a clean way to say:

```python
async with db.transaction():
    ...
```

The details can change, but the architectural concept must exist.

### 2.4 ORM separation

Keep:

```text
Domain model
    ↕
Repository
    ↕
SQLAlchemy model
```

rather than making Pydantic models double as database records.

That's consistent with your package architecture.

---

# Phase 3 — Event domain model

Now implement Event properly.

You actually already have the beginning of this in the repo.

`apps/core/src/pinky_core/event/models.py` currently defines `IncomingEvent` and immutable `Event`, including:

* `event_id`
* `event_type`
* `source`
* `source_event_id`
* `dedupe_key`
* `occurred_at`
* `received_at`
* `payload`
* `schema_version`

and normalizes timestamps to UTC.

That's a good start.

## But I'd refine it before proceeding

The canonical database/domain design also includes:

```text
metadata
causation_id
correlation_id
```

so the Event domain model must eventually align with that canonical contract.

### Tests first

Before Event persistence, write:

```text
test_event_requires_timezone
test_event_normalizes_to_utc
test_event_is_immutable
test_event_id_generated
test_incoming_event_can_be_converted_to_event
test_optional_source_identity
```

Then implement the persistence model.

---

# Phase 4 — Event Store

Now implement:

```text
event/store.py
persistence/models/event.py
persistence/repositories/event.py
```

Start with the simplest useful repository contract:

```text
append(event)
get(event_id)
exists(...)
query(...)
```

This matches the architecture and database specification.

## Database features to implement now

The `events` table needs:

```text
event_seq
event_id
event_type
source
occurred_at
received_at
payload
metadata
causation_id
correlation_id
source_event_id
dedupe_key
schema_version
```

plus:

```text
UNIQUE(event_id)
```

and partial unique indexes for source identity / dedupe identity where supplied.

### Critical tests

Test these before doing anything higher-level:

```text
insert event
read event
event survives new DB session
duplicate event_id rejected
duplicate (source, source_event_id) rejected
duplicate (source, dedupe_key) rejected
event_seq is assigned
payload remains immutable
```

---

# Phase 5 — Event Intake

Now implement:

```text
event/intake.py
```

The pipeline should become:

```text
IncomingEvent
    ↓
validate
    ↓
normalize
    ↓
derive/check identity
    ↓
persist
    ↓
result
```

with:

```text
ACCEPTED
DUPLICATE
REJECTED
```

Your architecture explicitly says the database uniqueness constraint is the final deduplication authority.

So don't write:

```python
if await repo.exists(...):
    return DUPLICATE
await repo.insert(...)
```

and consider the job done.

That creates a race.

You can do the lookup as an optimization, but the database constraint must resolve concurrent collisions.

### Write the concurrency test now

Two coroutines submit the same logical event simultaneously.

Expected:

```text
one ACCEPTED
one DUPLICATE
one stored event
```

That is an important foundational test.

---

# Phase 6 — Outbox + event delivery

Once Event persistence is solid, add:

```text
outbox
consumer_offsets
router
```

## Implement in this order

### 6.1 Outbox database model

Then:

### 6.2 Event append transaction

Make:

```text
insert Event
+
insert OutboxEntry
```

one transaction.

The architecture explicitly requires persist-before-publish semantics.

Then:

### 6.3 Outbox publisher

It can initially be extremely simple.

You do not need a broker.

### 6.4 Consumer offsets

Implement:

```text
consumer_id
last_processed_event_seq
updated_at
```

and the processing rule:

```text
process
→ commit consumer state
→ advance offset
```

Replay after crash must be expected.

### 6.5 Router

Only routing.

Do not let the Router start creating arbitrary scheduler work.

---

# Phase 7 — Reader framework

Now build the Reader abstraction.

Start with exactly one:

```text
SyntheticEventReader
```

The architecture explicitly recommends this as the deterministic first reader.

You need:

```text
Reader
ReaderManager
ReaderLifecycle
```

Reader manager owns:

* startup,
* shutdown,
* health,
* restart policy,
* fault isolation.

Reader itself owns:

* source interaction,
* parsing,
* source checkpointing.

It does **not** own persistence, Tasks, Scheduler, or LLM calls.

### First end-to-end milestone

At this point you should be able to:

```text
SyntheticEventReader
      ↓
EventIntake
      ↓
SQLite Event Store
      ↓
Outbox
```

and restart the Core without losing the Event.

Do this before Task implementation.

---

# Phase 8 — Task domain

Now finally implement the Task model.

This is the first real "responsibility" model.

## Models

Implement in this order:

### 8.1 Task

Fields:

```text
task_id
name
description
goal
execution_mode
base_priority
eligibility_policy
concurrency_policy
deadline_policy
backpressure_policy
resource_requirements
authorization_policy
lifecycle_state
timestamps
```

This aligns with the database and domain design.

### 8.2 Task lifecycle

Implement state transition methods, not arbitrary assignments:

```python
task.activate()
task.pause()
task.resume()
task.cancel()
task.complete()
```

Then tests for every allowed/disallowed transition.

### 8.3 Task service

Only after the entity/state machine works.

```text
create_task
update_task
activate_task
pause_task
resume_task
cancel_task
complete_task
```

---

# Phase 9 — Trigger

Next implement the trigger model.

Do not put trigger logic into Task itself.

Implement:

```text
Trigger
TriggerType
TriggerMatcher
```

Types:

```text
SCHEDULE
EVENT
CONDITION
MANUAL
```

The database already models these independently in `task_triggers`.

---

# Phase 10 — Occurrence

This should be the next model after Trigger.

Implement:

```text
Occurrence
OccurrenceStatus
OccurrenceService
```

The key concept:

```text
Task = responsibility
Occurrence = one activation
```

The architecture explicitly makes that distinction central.

### Most important feature here

Implement activation idempotency.

Create:

```text
activation_key
```

and enforce uniqueness.

Then write tests:

```text
same trigger processed twice
        ↓
one Occurrence
```

That should be proven before Scheduler work exists.

---

# Phase 11 — Task dependencies

Now add:

```text
task_dependencies
```

and the dependency service.

Keep this simple in Phase 1:

```text
dependency satisfied
if referenced Task == COMPLETED
```

The design specifically treats dependencies as **eligibility**, not a trigger category.

---

# Phase 12 — Eligibility

Now implement the Eligibility Engine.

This is the first point where I would resist the temptation to make a giant "is_runnable()" function.

Break it into explicit checks:

```text
Task active?
Occurrence activated?
Dependency satisfied?
Condition satisfied?
Runnable time reached?
Cancelled?
Expired?
```

Conceptually:

```python
EligibilityResult(
    eligible=True/False,
    reason=...
)
```

That gives the scheduler an explanation rather than just:

```python
False
```

### Important distinction

Eligibility:

> **May this work run?**

Scheduler:

> **Can this work run now?**

That boundary is explicit in the architecture.

---

# Phase 13 — SchedulerWork

Now create the scheduler-facing entity.

Implement:

```text
SchedulerWork
SchedulerWorkState
SchedulerWorkRepository
```

Durable states:

```text
WAITING
READY
ADMITTED
DISPATCHED
CANCELLED
EXPIRED
```

Do **not** create durable:

```text
QUEUED
```

because the architecture intentionally treats queue membership as in-memory operational state.

### Important design point

Don't let SchedulerWork become a duplicate Occurrence.

It should contain scheduler state and scheduler timestamps, not Task semantics.

---

# Phase 14 — Scheduler priority

Now implement:

```text
scheduler/priority.py
```

The priority function should consume inputs such as:

```text
Task.base_priority
Occurrence.urgency
Occurrence.deadline_at
Occurrence.runnable_at
current time
```

and calculate:

```text
effective_priority
```

with bounded aging.

Do not persist "the current truth" of effective priority.

Record it in a decision snapshot when needed. The database design explicitly says effective priority is diagnostic/derived state.

### Test this mathematically

You want tests like:

```text
higher base priority beats lower base priority

higher urgency increases priority

deadline pressure increases priority

aging increases priority

aging is bounded
```

and tests around equal-priority ordering.

---

# Phase 15 — Fairness

Only after priority works.

Implement the smallest possible fairness layer:

```text
bounded aging
optional lane guard
```

Do not implement fancy fair-share scheduling.

The architecture deliberately says Phase 1 fairness should remain simple.

---

# Phase 16 — Resource model

Now implement:

```text
Resource
Reservation
ResourceRepository
```

Start with:

```text
resource_id
name
resource_type
capacity
state
metadata
```

Then:

```text
Reservation
```

associated with:

```text
scheduler_work_id
resource_id
quantity
status
timestamps
```

The database design explicitly says Reservations belong to SchedulerWork, not merely Occurrence.

---

# Phase 17 — Admission

This is the most important scheduler transaction.

Implement:

```text
scheduler/admission.py
```

The critical operation should conceptually be:

```text
BEGIN
    check concurrency
    check resource capacity
    create reservation(s)
    transition SchedulerWork → ADMITTED
COMMIT
```

One transaction.

No external execution.

No network call.

No model call.

No filesystem work.

Just durable admission.

Then write a race test with two concurrent scheduler attempts against capacity 1.

Expected:

```text
one admitted
one blocked
```

never:

```text
two admitted
```

---

# Phase 18 — Run Scheduler

Only now implement the orchestrator.

`scheduler.py` should coordinate:

```text
eligibility
→ candidate selection
→ priority
→ fairness
→ concurrency
→ resource admission
→ decision record
→ dispatch
```

Do NOT put every algorithm into `scheduler.py`.

The package architecture explicitly says the orchestrator should coordinate these components rather than implement all of them.

---

# Phase 19 — Wake Scheduler

After Run Scheduler works, implement temporal wake behavior.

Build:

```text
WakeScheduler
ScheduleCalculator
TimerAdapter
```

The Timer Adapter can initially be extremely simple.

You don't need APScheduler immediately.

The important abstraction is:

```text
durable schedule state
        ↓
wake mechanism
        ↓
scheduler reevaluation
```

not:

```text
APScheduler owns Pinky schedules
```

The architecture explicitly prohibits the timer library from becoming the source of truth.

---

# Phase 20 — Scheduler decision records

Implement:

```text
DecisionRecord
```

and persist decisions such as:

```text
ELIGIBLE
BLOCKED
SELECTED
ADMITTED
EXPIRED
CANCELLED
```

with:

```text
effective_priority
priority_components
resource_snapshot
reason_code
details
```

This becomes invaluable when debugging scheduler behavior.

---

# Phase 21 — Recovery

Only now do the full startup recovery path.

It should:

```text
load durable state
    ↓
identify incomplete SchedulerWork
    ↓
reconcile Reservations
    ↓
rebuild queues
    ↓
restore wake timers
    ↓
resume scheduler
```

The architecture explicitly treats recovery as a first-class concern.

### Test ugly crashes

Don't just test normal restart.

Test:

```text
crash after Event commit
crash before consumer offset
crash during scheduling
crash after reservation
crash before dispatch
restart twice
```

The important property is that recovery is idempotent.

---

# Phase 22 — Dispatcher boundary

Implement only the boundary.

Something like:

```python
class Dispatcher(Protocol):
    async def dispatch(self, work: SchedulerWork) -> DispatchResult:
        ...
```

For Phase 1:

```text
Dispatcher
    ↓
DISPATCH INTENT
```

and stop.

Do not implement actual execution yet.

The architecture explicitly says the current implementation boundary stops here.

---

# Phase 23 — API

I would actually postpone most API work until the domain services work.

Then expose:

```text
/tasks
/events
/scheduler
/health
```

but as **domain operations**, not database CRUD.

For example:

```text
POST /tasks
POST /tasks/{id}/activate
POST /tasks/{id}/pause
POST /tasks/{id}/cancel
GET  /tasks/{id}

GET  /events/{id}
POST /events

GET  /scheduler/work
GET  /scheduler/decisions

GET  /health
```

The UI should never talk to SQL directly; the architecture explicitly makes Core the owner of those operations.

---

# Phase 24 — Real filesystem reader

Only after SyntheticEventReader is working end-to-end.

Then build something like:

```text
FilesystemReader
```

This is useful because it introduces real-world problems:

```text
bursts
duplicates
rapid changes
partial files
ordering ambiguity
reader failure
backpressure
```

Your architecture already identified filesystem as the first useful real stressor.

---

# The model implementation order, explicitly

You asked specifically:

> What models should I implement first?

This is the order I'd use:

```text
1. IDs / Clock / shared primitives
2. Event
3. Task
4. Trigger
5. Occurrence
6. TaskDependency
7. SchedulerWork
8. Resource
9. Reservation
10. DecisionRecord
11. OutboxEntry
12. ConsumerOffset
```

But there is an important nuance:

**I wouldn't implement all of those immediately as Pydantic classes.**

I'd implement each one only when its surrounding behavior is ready.

For example:

```text
Event
  ↓
EventStore
  ↓
EventIntake
```

before moving on.

Then:

```text
Task
  ↓
Task lifecycle
  ↓
Trigger
  ↓
Occurrence
```

Then scheduler.

That keeps every step executable and testable.

---

# The repository sequence I'd actually work in

If I were sitting at your machine, I'd create commits roughly like this:

```text
001 project packaging/tooling
002 common primitives
003 runtime lifecycle
004 sqlite infrastructure
005 alembic baseline
006 event domain
007 event persistence
008 event intake
009 event outbox
010 consumer offsets/router
011 synthetic reader
012 task domain
013 task persistence/service
014 triggers
015 occurrences
016 task dependencies
017 eligibility
018 scheduler work
019 priority
020 fairness/aging
021 resources
022 reservations
023 admission
024 scheduler orchestration
025 wake scheduler
026 decision records
027 recovery
028 dispatcher boundary
029 API
030 filesystem reader
031 phase-1 acceptance suite
```

That is much safer than trying to implement a huge "scheduler feature" across 15 files in one commit.

---

# And the AI-agent workflow I'd enforce

Since you want AI-assisted development, I'd make every implementation request follow:

```text
Read:
    System Design Specification
    relevant subsystem spec
    current code

Then state:
    Requirement being implemented
    Domain entities affected
    Invariants affected
    State transitions affected
    Persistence changes
    Tests required

Then:
    implement
    test
    lint
    explain
```

This is especially important because the repository architecture explicitly says the subsystem boundaries matter more than the directory names.

---

# The single biggest thing I would NOT do

Don't implement the LLM yet.

Not even a fake agent loop.

Not even "just one little tool."

The current architecture deliberately treats the LLM as a replaceable reasoning resource and says the implementation boundary stops after Scheduler/Dispatch.

We should prove:

```text
Event
→ Task
→ Occurrence
→ Eligibility
→ Scheduler
→ Admission
→ Dispatch intent
→ Restart
→ Recovery
```

**without an LLM.**

That would be an exceptionally useful milestone.

Because once that works, we'll know the deterministic runtime works independently of AI.

---

## One correction I'd make before coding

I noticed your current repository's `Event` model is missing some fields that your canonical database design now considers part of the Event contract: `metadata`, `causation_id`, and `correlation_id`.

I would resolve that **before implementing Event persistence**, rather than letting the current model and schema drift apart.

The next concrete task should therefore be:

> **Lock the Event domain contract and implement Event + EventStore completely, with tests, before touching Task.**

That gives us a clean first vertical slice rather than a pile of half-built models.
