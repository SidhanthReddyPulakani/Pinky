# Pinky — Technology Stack v1

**Status:** Design specification  
**Depends on:** `Pinky_Architecture_v1.md`, `Pinky_Domain_Model_and_State_Machines_v1.md`, `Pinky_Database_Schema_v1.md`  
**Scope:** Phase 1 implementation technology choices  
**Principle:** Technology supports the architecture; no framework becomes the architecture.

---

# 1. Stack Summary

| Area | Phase 1 Choice | Role |
|---|---|---|
| Language | Python 3.12+ | Primary implementation language |
| Runtime | `asyncio` | Cooperative asynchronous runtime |
| Database | SQLite | Durable local source of truth |
| SQLite mode | WAL | Read/write concurrency and crash-safe transactional storage |
| SQLite access | `aiosqlite` initially | Async DB interface |
| Validation | Pydantic v2 | Boundary/configuration validation |
| Scheduling timers | APScheduler | Wake Scheduler/timer adapter |
| Main scheduler | Pinky-owned implementation | Priority, fairness, admission, resources |
| Internal transport | `asyncio.Queue` + Router | Fast in-process event delivery |
| HTTP API | FastAPI | Future/local control interface |
| HTTP client | httpx | External HTTP integrations |
| Logging | Python `logging` | Runtime diagnostics |
| Configuration | Pydantic Settings | Typed configuration |
| Testing | pytest + pytest-asyncio | Unit/integration testing |
| Packaging | `uv` + `pyproject.toml` | Dependency/environment management |
| LLM runtime | Deferred | Execution subsystem concern |
| Containers | Deferred | Not required for Phase 1 |

---

# 2. Core Principle

Pinky is a local runtime first.

The desired Phase 1 deployment is:

```text
ONE MACHINE
    ↓
ONE PINKY PROCESS
    ↓
ONE ASYNC RUNTIME
    ↓
ONE SQLITE DATABASE
```

The internals are modular, but deployment remains intentionally simple.

The architecture should not depend on distributed infrastructure until actual requirements justify it.

---

# 3. Python

## Choice

```text
Python 3.12+
```

Python is appropriate because Phase 1 is primarily an orchestration and I/O workload:

```text
event ingestion
database I/O
timers
network I/O
IPC
subprocess management
coordination
scheduling
```

The architecture does not require a CPU-heavy numerical runtime.

## Version policy

Use a supported modern Python release.

The exact minimum version should be pinned in project metadata when implementation starts.

Do not target many Python versions simultaneously during Phase 1.

A narrow supported range reduces dependency and testing complexity.

---

# 4. Async Runtime: asyncio

`asyncio` is the foundation of Pinky's in-process concurrency model.

Conceptually:

```text
Pinky Process
      │
      ▼
 asyncio Event Loop
      │
 ┌────┼─────────────────────────────┐
 │    │             │               │
Readers Router   Scheduler     Runtime Manager
 │                │
 └────────────────┴──────→ persistence
```

Use `asyncio` for:

- Event Readers
- Event Router
- Outbox publisher
- Scheduler wake signals
- Scheduler coordination
- background maintenance
- HTTP I/O
- subprocess coordination

## Important distinction

Pinky's domain `Task` is not Python's `asyncio.Task`.

Code should maintain clear naming boundaries.

For example:

```text
domain.Task
runtime asyncio.Task
```

Do not let Python's concurrency primitive leak into the domain model.

---

# 5. Concurrency Model

Phase 1 should prefer:

```text
async I/O
+
cooperative concurrency
```

over arbitrary thread/process proliferation.

Use threads/processes only where required by:

- blocking third-party libraries
- CPU-bound work
- OS integration
- model runtimes
- native tooling

The Scheduler should never equate:

```text
asyncio concurrency
```

with:

```text
Pinky resource capacity
```

They are different concepts.

---

# 6. SQLite

SQLite is the durable Phase 1 database.

Reasons:

```text
single-machine deployment
single Pinky process
transactional state transitions
durability
low operational overhead
local data
```

SQLite should be configured with:

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
```

Additional pragmas should be chosen deliberately rather than treated as boilerplate.

---

# 7. SQLite WAL

WAL is appropriate for Pinky because the runtime will have:

```text
continuous reads
short transactional writes
scheduler queries
event ingestion
background consumers
```

The database remains local.

WAL is not a distributed coordination mechanism.

Phase 1 therefore remains:

```text
local SQLite
```

rather than:

```text
PostgreSQL
+
distributed workers
```

---

# 8. Database Driver: aiosqlite

Use:

```text
aiosqlite
```

initially.

The persistence layer should expose application/domain-oriented interfaces rather than exposing raw `aiosqlite` objects throughout the codebase.

Conceptually:

```text
Scheduler
    ↓
SchedulerStore
    ↓
SQLite implementation
    ↓
aiosqlite
    ↓
SQLite
```

This keeps persistence implementation replaceable.

---

# 9. No ORM Initially

Do not make an ORM the primary abstraction.

Pinky's database operations contain important transactional semantics:

```text
event + outbox
occurrence + scheduler work
resource check + reservation + admission
```

Explicit SQL makes these operations easier to reason about.

Repositories/stores should encapsulate SQL without hiding transaction boundaries from the subsystem design.

An ORM can be reconsidered later if schema complexity actually justifies it.

---

# 10. Migration Tooling

Schema migrations are mandatory.

The implementation should maintain ordered migrations such as:

```text
001_initial
002_add_...
003_...
```

A migration tool can be selected during implementation.

Two reasonable options are:

```text
Alembic
```

or:

```text
small project-owned migration runner
```

The choice should be based on actual project complexity.

Do not introduce Alembic solely because it is common if a very small migration layer is easier to maintain.

---

# 11. Pydantic v2

Use Pydantic for typed validation at boundaries.

Good uses:

```text
external Event payloads
configuration
Task creation commands
API request/response schemas
external service data
```

Conceptually:

```text
untrusted input
      ↓
Pydantic validation
      ↓
validated command/data
      ↓
domain subsystem
```

Pydantic should not become the domain architecture.

Not every internal object needs to be a Pydantic model.

---

# 12. Domain Objects

Keep domain objects conceptually separate from:

```text
Pydantic transport models
SQLite rows
HTTP request models
```

A healthy boundary is:

```text
Input Schema
    ↓
Domain Command / Object
    ↓
Repository
    ↓
Database Record
```

This avoids coupling the domain to a particular serialization or persistence framework.

---

# 13. APScheduler

Use APScheduler only for the **Wake Scheduler** role.

```text
                 PINKY
                   │
        ┌──────────┴──────────┐
        │                     │
 Wake Scheduler          Run Scheduler
        │                     │
 APScheduler             Pinky code
        │                     │
        └──────────┬──────────┘
                   ▼
              Dispatcher
```

APScheduler may manage:

```text
one-shot timers
intervals
cron-like schedules
wakeups
retry timing
deadline-related wakeups
```

The final feature set should be limited to what Pinky actually uses.

---

# 14. APScheduler Is Not the Source of Truth

APScheduler must not own:

```text
Task lifecycle
Occurrence lifecycle
priority
aging
resources
reservations
admission
fairness
Pinky scheduler state
```

Instead:

```text
Pinky persistent state
        ↓
timer registration
        ↓
APScheduler
        ↓
wake callback
        ↓
Pinky re-evaluates state
```

If APScheduler loses an in-memory timer, Pinky must be capable of rebuilding it from durable state.

This is one of the most important technology boundaries.

---

# 15. Main Scheduler

The Run Scheduler is custom Pinky code.

No general-purpose task queue should replace it.

Its responsibilities include:

```text
eligibility consumption
priority calculation
bounded aging
deadline pressure
queue management
concurrency limits
resource admission
reservation
backpressure
simple backfill
dispatch decision
recovery
```

This is core Pinky logic.

---

# 16. Internal Event Transport

Use:

```text
asyncio.Queue
```

and a Pinky-owned routing layer.

Conceptually:

```text
SQLite / Outbox
       ↓
Publisher
       ↓
asyncio transport
       ↓
EventRouter
       ├── Trigger Engine
       ├── Scheduler
       ├── internal consumers
       └── future components
```

The queue is not durable.

If the process crashes:

```text
in-memory queue state disappears
```

Durable state remains in SQLite and must be replayable.

---

# 17. Why No External Message Broker

Do not add:

```text
Kafka
RabbitMQ
Redis Streams
NATS
```

during Phase 1.

They solve problems Pinky does not yet have:

```text
multiple machines
large distributed throughput
independent broker scaling
cross-process distributed delivery
```

Pinky instead needs:

```text
correct persistence
clear transactions
replay
simple local operation
```

SQLite + in-process transport is sufficient for the intended Phase 1 deployment.

---

# 18. FastAPI

FastAPI is a good candidate for Pinky's local/API boundary.

Potential future interfaces:

```text
CLI
Web UI
local application
remote/local API client
voice interface
```

Conceptually:

```text
             Pinky Core
                 │
          Command / Query API
                 │
       ┌─────────┼─────────┐
       ↓         ↓         ↓
      CLI     FastAPI    future UI
```

FastAPI should not be required for the core runtime to function.

Pinky should be able to start its core subsystems without depending on an HTTP server.

---

# 19. HTTP Client: httpx

Use `httpx` for external HTTP integrations.

Potential uses:

```text
webhooks
external APIs
cloud/local services
future integrations
```

Keep external network I/O behind integration modules.

Do not allow arbitrary HTTP calls to become part of the domain layer.

---

# 20. Logging

Use Python's standard:

```text
logging
```

initially.

Logs should carry contextual identifiers where applicable:

```text
event_id
task_id
occurrence_id
scheduler_work_id
reservation_id
correlation_id
```

The objective is to answer:

> Why did Pinky make this decision?

without requiring a debugger.

Structured logging can be introduced without changing the domain architecture.

---

# 21. Configuration

Use typed configuration through:

```text
Pydantic Settings
```

The configuration hierarchy should conceptually be:

```text
defaults
    ↓
configuration file
    ↓
environment
    ↓
runtime/task policy
```

Task-level settings should not require modifying global configuration.

Examples:

```yaml
scheduler:
  max_concurrency: 4

resources:
  strong_llm:
    capacity: 1
```

The exact configuration file format can be selected during implementation.

---

# 22. Testing

Use:

```text
pytest
pytest-asyncio
```

Testing priorities:

## Domain tests

State transitions and invariants.

## Persistence tests

Transactions, foreign keys, migrations, recovery.

## Event tests

Persistence, outbox, replay, deduplication.

## Scheduler tests

Priority, aging, resources, concurrency, deadlines.

## Recovery tests

Crash-equivalent states and reconciliation.

## Integration tests

End-to-end:

```text
Event
 ↓
Task
 ↓
Occurrence
 ↓
Scheduler
 ↓
Admission
 ↓
Dispatch intent
```

Execution can be represented by a mock dispatcher.

---

# 23. Scheduler Testing Requirements

The Scheduler must have deterministic tests for cases such as:

```text
A higher-priority task arrives.

A low-priority task has waited for a long time.

A required resource is unavailable.

A resource becomes available.

Task concurrency limit is reached.

A deadline approaches.

A deadline expires.

Multiple resources are required.

A high-priority item is blocked but another item is runnable.

Pinky crashes after reservation.

Pinky crashes before admission.

Two scheduler decisions attempt the same capacity concurrently.
```

These tests are more valuable than superficial line coverage.

---

# 24. Packaging: uv

Use:

```text
uv
```

with:

```text
pyproject.toml
uv.lock
```

The lockfile should be committed.

Development environments should be reproducible.

Dependencies should be deliberately added rather than installing large framework bundles.

---

# 25. Suggested Dependency Groups

Conceptually:

```text
runtime
    pydantic
    pydantic-settings
    aiosqlite
    apscheduler

interface
    fastapi
    uvicorn
    httpx

development
    pytest
    pytest-asyncio
```

The exact dependency list will be finalized when implementation begins.

---

# 26. LLM Technology

LLMs are deliberately **not a Phase 1 core dependency**.

Pinky should be able to boot and demonstrate:

```text
Event
→ Task
→ Occurrence
→ Scheduler
→ Admission
→ Dispatch
```

without loading an LLM.

This is important because:

```text
LLM
```

is a future execution resource, not Pinky's runtime.

---

# 27. Future LLM Boundary

The eventual architecture should look approximately like:

```text
                    Scheduler
                        │
                     Dispatch
                        │
                    Execution
                        │
             ┌──────────┼──────────┐
             │          │          │
          small LLM  strong LLM   tools
```

The Scheduler should not know how inference works.

It should only understand resource requirements such as:

```text
small_llm
strong_llm
gpu
```

The Execution subsystem resolves those resources into actual runtime implementations.

---

# 28. LLM Framework Policy

Do not make Pinky dependent on:

```text
LangChain
LlamaIndex
AutoGen
CrewAI
```

as architectural foundations.

They may eventually be evaluated as optional libraries inside an Execution/agent subsystem if a concrete capability requires them.

The core runtime must remain independent.

---

# 29. Containers

Do not require Docker for Phase 1.

Local development should work directly with:

```text
Python
uv
SQLite
```

Containers may become useful later for:

- isolated execution workers
- model services
- reproducible deployment
- external integrations
- sandboxing

But none is required to validate the current architecture.

---

# 30. Operating-System Integration

OS-specific functionality should be isolated behind readers/adapters.

Examples:

```text
filesystem watcher
process monitor
system events
device events
```

The Event subsystem should consume canonical Events rather than directly depending on OS-specific APIs.

Conceptually:

```text
OS API
   ↓
Reader Adapter
   ↓
Canonical Event
   ↓
Pinky
```

---

# 31. Dependency Policy

A dependency should be introduced when it provides meaningful functionality that is better maintained externally than internally.

Prefer:

```text
small dependency
clear boundary
replaceable implementation
```

Avoid:

```text
framework dependency
deep coupling
large transitive dependency graph
```

The question for every dependency should be:

> What part of Pinky's architecture does this dependency implement, and can we replace it without changing the domain model?

---

# 32. Technologies Explicitly Deferred

No Phase 1 dependency on:

```text
PostgreSQL
Redis
Kafka
RabbitMQ
NATS
Celery
Kubernetes
Docker
distributed locks
distributed task queues
vector databases
LLM orchestration frameworks
cloud model APIs
```

They can be evaluated later if requirements emerge.

---

# 33. Technology-to-Architecture Mapping

```text
ARCHITECTURE              TECHNOLOGY

Pinky runtime             Python + asyncio

Durable state             SQLite + WAL

Async database access     aiosqlite

Data validation           Pydantic

Configuration             Pydantic Settings

Event transport           asyncio.Queue

Event routing             Pinky-owned Router

Wake scheduling           APScheduler

Run scheduling            Pinky-owned Scheduler

HTTP API                  FastAPI

HTTP integration          httpx

Testing                   pytest + pytest-asyncio

Packaging                 uv

Logging                   Python logging

LLM execution             Deferred
```

---

# 34. Technology Boundaries

The following dependencies should remain behind interfaces:

```text
SQLite
    → Persistence interfaces

APScheduler
    → Wake Scheduler interface

FastAPI
    → API interface

httpx
    → External integration interfaces

Pydantic
    → Boundary validation

LLM runtime
    → Execution resource interface
```

The domain should not import framework-specific types unnecessarily.

---

# 35. Proposed Project Shape

A starting structure could be:

```text
pinky/
├── pyproject.toml
├── uv.lock
├── README.md
│
├── src/
│   └── pinky/
│       ├── core/
│       ├── domain/
│       ├── events/
│       ├── tasks/
│       ├── scheduler/
│       ├── persistence/
│       ├── runtime/
│       └── interfaces/
│
├── migrations/
│
└── tests/
    ├── unit/
    ├── integration/
    └── recovery/
```

This is an initial implementation shape, not a final requirement.

Package boundaries should follow subsystem ownership.

---

# 36. Startup Model

The runtime should eventually start approximately as:

```text
main()
  ↓
load configuration
  ↓
initialize logging
  ↓
initialize database
  ↓
run migrations
  ↓
recover persistent state
  ↓
initialize Event Router
  ↓
initialize Readers
  ↓
initialize Wake Scheduler
  ↓
initialize Run Scheduler
  ↓
start runtime supervision
  ↓
Pinky operational
```

Startup ordering matters because recovery must occur before normal scheduling resumes.

---

# 37. Shutdown Model

Shutdown should be graceful:

```text
shutdown signal
      ↓
stop accepting new external work
      ↓
stop readers
      ↓
stop wake generation
      ↓
allow/coordinate scheduler shutdown
      ↓
flush required durable state
      ↓
release/reconcile runtime-owned resources
      ↓
close database
      ↓
exit
```

Execution-specific shutdown semantics will be added later.

---

# 38. Phase 1 Technology Acceptance Criteria

The stack is considered validated when Pinky can:

```text
1. Start with one local process.

2. Initialize SQLite reliably.

3. Apply migrations.

4. Persist Events transactionally.

5. Persist Outbox entries with Events.

6. Recover pending Outbox work after restart.

7. Create Tasks and Occurrences.

8. Run Scheduler decisions asynchronously.

9. Atomically reserve resources.

10. Recover stale Scheduler state.

11. Restore wake timers from durable state.

12. Run without an LLM.

13. Run tests deterministically.

14. Run entirely on a local machine without external infrastructure.
```

---

# 39. Final Technology Principle

The stack should preserve this hierarchy:

```text
                  PINKY DOMAIN
                       │
        ┌──────────────┼──────────────┐
        │              │              │
      Events        Tasks         Scheduler
        │              │              │
        └──────────────┼──────────────┘
                       │
                  Interfaces
                       │
        ┌──────────────┼──────────────┐
        │              │              │
     SQLite        APScheduler     asyncio
        │              │              │
        └──────────────┼──────────────┘
                       │
                  Infrastructure
```

Frameworks and libraries are implementation choices.

The domain model, state machines, invariants, and subsystem contracts remain Pinky's architectural authority.

---

# 40. Decision Summary

| Decision | Status |
|---|---|
| Python | Fixed |
| asyncio | Fixed |
| SQLite | Fixed |
| SQLite WAL | Fixed |
| aiosqlite initially | Fixed |
| ORM-first design | Rejected for Phase 1 |
| Pydantic | Fixed |
| APScheduler for Wake Scheduler | Fixed |
| Pinky-owned Run Scheduler | Fixed |
| asyncio.Queue for in-process transport | Fixed |
| FastAPI | Selected for future API boundary |
| httpx | Selected for external HTTP boundary |
| pytest + pytest-asyncio | Fixed |
| uv | Selected |
| Standard logging initially | Fixed |
| LLM runtime | Deferred |
| LLM orchestration framework | Deferred |
| Redis/Kafka/RabbitMQ/NATS | Deferred |
| Celery | Excluded from Phase 1 |
| Docker | Deferred |
| Kubernetes | Deferred |
| PostgreSQL | Deferred |

---

# 41. Next Step

With:

```text
Pinky_Architecture_v1.md
Pinky_Domain_Model_and_State_Machines_v1.md
Pinky_Database_Schema_v1.md
Pinky_Tech_Stack_v1.md
```

the design foundation is complete enough to begin implementation planning.

The next artifact should be an **Implementation Specification / Phase 1 Build Plan**, covering:

```text
repository structure
      ↓
database initialization
      ↓
domain types
      ↓
repositories
      ↓
Event Intake
      ↓
Event Store + Outbox
      ↓
Router
      ↓
Task/Occurrence
      ↓
Eligibility
      ↓
Wake Scheduler
      ↓
Run Scheduler
      ↓
Resource Admission
      ↓
Recovery
      ↓
Mock Dispatcher
      ↓
integration tests
```

The first implementation milestone remains:

**Event → Task → Occurrence → Scheduler → Admission → Dispatch Intent**

with no real Execution subsystem yet.
