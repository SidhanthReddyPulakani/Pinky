# Pinky — Technology Stack v1

**Status:** Proposed / Phase 1 baseline  
**Scope:** Application foundation through Scheduler, with UI and supporting developer infrastructure  
**Primary goals:** Fast startup, low idle overhead, high UI customization, local-first operation, maintainability, and clear subsystem boundaries.

## 1. Final Stack

```text
Tauri 2
 └── React + TypeScript UI
       │
       └── local API / IPC
             │
             ▼
        Python Core
        ├── asyncio
        ├── FastAPI
        ├── Event System
        ├── Task System
        └── Scheduler
             │
             ▼
        SQLite + WAL
        ├── SQLAlchemy 2
        └── Alembic

Supporting:
  uv / Ruff / pytest / OpenTelemetry / Python logging

Future / replaceable:
  Ollama / llama.cpp / vLLM / other ModelProvider
```

## 2. Core Decisions

### Desktop: Tauri 2

Locked. Tauri uses the OS WebView rather than shipping a separate browser runtime and combines a Rust application layer with a web frontend. It supports desktop lifecycle, tray, system integration, packaging, and frontend↔Rust communication. citeturn0search6

Rust should remain primarily the desktop shell:

```text
desktop lifecycle
OS integration
window management
tray
packaging
secure bridge
```

Do not move Pinky's domain logic into Rust merely because Rust is available.

### Frontend: React + TypeScript

Default frontend inside Tauri. Tauri does not require a specific frontend framework, so this keeps the UI highly customizable without coupling the Core to the UI framework. citeturn0search6

### Core: Python + asyncio

Python remains the Core language. `asyncio` is the primary concurrency model for Event Readers, timers, IPC/API work, integrations, and other I/O-heavy activity.

### Local API / IPC: FastAPI

FastAPI provides typed request validation and automatic OpenAPI documentation. citeturn1search0turn1search14

The API is an application/domain boundary, not a database CRUD wrapper.

### Validation: Pydantic

Use Pydantic for API contracts, Event envelopes, Task requests, configuration, IPC messages, and other explicit data boundaries.

### Database: SQLite

Locked for Phase 1. Use WAL mode and foreign keys. SQLite is appropriate for Pinky's local-first, single-user, transaction-heavy architecture.

### DB access: SQLAlchemy 2

Use SQLAlchemy 2.x. Its SQLite dialect supports standard and asyncio interfaces; `aiosqlite` provides the asyncio interface. citeturn0search2turn0search13

Keep transactions short. Never hold database transactions across LLM calls or external execution.

### Migrations: Alembic

Use Alembic for schema migrations. Alembic explicitly supports SQLite batch migration operations for SQLite's ALTER TABLE limitations. citeturn0search1turn0search15

### Python tooling: uv + Ruff

Use `uv` for Python versions, environments, dependencies, lockfiles, and project commands. It provides project management and reproducible locking in one tool. citeturn1search3turn1search12

Use Ruff for linting and formatting. citeturn1search2

### Testing: pytest

Use pytest for unit, integration, transaction, replay, scheduler, recovery, and end-to-end tests.

The highest-value early tests are:

```text
Event → persistence → replay
Event → Trigger → Occurrence
Occurrence → SchedulerWork
Scheduler → admission
Resource → reservation
Crash → recovery
```

### Observability: OpenTelemetry + Python logging

Use OpenTelemetry as the vendor-neutral observability foundation. Python support includes stable traces and metrics, while logs can integrate with existing Python logging infrastructure. citeturn0search0turn0search4turn0search10

Start with structured logs and correlation identifiers; add richer tracing/metrics as runtime complexity grows.

## 3. LLM Runtime — Deliberately Not Locked

Do not hard-code Pinky to one local inference runtime yet.

Define an internal interface:

```text
Agent / Execution
       ↓
Model Router
       ↓
Model Provider
       ↓
Ollama / llama.cpp / vLLM / future provider
```

This preserves the possibility of the previously discussed:

```text
Interactive model
+
Autonomous/reasoning model
```

without embedding that decision into the Event/Task/Scheduler architecture.

The actual runtime should be selected after hardware, model family, quantization, VRAM, context length, concurrency, streaming, and tool-calling requirements are known.

## 4. Event Transport

Do **not** introduce Redis, Kafka, RabbitMQ, NATS, or another external broker in Phase 1.

The existing design already provides:

```text
Event Store
+ Outbox
+ Consumer Offsets
+ in-process routing
```

For a local single-user application, this is sufficient and avoids unnecessary operational complexity.

A broker can be introduced later behind the Event subsystem if Pinky becomes multi-process or distributed.

## 5. Workflow Engine

Do **not** introduce Temporal in Phase 1. Temporal provides durable workflow execution and crash-resume semantics, including long-running workflows. citeturn0search7

It remains a legitimate future option if Pinky eventually needs distributed, long-running workflows. For now, Pinky's own Event → Task → Occurrence → Scheduler → Execution model should remain explicit and under our control.

## 6. Process Architecture

Initial deployment should stay small:

```text
Pinky Desktop
│
├── Tauri process
│     └── UI WebView
│
└── Pinky Core process
      ├── Event subsystem
      ├── Task subsystem
      ├── Scheduler
      ├── API
      └── SQLite
```

Later, model runtimes, execution workers, or sandboxes can become separate processes where isolation or resource management requires it.

## 7. Startup Model

Startup should be staged:

```text
A. Tauri + UI
B. Python Core + SQLite + recovery
C. Optional model runtime / workers / integrations
```

Opening Pinky must not require loading an LLM.

## 8. Security Boundary

```text
UI
 ↓
Core API
 ↓
Domain authorization
 ↓
Execution
```

The UI must never directly manipulate SQLite. Future tool execution must establish explicit permissions, sandboxing, and resource limits before arbitrary system actions are allowed.

## 9. Phase 1 Database

Use `Pinky_Database_Schema_v2.md` as the canonical persistence specification.

Core tables:

```text
events
outbox
consumer_offsets

tasks
task_triggers
task_dependencies
occurrences

scheduler_work
resources
reservations
scheduler_decisions
```

## 10. What We Are Not Adding Yet

```text
Redis
Kafka
RabbitMQ
NATS
Temporal
PostgreSQL
MongoDB
Kubernetes
Docker
microservices
GraphQL
gRPC
cloud observability stacks
```

These may become useful later, but none solves a Phase 1 requirement strongly enough to justify the added complexity.

## 11. Industry Alignment

The stack follows widely used patterns without importing distributed-system infrastructure unnecessarily:

```text
Desktop       Tauri / Rust / WebView
Frontend      React / TypeScript
Backend       Python
API           FastAPI
Validation    Pydantic
Persistence   SQLite / SQLAlchemy
Migrations    Alembic
Async         asyncio
Tooling       uv / Ruff
Testing       pytest
Observability OpenTelemetry
```

The important principle is that "industry standard" does not mean "use the largest infrastructure available." For a local agent, minimizing unnecessary infrastructure is itself a useful architectural property.

## 12. Phase 1 Development Order

```text
1. Repository structure
2. Python environment / uv
3. Tauri application shell
4. React + TypeScript frontend
5. Core process
6. FastAPI local API
7. SQLite initialization
8. SQLAlchemy models
9. Alembic migrations
10. Event Store
11. Outbox
12. Consumer offsets
13. Event Intake
14. Event Router
15. Tasks
16. Triggers
17. Occurrences
18. SchedulerWork
19. Resources
20. Reservations
21. Scheduler
22. Scheduler recovery
23. UI ↔ Core integration
24. Phase 1 integration tests
```

## 13. Final Decision

**Pinky Phase 1:**

> **Tauri 2 + React + TypeScript for the desktop application, Python + asyncio + FastAPI for the Core runtime, SQLite + SQLAlchemy + Alembic for persistence, and uv + Ruff + pytest + OpenTelemetry for engineering infrastructure.**

The LLM runtime remains replaceable.

The resulting stack is intentionally small, local-first, fast to start, highly customizable at the UI layer, and capable of growing into the later agent/execution architecture without prematurely introducing distributed infrastructure.

## 14. Boundary of This Document

This document defines technology choices. It does not redefine the domain model, Event taxonomy, Task semantics, Scheduler semantics, database schema, Execution architecture, or LLM reasoning architecture. Those remain defined by their respective design documents.
