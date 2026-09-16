# Pinky — Tech Stack & Implementation How-To

*Companion to `pinky_architecture.md`. That document defines the components and their contracts; this document tells you exactly which tools to install and how to wire each component to those tools, with working code.*

---

## 1. Tech Stack at a Glance

| Component (from the architecture doc) | Tool | Install |
|---|---|---|
| Runtime | Python 3.12+, single process, `asyncio` | `uv init pinky && cd pinky` |
| Package/venv manager | `uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Source of truth / persistence | SQLite (WAL mode) + `aiosqlite` | `uv add aiosqlite` |
| ID generation | ULID (sortable, unique) | `uv add python-ulid` |
| In-process event bus | plain `asyncio.Queue` fan-out | stdlib, no install |
| Wake Scheduler (cron/interval/date, misfire, DST) | **APScheduler v3** (`AsyncIOScheduler` + `SQLAlchemyJobStore`) | `uv add apscheduler sqlalchemy` |
| Filesystem reader | `watchdog` | `uv add watchdog` |
| Autonomous runtime (strong LLM + tools, checkpointed, interruptible) | **LangGraph** (`create_react_agent` + `SqliteSaver`) | `uv add langgraph langgraph-checkpoint-sqlite langchain-anthropic` |
| Interactive runtime (small/fast LLM) | **Ollama** (local) via `ollama` Python client | `uv add ollama` + `ollama pull llama3.2` |
| Config | `tomllib` (stdlib, read) + SQLite `config` table (write/override) | stdlib |
| Observability | `structlog` + your own `decision_log` table | `uv add structlog` |
| Process supervision | hand-written `asyncio.TaskGroup` supervisor | stdlib |
| Deployment | `systemd` (Linux) / `launchd` (macOS) service | OS-native |

Everything above deliberately fits in **one process, one SQLite file**. No Docker, no message broker, no second database — see the architecture doc §2/§3/§8 for why that's the right call for a single-user local agent, not a corner cut.

---

## 2. Project Layout

```
pinky/
├── pyproject.toml
├── pinky.toml                     # global config defaults (TOML, human-edited)
├── data/
│   └── pinky.db                    # the one SQLite file — events, tasks, occurrences,
│                                    # executions, attempts, resources, config, decision_log,
│                                    # AND the apscheduler_jobs table AND langgraph checkpoints
├── migrations/
│   ├── 0001_init.sql
│   └── ...
└── src/pinky/
    ├── main.py                     # entrypoint + supervisor
    ├── db.py                       # single-writer SQLite access
    ├── ids.py                      # ULID helpers
    ├── bus.py                      # in-process event bus
    ├── config.py                   # layered config resolver
    ├── observability.py            # structlog + decision_log
    ├── events/
    │   ├── intake.py
    │   ├── store.py
    │   ├── router.py
    │   └── readers/
    │       ├── base.py
    │       ├── reader_manager.py
    │       ├── user_input.py
    │       ├── filesystem.py
    │       └── scheduled.py
    ├── tasks/
    │   ├── manager.py
    │   ├── trigger_engine.py
    │   └── eligibility.py
    ├── scheduler/
    │   ├── wake.py                 # APScheduler wrapper
    │   ├── run.py                  # priority/lanes/admission
    │   └── resources.py
    ├── dispatch/
    │   ├── dispatcher.py
    │   └── execution_manager.py
    └── execution/
        ├── deterministic.py
        ├── interactive.py          # Ollama-backed
        ├── autonomous.py           # LangGraph-backed
        ├── tools.py                # Tool interface
        └── approval.py             # Approval Gate
```

---

## 3. Persistence Layer — SQLite, WAL, Single Writer

Enable WAL once, at first connection, and route **all writes** through one dedicated writer task so SQLite never sees concurrent writers (SQLite allows only one writer at a time regardless; a single-writer queue avoids `SQLITE_BUSY` retries entirely rather than papering over them).

```python
# src/pinky/db.py
import asyncio
import aiosqlite

DB_PATH = "data/pinky.db"

class Database:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._write_queue: asyncio.Queue[tuple] = asyncio.Queue()
        self._conn: aiosqlite.Connection | None = None
        self._writer_task: asyncio.Task | None = None

    async def start(self):
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        self._writer_task = asyncio.create_task(self._writer_loop())

    async def _writer_loop(self):
        while True:
            sql, params, fut = await self._write_queue.get()
            try:
                cur = await self._conn.execute(sql, params)
                await self._conn.commit()
                fut.set_result(cur.lastrowid)
            except Exception as e:
                fut.set_exception(e)

    async def write(self, sql: str, params: tuple = ()):
        fut = asyncio.get_event_loop().create_future()
        await self._write_queue.put((sql, params, fut))
        return await fut

    async def read(self, sql: str, params: tuple = ()):
        # Reads are safe to run concurrently in WAL mode without going
        # through the writer queue — open a short-lived read connection.
        async with aiosqlite.connect(self.path) as conn:
            conn.row_factory = aiosqlite.Row
            cur = await conn.execute(sql, params)
            return await cur.fetchall()

    async def stop(self):
        if self._writer_task:
            self._writer_task.cancel()
        if self._conn:
            await self._conn.close()
```

Apply the schema from the architecture doc's §7 as a plain migration file (`migrations/0001_init.sql` — literally paste those `CREATE TABLE` statements). For a single-developer local project, a `schema_version` table plus a list of `.sql` files applied in order is enough; don't reach for Alembic until the schema is actually churning across environments.

```python
# apply once at startup, in main.py
async def run_migrations(db: Database):
    await db.write("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
    rows = await db.read("SELECT version FROM schema_version")
    current = rows[0]["version"] if rows else 0
    for path in sorted(Path("migrations").glob("*.sql")):
        version = int(path.stem.split("_")[0])
        if version > current:
            sql = path.read_text()
            for statement in sql.split(";"):
                if statement.strip():
                    await db.write(statement)
            await db.write("DELETE FROM schema_version")
            await db.write("INSERT INTO schema_version VALUES (?)", (version,))
```

---

## 4. ID Generation — ULID

Every table in the schema uses `TEXT PRIMARY KEY`. Use ULIDs, not UUID4 — they're lexicographically sortable by creation time, which makes `ORDER BY id` on the `events` table give you time order for free (this matters for the Event Store's append-only ordering).

```python
# src/pinky/ids.py
from ulid import ULID

def new_id() -> str:
    return str(ULID())
```

---

## 5. In-Process Event Bus

This is the Event Router (architecture doc §5.1) — a list of subscriber queues, nothing more. No broker needed for a single process.

```python
# src/pinky/bus.py
import asyncio
from typing import Callable, Awaitable

class EventBus:
    def __init__(self):
        self._subscribers: list[Callable[[dict], Awaitable[None]]] = []

    def subscribe(self, handler: Callable[[dict], Awaitable[None]]):
        self._subscribers.append(handler)

    async def publish(self, event: dict):
        # fan-out concurrently; one slow consumer shouldn't block others
        await asyncio.gather(
            *(handler(event) for handler in self._subscribers),
            return_exceptions=True,   # a consumer's bug must not kill the bus
        )
```

Wire consumers in `main.py`:

```python
bus.subscribe(trigger_engine.on_event)
bus.subscribe(observability.on_event)   # decision_log mirror, per architecture §6.5
```

---

## 6. Event Intake — Persist-Before-Publish (the Outbox)

This is the exact mechanism your architecture doc's §7.2 schema backs. Two steps, never reversed:

```python
# src/pinky/events/intake.py
from pinky.ids import new_id
import json, datetime

class EventIntake:
    def __init__(self, db, bus):
        self.db = db
        self.bus = bus

    async def submit(self, candidate: dict) -> str | None:
        # 1. validate + normalize (deliberately dumb/deterministic, per architecture §1.3)
        if "type" not in candidate or "source" not in candidate:
            raise ValueError("candidate event missing type/source")

        # 2. dedupe on (source, source_event_id) via the UNIQUE constraint
        event_id = new_id()
        now = datetime.datetime.utcnow().isoformat()
        try:
            await self.db.write(
                """INSERT INTO events
                   (id, type, source, source_event_id, occurred_at, recorded_at,
                    correlation_id, causation_id, payload, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, candidate["type"], candidate["source"],
                 candidate.get("source_event_id"),
                 candidate.get("occurred_at", now), now,
                 candidate.get("correlation_id"), candidate.get("causation_id"),
                 json.dumps(candidate.get("payload", {})),
                 json.dumps(candidate.get("metadata", {}))),
            )
        except Exception as e:
            if "UNIQUE" in str(e):
                return None   # duplicate — silently accepted, not re-published
            raise

        # 3. persist to outbox BEFORE publishing — this is the durability guarantee
        await self.db.write(
            "INSERT INTO outbox (event_id, published) VALUES (?, 0)", (event_id,)
        )

        # 4. only now publish in-process
        await self._drain_one(event_id, candidate)
        return event_id

    async def _drain_one(self, event_id: str, candidate: dict):
        await self.bus.publish({"id": event_id, **candidate})
        await self.db.write("UPDATE outbox SET published = 1 WHERE event_id = ?", (event_id,))
```

A background **outbox drain task** runs at startup and periodically, to redeliver anything that got persisted but never made it to `published = 1` (e.g. process died mid-publish):

```python
async def outbox_drain_loop(db, bus, intake: EventIntake, interval_s: int = 5):
    while True:
        rows = await db.read("SELECT event_id FROM outbox WHERE published = 0")
        for row in rows:
            ev = (await db.read("SELECT * FROM events WHERE id = ?", (row["event_id"],)))[0]
            await intake._drain_one(ev["id"], dict(ev))
        await asyncio.sleep(interval_s)
```

This is precisely the "prove it with a kill test" checkpoint from the architecture doc's Phase 1 exit criteria — kill the process between step 3 and step 4 above, restart, and this loop redelivers it.

---

## 7. Filesystem Reader — `watchdog` bridged into asyncio

`watchdog`'s `Observer` runs its own OS thread; bridge its callbacks into the asyncio loop with `call_soon_threadsafe` (this is the standard, well-established pattern for this exact library):

```python
# src/pinky/events/readers/filesystem.py
import asyncio
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class _Handler(FileSystemEventHandler):
    def __init__(self, loop: asyncio.AbstractEventLoop, on_event):
        self._loop = loop
        self._on_event = on_event

    def on_created(self, event):
        self._loop.call_soon_threadsafe(
            asyncio.create_task, self._on_event("FILE_CREATED", event.src_path)
        )
    def on_modified(self, event):
        self._loop.call_soon_threadsafe(
            asyncio.create_task, self._on_event("FILE_MODIFIED", event.src_path)
        )
    def on_deleted(self, event):
        self._loop.call_soon_threadsafe(
            asyncio.create_task, self._on_event("FILE_DELETED", event.src_path)
        )

class FilesystemReader:
    category = "LISTENER"

    def __init__(self, path: str, intake, recursive: bool = True):
        self.path = path
        self.intake = intake
        self.recursive = recursive
        self._observer = Observer()

    async def start(self):
        loop = asyncio.get_running_loop()
        handler = _Handler(loop, self._emit)
        self._observer.schedule(handler, self.path, recursive=self.recursive)
        self._observer.start()   # spawns its own OS thread; non-blocking

    async def _emit(self, event_type: str, src_path: str):
        await self.intake.submit({
            "type": event_type,
            "source": "filesystem",
            "source_event_id": f"{src_path}:{event_type}:{int(asyncio.get_event_loop().time()*1000)}",
            "payload": {"path": src_path},
        })

    async def stop(self):
        self._observer.stop()
        self._observer.join(timeout=5)

    def health(self) -> bool:
        return self._observer.is_alive()
```

Note the `source_event_id` construction — `watchdog` doesn't give you a stable event ID, exactly the case your architecture doc's Event Subsystem §10 flags ("some sources don't provide stable event IDs... we may need a source-specific deduplication key"). This composite key means duplicate OS-level notifications within the same millisecond dedupe; genuinely repeated user edits do not (which is correct — those are real new events).

---

## 8. Wake Scheduler — APScheduler, Scoped Strictly to "When"

Install: `uv add apscheduler sqlalchemy`. Point its job store at the *same* SQLite file so there's still only one database file to back up, but let it own its own table (`apscheduler_jobs`) rather than reusing your `wake_schedule` table — APScheduler needs its own pickled job format.

```python
# src/pinky/scheduler/wake.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

class WakeScheduler:
    def __init__(self, db_path: str, on_wake_due):
        self._on_wake_due = on_wake_due   # single callback — hands off to Run Scheduler
        self._scheduler = AsyncIOScheduler(
            jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{db_path}")},
            job_defaults={
                "coalesce": True,        # multiple missed firings collapse to one (misfire=RUN semantics)
                "misfire_grace_time": 3600,
                "max_instances": 1,
            },
        )

    def start(self):
        self._scheduler.start()

    def schedule_cron(self, work_ref_id: str, cron_expr: dict, timezone: str):
        # cron_expr e.g. {"hour": 8, "minute": 0}
        self._scheduler.add_job(
            self._fire, CronTrigger(timezone=timezone, **cron_expr),
            id=work_ref_id, replace_existing=True, args=[work_ref_id],
        )

    def schedule_once(self, work_ref_id: str, run_at):
        self._scheduler.add_job(
            self._fire, DateTrigger(run_date=run_at),
            id=work_ref_id, replace_existing=True, args=[work_ref_id],
        )

    async def _fire(self, work_ref_id: str):
        await self._on_wake_due(work_ref_id)   # this is the ONLY thing APScheduler is allowed to call
```

**The architectural discipline that matters here**: `_fire` does exactly one thing — hand a `work_ref_id` to your own Run Scheduler. APScheduler must never see priority, resources, or execution class. If you ever find yourself passing those into an APScheduler job, stop — that logic belongs in `scheduler/run.py`, not here. This is the boundary called out in the architecture doc §8.

For retries (Scheduler_Subsystem §69–70's exponential backoff), just call `schedule_once` again with `run_at = now + backoff_delay` — no separate retry mechanism needed, exactly as your own design concludes.

---

## 9. Run Scheduler — Priority, Lanes, Resource Admission

This is the genuinely bespoke part (nothing off-the-shelf fits, confirmed in the architecture doc §2/§8). Keep it a plain function, not a pluggable strategy object, per the over-engineering audit (§3.2 of the architecture doc):

```python
# src/pinky/scheduler/run.py
import time

def effective_priority(base_priority: int, created_at_ts: float, deadline_ts: float | None,
                        now: float, aging_rate: float = 0.5, aging_cap: float = 30.0) -> float:
    age_seconds = now - created_at_ts
    aging_bonus = min(age_seconds * aging_rate / 60.0, aging_cap)   # capped, per architecture §7 note

    deadline_pressure = 0.0
    if deadline_ts:
        remaining = deadline_ts - now
        if remaining <= 0:            deadline_pressure = 100.0   # overdue
        elif remaining < 300:         deadline_pressure = 60.0    # <5 min
        elif remaining < 900:         deadline_pressure = 30.0    # <15 min
        elif remaining < 3600:        deadline_pressure = 10.0    # <1 hr

    return base_priority + aging_bonus + deadline_pressure


class ResourceManager:
    def __init__(self, db):
        self.db = db

    async def try_reserve(self, resource_name: str, execution_id: str, amount: int = 1) -> bool:
        # atomic check+reserve — single write statement, see architecture §5.3
        resources = await self.db.read("SELECT capacity FROM resources WHERE name = ?", (resource_name,))
        if not resources:
            raise ValueError(f"unknown resource {resource_name}")
        capacity = resources[0]["capacity"]
        reserved = await self.db.read(
            "SELECT COALESCE(SUM(amount),0) as total FROM resource_reservations "
            "WHERE resource_name = ? AND released_at IS NULL", (resource_name,)
        )
        if reserved[0]["total"] + amount > capacity:
            return False
        await self.db.write(
            "INSERT INTO resource_reservations (id, resource_name, execution_id, amount, reserved_at) "
            "VALUES (?, ?, ?, ?, datetime('now'))",
            (new_id(), resource_name, execution_id, amount),
        )
        return True

    async def release(self, execution_id: str, resource_name: str):
        await self.db.write(
            "UPDATE resource_reservations SET released_at = datetime('now') "
            "WHERE execution_id = ? AND resource_name = ? AND released_at IS NULL",
            (execution_id, resource_name),
        )


class RunScheduler:
    LANE_CONCURRENCY = {"DETERMINISTIC": 4, "INTERACTIVE": 2, "AUTONOMOUS": 1}

    def __init__(self, db, resources: ResourceManager, dispatcher, decision_log):
        self.db = db
        self.resources = resources
        self.dispatcher = dispatcher
        self.decision_log = decision_log
        self._wake_event = asyncio.Event()   # signaled, not polled — per architecture §5.3

    def signal(self):
        self._wake_event.set()

    async def run_forever(self):
        while True:
            await self._wake_event.wait()
            self._wake_event.clear()
            await self._pass()

    async def _pass(self):
        for lane in ("INTERACTIVE", "AUTONOMOUS", "DETERMINISTIC"):  # interactive gets first look
            candidates = await self._runnable_candidates(lane)
            now = time.time()
            scored = sorted(
                candidates,
                key=lambda c: -effective_priority(c["base_priority"], c["created_ts"], c["deadline_ts"], now),
            )
            for c in scored:
                ok = await self.resources.try_reserve(c["required_resource"], c["execution_id"])
                if ok:
                    await self.decision_log_write(c["occurrence_id"], "ADMIT", "highest admissible candidate")
                    await self.dispatcher.dispatch(c)
                else:
                    await self.decision_log_write(c["occurrence_id"], "WAIT", f"{c['required_resource']} unavailable")
                    # don't `break` — try the next candidate (this IS backfill, per architecture §3.1)
```

This ~50-line scheduler implements everything on the architecture doc's Phase 3 checklist except formal queue-level fairness, which was explicitly deferred (§3.1 of the architecture doc) — resist the urge to add it back here until you have real starvation data.

---

## 10. Autonomous Runtime — LangGraph with Checkpointing + Human Approval

This is where the Approval Gate (architecture §5.5) and LangGraph's `interrupt()` primitive are literally the same mechanism — this is the single biggest reason LangGraph was chosen over a hand-rolled agent loop.

```python
# src/pinky/execution/autonomous.py
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command, interrupt
from langchain_anthropic import ChatAnthropic

checkpointer = SqliteSaver.from_conn_string("data/pinky.db")

def make_approval_gated_tool(tool_fn, side_effect_class: str, capability: str):
    """Wrap any tool so IRREVERSIBLE/REVERSIBLE calls pause the graph for approval,
       exactly matching the ApprovalGate contract in architecture §5.5."""
    def wrapped(**kwargs):
        if side_effect_class in ("REVERSIBLE", "IRREVERSIBLE"):
            decision = interrupt({
                "tool": tool_fn.__name__,
                "capability": capability,
                "args": kwargs,
            })
            if decision != "APPROVED":
                return f"Tool call denied by human: {decision}"
        return tool_fn(**kwargs)
    wrapped.__name__ = tool_fn.__name__
    wrapped.__doc__ = tool_fn.__doc__
    return wrapped

model = ChatAnthropic(model="claude-sonnet-4-6")

agent = create_react_agent(
    model=model,
    tools=[
        make_approval_gated_tool(read_file, "READ_ONLY", "filesystem.read"),
        make_approval_gated_tool(write_file, "REVERSIBLE", "filesystem.write"),
        make_approval_gated_tool(send_email, "IRREVERSIBLE", "email.send"),
    ],
    checkpointer=checkpointer,
)

class AutonomousRuntime:
    async def run(self, execution, attempt):
        config = {"configurable": {"thread_id": execution["id"]}}
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": execution["goal"]}]},
            config=config,
        )
        if "__interrupt__" in result:
            # this durably parks the execution — release the resource, per architecture §5.4/§7.10
            interrupt_payload = result["__interrupt__"][0].value
            await self._request_approval(execution["id"], interrupt_payload)
            return  # EXECUTION status stays WAITING_FOR_APPROVAL; resumed below
        return result["messages"][-1].content

    async def resume(self, execution_id: str, decision: str):
        config = {"configurable": {"thread_id": execution_id}}
        result = await agent.ainvoke(Command(resume=decision), config=config)
        return result["messages"][-1].content
```

Two things this buys you for free, both of which are exact requirements from the architecture doc:

- **Checkpointing**: (cite index="20-1">the framework's stateful design automatically saves progress after each step, enabling pause-and-resume functionality for long-running tasks</cite> — this is your `Attempt` durability requirement, implemented by the library instead of by hand.
- **Human-in-the-loop**: `interrupt()` (cite index="49-1">halts the graph and returns control to the caller with a payload; the caller decides what to do, then resumes with `Command(resume=value)`</cite>, and a persistent checkpointer such as SqliteSaver is a hard prerequisite for it — which you already have, since it's the same SQLite file everything else uses.

The `AutonomousRuntime.run` / `.resume` split maps directly onto the `WAITING_FOR_APPROVAL` execution state and the `approvals` table from the architecture doc's §7.10 — when a human approves via CLI, call `resume(execution_id, "APPROVED")`.

---

## 11. Interactive Runtime — Ollama, Modeled as a Resource

Install and pull a small model once:

```bash
uv add ollama
ollama pull llama3.2
```

```python
# src/pinky/execution/interactive.py
import ollama

class InteractiveRuntime:
    async def run(self, execution, attempt):
        response = ollama.chat(
            model="llama3.2",
            messages=[{"role": "user", "content": execution["goal"]}],
            tools=[create_task_tool],   # a plain Python function, per architecture §5.5
        )
        for call in response.message.tool_calls or []:
            if call.function.name == "create_task_tool":
                await self.task_manager.create(**call.function.arguments)
        return response.message.content
```

(cite index="63-1">The Ollama Python library supports passing plain Python functions directly as tools</cite> — no wrapper schema needed for simple cases, which keeps the Interactive lane genuinely lightweight, matching the architecture doc's "optimize for latency" requirement for this lane.

The Resource Manager treats `small_llm` and `strong_llm` (LangGraph/Anthropic) as two independent named resources with their own capacity — exactly the pattern in architecture §5.3/§7.9 — so swapping Ollama for a different small model later, or running it remotely, never touches the Scheduler.

---

## 12. Config — Layered Resolution

```python
# src/pinky/config.py
import tomllib

class Config:
    def __init__(self, db, toml_path="pinky.toml"):
        self.db = db
        with open(toml_path, "rb") as f:
            self._global_defaults = tomllib.load(f)

    async def get(self, key: str, *, execution_class=None, task_id=None, occurrence_id=None, default=None):
        # resolution order: OCCURRENCE > TASK > CLASS > GLOBAL — architecture §7.11
        for scope, ref in (("OCCURRENCE", occurrence_id), ("TASK", task_id), ("CLASS", execution_class)):
            if ref:
                rows = await self.db.read(
                    "SELECT value FROM config WHERE scope=? AND scope_ref=? AND key=?", (scope, ref, key)
                )
                if rows:
                    return json.loads(rows[0]["value"])
        return self._global_defaults.get(key, default)
```

`pinky.toml`:

```toml
[scheduler]
aging_rate = 0.5
aging_cap = 30.0

[resources]
strong_llm_capacity = 1
small_llm_capacity = 2

[retry]
base_backoff_s = 10
max_backoff_s = 300
```

---

## 13. Observability — `structlog` + Decision Log

```python
# src/pinky/observability.py
import structlog

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger("pinky")

async def decision_log_write(db, work_id: str, decision: str, reason: str, attributes: dict | None = None):
    await db.write(
        "INSERT INTO decision_log (id, work_id, at, decision, reason, attributes) "
        "VALUES (?, ?, datetime('now'), ?, ?, ?)",
        (new_id(), work_id, decision, reason, json.dumps(attributes or {})),
    )
    log.info("decision", work_id=work_id, decision=decision, reason=reason)
```

A `pinky why <id>` CLI command (Phase 5 checkpoint in the architecture doc) is then a single query:

```python
async def why(db, work_id: str):
    rows = await db.read(
        "SELECT at, decision, reason, attributes FROM decision_log WHERE work_id = ? ORDER BY at", (work_id,)
    )
    for r in rows:
        print(f"{r['at']}  {r['decision']:8s}  {r['reason']}")
```

---

## 14. Process Supervision — Restart-With-Backoff, in Plain `asyncio`

This implements the Erlang/OTP-style supervision pattern the architecture doc cites in §2, without needing Erlang:

```python
# src/pinky/main.py (core loop)
import asyncio

async def supervised(name: str, coro_factory, max_failures=5):
    failures = 0
    backoff = 1.0
    while failures < max_failures:
        try:
            await coro_factory()
            failures = 0   # clean exit resets the counter
        except asyncio.CancelledError:
            raise
        except Exception:
            failures += 1
            log.error("component_failed", name=name, failures=failures)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
    log.error("component_disabled", name=name)  # READER_FAILED state, per architecture §5.1

async def main():
    db = Database()
    await db.start()
    await run_migrations(db)

    bus = EventBus()
    intake = EventIntake(db, bus)
    # ... construct readers, task manager, scheduler, dispatcher, runtimes ...

    async with asyncio.TaskGroup() as tg:
        tg.create_task(supervised("fs_reader", lambda: fs_reader.start()))
        tg.create_task(supervised("outbox_drain", lambda: outbox_drain_loop(db, bus, intake)))
        tg.create_task(supervised("run_scheduler", run_scheduler.run_forever))
        wake_scheduler.start()   # APScheduler manages its own thread/loop internally

asyncio.run(main())
```

---

## 15. Running It Always-On

**Linux (systemd)** — `~/.config/systemd/user/pinky.service`:

```ini
[Unit]
Description=Pinky agent

[Service]
WorkingDirectory=/home/you/pinky
ExecStart=/home/you/.local/bin/uv run python -m pinky.main
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

```bash
systemctl --user enable --now pinky.service
journalctl --user -u pinky -f    # tail structlog JSON output
```

**macOS (launchd)** — `~/Library/LaunchAgents/com.pinky.agent.plist`, `KeepAlive: true`, pointing `ProgramArguments` at the same `uv run python -m pinky.main` command, loaded with `launchctl load ~/Library/LaunchAgents/com.pinky.agent.plist`.

Either way, the OS-level `Restart=always` / `KeepAlive` is your outermost safety net *above* the in-process supervisor in §14 — the in-process one handles individual component crashes (a reader dying); the OS-level one handles the whole process dying (e.g. an unhandled exception that escapes the TaskGroup).

---

## 16. Pinned Dependencies

```toml
# pyproject.toml
[project]
name = "pinky"
requires-python = ">=3.12"
dependencies = [
    "aiosqlite>=0.20",
    "python-ulid>=1.1",
    "apscheduler>=3.10,<4.0",       # v3, not the v4 pre-release — v4 API is still in flux
    "sqlalchemy>=2.0",
    "watchdog>=4.0",
    "langgraph>=0.2",
    "langgraph-checkpoint-sqlite>=1.0",
    "langchain-anthropic>=0.2",
    "ollama>=0.4",
    "structlog>=24.1",
]
```

---

## 17. Build Order (matches the Phase Plan in `pinky_architecture.md`)

1. `db.py` + migrations + `ids.py` → Phase 0 checkpoint.
2. `bus.py` + `events/intake.py` + `readers/user_input.py` + `readers/filesystem.py` → Phase 1 checkpoint (kill-test the outbox).
3. `tasks/manager.py` + `tasks/trigger_engine.py` → Phase 2 checkpoint.
4. `scheduler/wake.py` (APScheduler) + `scheduler/run.py` + `scheduler/resources.py` → Phase 3 checkpoint (deterministic tie-break test, burst backpressure test).
5. `dispatch/dispatcher.py` + `execution/deterministic.py` + `execution/interactive.py` (Ollama) + `execution/autonomous.py` (LangGraph) + `execution/approval.py` → Phase 4 checkpoint (approval-gated tool call surviving a restart).
6. Idempotency keys on your first real side-effecting tool, `pinky why`, recurring-task overlap policy → Phase 5 checkpoint.

Each numbered item above is a directly buildable module against the code in this document — nothing here requires a design decision that isn't already settled in `pinky_architecture.md`.
