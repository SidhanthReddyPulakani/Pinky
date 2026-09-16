Good. I’ve read the four Markdown documents in the Pinky repository:

* `Event Layer`
* `Event Task Execution`
* `Events.md`
* `Sibling Layer.md`

I’m treating these as **research notes from our earlier design discussion**, not as architecture that is already fixed. There is some repetition and a few ideas evolved between documents, so I’ve consolidated them below into a clean baseline rather than pretending every earlier statement is equally final. The central model is consistent across the notes: events are the connective tissue; Tasks represent persistent responsibility; Executions are concrete attempts; and deterministic, interactive, and autonomous are sibling execution modes.

# Pinky — Consolidated Architectural Findings

## 1. The fundamental mental model

Pinky is **not primarily an LLM application**.

It is an **event-driven execution system that can use LLMs as reasoning resources**.

The hierarchy is:

```text
                         EVENTS
                            │
                            ▼
                          TASKS
                            │
                            ▼
                       EXECUTIONS
                            │
                   ┌────────┼────────┐
                   ▼        ▼        ▼
             DETERMINISTIC INTERACTIVE AUTONOMOUS
                              │        │
                           Small LLM  Strong LLM
```

The critical separation is:

```text
Event     = something happened
Task      = something needs to be accomplished
Execution = an attempt to accomplish it
Agent     = reasoning capability operating within an execution
LLM       = reasoning engine
Tool      = capability/action provider
```

This separation is repeatedly established in the notes and should be preserved.

---

# 2. Pinky is event-driven, not LLM-driven

The runtime should remain operational even when **no LLM is doing anything**.

That means Pinky can be:

```text
RUNNING
```

while:

```text
LLM = idle
```

or even:

```text
LLM = unloaded
```

The persistent system is:

```text
Event infrastructure
Task infrastructure
Scheduler
Execution state
Persistence
```

The LLM is invoked only when an Execution actually requires reasoning. This distinction was one of the strongest conclusions in the research notes.

So an "always-on agent" is more accurately:

> **An always-available execution runtime whose reasoning resources are activated on demand.**

---

# 3. Three sibling execution modes

This has evolved slightly from the earliest "small LLM vs big LLM" idea.

We should not define the system as:

```text
Human → Small
Everything else → Strong
```

Instead:

```text
DETERMINISTIC
INTERACTIVE
AUTONOMOUS
```

are **three sibling execution modes**.

### Deterministic

No reasoning required.

Examples:

```text
send notification
save file
run scheduled script
update state
```

### Interactive

Human-facing execution.

Default reasoning resource:

```text
Small LLM
```

Typical responsibilities:

```text
understand user
answer
clarify
schedule
create tasks
cancel tasks
delegate
```

### Autonomous

Longer-running task execution.

Default reasoning resource:

```text
Strong LLM
```

Typical responsibilities:

```text
plan
retrieve
reason
use tools
observe
recover
complete
```

The important part is that **execution mode and model choice are not identical concepts**. A future autonomous task could use a small model, and an unusually complex interactive request could escalate to the stronger model.

---

# 4. Event

Our consolidated definition:

> **An Event is an immutable, persistable fact representing something that occurred, was requested, or became true, and which may cause the system to evaluate whether state or work should change.**

The key properties are:

```text
immutable
identified
timestamped
causally traceable
persistable
machine-readable
```

The event itself does **not** decide what to do.

For example:

```text
FILE_CREATED
```

doesn't mean:

```text
run the LLM
```

It simply means:

```text
a file was created
```

Different consumers may independently react.

The notes emphasize this fact-versus-action distinction repeatedly.

---

# 5. Event structure

The current conceptual envelope is:

```text
Event
├── id
├── type
├── source
├── occurred_at
├── recorded_at
├── correlation_id
├── causation_id
├── payload
└── metadata
```

### `id`

Globally unique event identity.

### `type`

Semantic event type:

```text
USER_MESSAGE_RECEIVED
FILE_CREATED
TASK_CREATED
EXECUTION_COMPLETED
```

### `source`

Where it originated:

```text
human
scheduler
filesystem
tool
agent
system
external_service
```

### `occurred_at`

When the event actually happened.

### `recorded_at`

When Pinky persisted/accepted it.

### `correlation_id`

Which larger operation it belongs to.

### `causation_id`

Which specific event caused it.

### `payload`

Event-specific information.

### `metadata`

Non-semantic infrastructure/trace information.

This model is documented in the Event Layer findings.

---

# 6. Event ≠ Command

This should become a hard architectural boundary.

A command means:

```text
"Please do this."
```

An event means:

```text
"This happened."
```

Example:

```text
CREATE_TASK
```

is a command.

After successful handling:

```text
TASK_CREATED
```

is an event.

Likewise:

```text
EXECUTION_CANCEL_REQUESTED
```

is preferable to pretending that:

```text
CANCEL_EXECUTION
```

is itself an event.

The command/event distinction prevents the Event Bus from turning into a vague RPC mechanism.

---

# 7. Event history

Events should form a durable history.

For example:

```text
USER_MESSAGE_RECEIVED
        ↓
TASK_CREATED
        ↓
SCHEDULE_CREATED
        ↓
SCHEDULE_DUE
        ↓
EXECUTION_CREATED
        ↓
EXECUTION_STARTED
        ↓
TOOL_COMPLETED
        ↓
EXECUTION_COMPLETED
```

Events are therefore not merely transient messages.

They provide:

```text
history
auditability
causality
recovery information
debugging
observability
```

The notes specifically favored immutable event history while keeping current state separately materialized.

---

# 8. Event storage vs current state

We should distinguish:

```text
EVENT HISTORY
```

from:

```text
CURRENT STATE
```

For example:

```text
Event History
    ↓
TASK_CREATED
TASK_PAUSED
TASK_RESUMED
...
    ↓
Task Projection
    ↓
Task.status = ACTIVE
```

This is the **hybrid/event-sourced direction** that emerged in the notes:

> events are authoritative historical facts; current Task/Execution state is a materialized representation for efficient access.

We should not force every read to reconstruct an entity from thousands of events.

---

# 9. Event delivery

Persistence and delivery are different.

Conceptually:

```text
Event received
     ↓
validate
     ↓
persist
     ↓
publish/dispatch
     ↓
consumer
```

If a consumer crashes:

```text
event still exists
```

and can be retried.

This leads naturally to:

```text
idempotent consumers
deduplication
retryable delivery
```

We should assume at-least-once delivery rather than build the architecture around an unrealistic guarantee of exactly-once execution.

---

# 10. Event ordering

We should **not** assume one global total event order.

Instead, ordering matters within appropriate streams/correlations.

For example:

```text
Task A:
A1 → A2 → A3

Task B:
B1 → B2
```

A and B can progress independently.

Causation and correlation should help establish meaningful relationships without forcing the whole system into a single serialized event stream.

---

# 11. Event taxonomy

The research ultimately converged on a broader taxonomy than the first nine categories.

The current full classification is:

```text
1. Human
2. Temporal
3. System
4. Application
5. External
6. Device
7. Network
8. File/Data
9. Task
10. Execution
11. Agent/LLM
12. Condition/State
13. Recovery/Lifecycle
14. Composite
```

These are **categories**, not necessarily fourteen separate implementations.

They answer:

> Who/what produced this kind of event?

The notes explicitly expanded the original taxonomy to this 14-category model.

---

# 12. Not every event should invoke an LLM

This is one of the strongest conclusions.

For example:

```text
TIMER_EXPIRED
```

could cause:

```text
SEND_NOTIFICATION
```

with no LLM.

Similarly:

```text
FILE_CREATED
```

could trigger:

```text
BACKUP_FILE
```

deterministically.

Or:

```text
FILE_CREATED
```

could trigger:

```text
SUMMARIZE_DOCUMENT
```

using an LLM.

Therefore:

```text
Event
 ↓
Trigger / Task
 ↓
Execution policy
 ↓
LLM requirement
```

The event itself should not contain something like:

```text
requires_llm = true
```

This became an explicit correction in the research.

---

# 13. Task

Our consolidated definition:

> **A Task is a persistent responsibility describing an outcome the system is expected to accomplish, together with the conditions, constraints, and policies governing when and how it should be pursued.**

Task is deliberately more durable than an Execution.

Example:

```text
Task:
Every morning at 08:00, analyze my calendar.
```

That task exists for months.

Its executions are individual occurrences:

```text
Task T1
 ├── Execution E1 — Sept 15
 ├── Execution E2 — Sept 16
 ├── Execution E3 — Sept 17
 └── ...
```

This distinction is fundamental.

---

# 14. Task describes WHAT, not HOW

This is another hard principle.

Good:

```text
Goal:
Identify important emails from the last 24 hours.

Constraints:
Read-only.

Output:
Summary.
```

Bad:

```text
1. Call Gmail
2. Fetch messages
3. Filter messages
4. Send prompt
5. Summarize
```

The second is an execution plan.

The autonomous Execution should be able to determine **how** to achieve the Task's outcome.

---

# 15. Task structure

The consolidated conceptual Task is:

```text
Task
├── id
├── goal
├── status
├── creator
├── trigger
├── execution_policy
├── constraints
├── priority
├── deadline
├── dependencies
├── input
├── output_spec
├── created_at
└── updated_at
```

The exact final schema belongs to Phase 1 planning.

---

# 16. Task triggers

A Task may become eligible through different mechanisms:

```text
schedule
event
condition
dependency
manual
```

Examples:

```text
daily at 08:00
```

or:

```text
when FILE_CREATED
```

or:

```text
when Task A completes
```

or:

```text
when battery < 10%
```

This means **Schedule is not the same thing as Task**.

Schedule is one type of trigger/policy attached to a Task.

---

# 17. Task state vs Execution state

This is another important boundary.

A Task might be:

```text
ACTIVE
```

while an Execution is:

```text
WAITING
```

or:

```text
FAILED
```

or:

```text
RUNNING
```

The Task represents the persistent responsibility.

The Execution represents the current attempt.

Therefore they need independent lifecycles.

---

# 18. Task lifecycle

Current conceptual lifecycle:

```text
DRAFT
ACTIVE
PAUSED
BLOCKED
COMPLETED
CANCELLED
EXPIRED
```

I would keep:

```text
QUEUED
RUNNING
WAITING
```

out of the Task lifecycle unless Phase 1 reveals a strong reason otherwise; those are more naturally Execution states.

That was one of the refinements that emerged during discussion.

---

# 19. Recurring Tasks and Occurrences

A recurring Task should not create a new Task every time.

Instead:

```text
Task
 │
 ├── Schedule
 │
 ├── Occurrence 1 → Execution 1
 ├── Occurrence 2 → Execution 2
 └── Occurrence 3 → Execution 3
```

The **Occurrence** represents a particular scheduled instance of the persistent Task.

This is especially useful for:

```text
daily
weekly
monthly
recurring background work
```

This concept emerged during the Task design discussion and should remain part of the planning model.

---

# 20. Execution

Our consolidated definition:

> **An Execution is a concrete runtime instance representing one attempt to fulfill a Task under a particular set of conditions.**

Execution is where the actual agent runtime lives.

```text
Task
 ↓
Execution
 ↓
steps
 ↓
tool/model/wait
 ↓
result
```

The Execution persists through:

```text
LLM calls
tool calls
waiting
human intervention
retries
failures
recovery
```

---

# 21. The LLM is not the Execution

This is perhaps the most important runtime insight.

Bad conceptual model:

```text
Execution = LLM process
```

Correct:

```text
Execution
├── persistent state
├── current progress
├── waiting condition
├── attempts
├── context
└── reasoning operations
       │
       └── LLM
```

The LLM can disappear between reasoning calls.

The Execution still exists.

This is how long-running autonomy becomes practical on local hardware.

---

# 22. Execution lifecycle

Current conceptual state machine:

```text
CREATED
   ↓
QUEUED
   ↓
RUNNING
   │
   ├── WAITING
   ├── PAUSED
   ├── FAILED
   └── ...
        ↓
     retry
        ↓
     QUEUED
```

Terminal states:

```text
COMPLETED
FAILED
CANCELLED
```

Some distinctions may be refined during implementation.

---

# 23. Waiting is first-class

An Execution can legitimately be:

```text
WAITING
```

because it needs:

```text
time
human input
another Task
external response
resource
event
```

It should **not** implement waiting as:

```python
sleep(86400)
```

Instead:

```text
Execution
status = WAITING
wake_condition = ...
persist
```

Then later:

```text
wake event
 ↓
resume Execution
```

This is a central idea in durable workflow systems and is directly relevant to Pinky.

---

# 24. Execution Steps

Execution consists of logical steps:

```text
Execution
│
├── Context Assembly
├── LLM Call
├── Tool Call
├── Observation
├── LLM Call
├── Human Wait
└── Completion
```

A step is **not necessarily an LLM call**.

Possible step kinds include:

```text
LLM
TOOL
WAIT
HUMAN_INPUT
VALIDATION
CHECKPOINT
COMPLETION
```

This allows the runtime to remain model-independent.

---

# 25. Agent loop inside Execution

The autonomous reasoning loop is roughly:

```text
Execution
   ↓
Context
   ↓
LLM
   ↓
decision
   ├── final
   ├── tool
   ├── wait
   ├── human input
   └── other control decision
```

If tool:

```text
LLM
 ↓
Tool Request
 ↓
Policy/Authorization
 ↓
Tool
 ↓
Observation
 ↓
LLM
```

This continues until:

```text
complete
wait
fail
cancel
```

OpenHands, OpenAI Agents SDK, and LangGraph each expose variations of these concepts, but Pinky should first define its own runtime semantics instead of inheriting framework assumptions.

---

# 26. Runtime authority

A major principle emerged:

> **The LLM may decide what should happen next; the runtime decides whether and how that decision is executed.**

So:

```text
LLM says:
send_email(...)
```

does not directly execute the side effect.

Instead:

```text
LLM decision
     ↓
Execution Runtime
     ↓
authorization
     ↓
constraints
     ↓
approval?
     ↓
Tool
```

The same applies to:

```text
WAIT
RETRY
CREATE_TASK
CANCEL
```

The LLM expresses intent.

The runtime enforces it.

---

# 27. Human-in-the-loop

An autonomous Execution can reach:

```text
WAITING_FOR_HUMAN
```

and persist itself.

Example:

```text
Strong LLM
 ↓
request approval
 ↓
Execution WAITING
 ↓
checkpoint
```

Then:

```text
USER_APPROVAL
 ↓
Execution resumes
```

The small interactive LLM can serve as the human-facing side of this interaction, but the Execution itself remains owned by the Autonomous plane.

This is a particularly nice consequence of the three-sibling design.

---

# 28. Execution attempts

We should distinguish:

```text
Task
 ↓
Occurrence
 ↓
Execution
 ↓
Attempt
```

For example:

```text
Task T1
Occurrence O17
Execution E42

Attempt 1 → LLM timeout
Attempt 2 → API timeout
Attempt 3 → success
```

This is better than creating a new Task for every retry.

---

# 29. Failure semantics

Pinky should assume that failures can occur after an external side effect has actually happened.

Example:

```text
send_email()
 ↓
remote server accepts
 ↓
Pinky crashes
```

On restart, Pinky may not know whether the operation completed.

Therefore the design should prefer:

```text
idempotency
deduplication
retry policies
reconciliation
```

rather than assuming exactly-once external side effects.

This is an important reliability principle from the Execution research.

---

# 30. Scheduler

The Scheduler is **not**:

```text
cron wrapper
```

It is better defined as:

> **The Scheduler determines when eligible work becomes runnable and which runnable work should receive execution resources.**

This means:

```text
Scheduler
≠ Task Manager
≠ Execution Engine
≠ LLM
≠ Queue
```

though all interact closely.

---

# 31. Scheduler responsibilities

Conceptually:

```text
Scheduler
├── temporal scheduling
├── wake-up management
├── eligibility
├── dependency awareness
├── priority
├── queueing
├── concurrency
├── resource awareness
├── retry timing
├── expiration
└── dispatch coordination
```

Not all need to be separate classes/processes.

These are **responsibilities**.

---

# 32. Temporal scheduling

Handles:

```text
at 08:00
in 30 minutes
daily
weekly
monthly
deadline
delay
```

The scheduler should not constantly scan every Task.

Instead it should maintain relevant future wake-up points.

---

# 33. Event-based scheduling

A Task can become eligible because of an event:

```text
EMAIL_RECEIVED
     ↓
trigger matcher
     ↓
Task eligible
```

Similarly:

```text
TASK_COMPLETED
     ↓
dependency satisfied
     ↓
Task eligible
```

Or:

```text
NETWORK_AVAILABLE
     ↓
waiting execution becomes eligible
```

Thus time and events are two different wake mechanisms.

---

# 34. Condition scheduling

Some Tasks are based on conditions:

```text
CPU < 20%
battery < 10%
user idle > 30 min
calendar is free
```

The condition subsystem may need polling when the environment offers no native event.

But polling belongs at the **observation layer**, not inside arbitrary Tasks.

Conceptually:

```text
Observation
 ↓
Condition Engine
 ↓
Condition became true
 ↓
Event
```

---

# 35. Eligibility

This deserves to be explicit.

A Task may have all of these:

```text
time reached
dependencies satisfied
task active
condition satisfied
resource policy satisfied
```

Only then is it eligible.

Conceptually:

```text
Task
 ↓
Eligibility Engine
 ├── time
 ├── dependency
 ├── condition
 ├── policy
 └── state
      ↓
   ELIGIBLE
```

The scheduler should not treat "trigger occurred" as equivalent to "execution must start."

---

# 36. Queueing

Once work is eligible:

```text
ELIGIBLE
   ↓
RUNNABLE
   ↓
QUEUE
```

The queue holds **work waiting for resources**.

Priority decides **which work gets selected**.

These are separate concepts.

---

# 37. Priority

We should not reduce everything immediately to:

```text
HIGH
MEDIUM
LOW
```

The design should support factors such as:

```text
urgency
importance
deadline pressure
user initiated
waiting age
resource cost
execution class
```

Then derive:

```text
effective priority
```

The exact formula should be a Phase 1 planning decision.

---

# 38. Priority aging

To prevent starvation:

```text
waiting longer
     ↓
effective priority rises
```

This is particularly important for low-priority autonomous work.

Otherwise a steady stream of interactive work could prevent background Tasks from ever executing.

---

# 39. Preemption

Priority and preemption are different.

A high-priority item may mean:

```text
run next
```

rather than:

```text
kill current execution immediately
```

Possible preemption semantics:

```text
RUN_NEXT
PREEMPT_AT_SAFE_POINT
PAUSE
CANCEL
FORCE_CANCEL
```

Preemption should occur only at appropriate execution boundaries where possible.

---

# 40. Resource-aware scheduling

Pinky is a local system, so resource contention matters.

Example:

```text
Deterministic
Small LLM
Strong LLM
Network
CPU
GPU
```

The scheduler should not blindly start five strong-model executions because five Tasks are runnable.

Instead:

```text
Runnable
 ↓
Resource availability
 ↓
Concurrency policy
 ↓
Dispatch
```

This becomes especially important if the strong model is occupying most of a GPU.

---

# 41. Multiple lanes

I would conceptually use:

```text
                     SCHEDULER
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
     Interactive      Autonomous    Deterministic
        Lane             Lane           Lane
```

but **one global scheduling policy** rather than three isolated schedulers.

That allows interactive work to receive appropriate priority while still allowing global resource coordination.

---

# 42. Scheduler persistence

The persistent database/state should be authoritative.

The in-memory queue should be derived.

```text
Persistent state
      ↓
Scheduler recovery
      ↓
rebuild timers
      ↓
rebuild runnable queues
```

That way a scheduler crash doesn't erase Tasks.

---

# 43. Misfires

We need a policy for when a scheduled time passes while Pinky is offline.

For example:

```text
scheduled = 08:00
system comes back = 10:00
```

Possible policies:

```text
RUN_IMMEDIATELY
SKIP
RUN_IF_WITHIN_WINDOW
RESCHEDULE
```

This should be Task/schedule policy.

Different Tasks legitimately need different behavior.

---

# 44. Expiration

A Task may have:

```text
scheduled_at
expires_at
```

These are different.

Example:

```text
"Remind me to join the 10 AM meeting."
```

At 11 AM the Task may be meaningless and should be expired rather than executed.

---

# 45. Recurrence overlap

If recurring Task A is still executing when the next occurrence arrives, we need a policy:

```text
SKIP
QUEUE
PARALLEL
DELAY
```

Again, this belongs in scheduling policy rather than being hardcoded globally.

---

# 46. Retry and backoff

Failures should generally use policy-controlled retries:

```text
attempt 1
 ↓
failure
 ↓
backoff
 ↓
attempt 2
 ↓
failure
 ↓
backoff
 ↓
attempt 3
```

The scheduler manages when the next attempt becomes runnable.

The Execution system manages the actual attempt.

---

# 47. Recovery

Pinky must be designed around restartability.

On startup:

```text
SYSTEM_STARTED
      ↓
RECOVERY
      ↓
load Tasks
load schedules
load incomplete Executions
load waiting conditions
      ↓
reconstruct runnable state
      ↓
scheduler ready
```

This was consistently identified as necessary in the research.

---

# 48. Event Readers vs Event Intake

These are separate.

### Event Reader

Knows how to observe one external source.

Examples:

```text
KeyboardReader
MicrophoneReader
FileSystemReader
GmailReader
CalendarReader
SystemReader
SchedulerReader
```

Its job:

> **Observe a source and produce events.**

### Event Intake

Knows how Pinky accepts events.

Its job:

```text
validate
normalize
assign/verify identity
timestamp
deduplicate
persist
publish
```

Therefore:

```text
GmailReader
    ↓
source-specific event
    ↓
Event Intake
    ↓
canonical Pinky Event
```

This is a very important boundary for Phase 1.

---

# 49. Event Router

After persistence:

```text
Event
 ↓
Event Router
```

The Router determines what kind of response is appropriate.

Potential outcomes:

```text
ignore/store only
deterministic action
interactive execution
autonomous execution
task activation
wake existing execution
runtime control
```

The Router itself should be primarily deterministic.

It should **not require the LLM for ordinary routing**.

---

# 50. Trigger Engine

The Trigger Engine answers:

> **Does this event activate any Task?**

For example:

```text
FILE_CREATED
    ↓
Trigger Matcher
    ↓
Task A
Task B
Task C
```

One event can activate multiple Tasks.

One Task can respond to multiple event types.

---

# 51. Task Manager

The Task Manager owns the Task lifecycle.

Agents should **request** Task changes.

They should not directly mutate Task state.

For example:

```text
Interactive Agent
    ↓
CREATE_TASK command
    ↓
Task Manager
    ↓
TASK_CREATED event
```

Likewise:

```text
Autonomous Agent
    ↓
CREATE_TASK
    ↓
Task Manager
```

One canonical owner.

---

# 52. Execution Manager

The Execution Manager owns:

```text
create execution
queue execution
start
pause
resume
wait
cancel
retry
recover
complete
```

Again, the agent should not directly own those transitions.

The agent operates **inside** an Execution.

---

# 53. Dispatcher

The Dispatcher sits between scheduling and actual execution resources.

Conceptually:

```text
Runnable work
     ↓
Dispatcher
     ↓
Execution mode
     ↓
resource/model selection
     ↓
Execution starts
```

This is where:

```text
deterministic
interactive
autonomous
```

becomes operational.

---

# 54. Model Router

Model choice should remain separate from Task identity.

For example:

```text
Execution Policy
       ↓
reasoning requirement = HIGH
       ↓
Model Router
       ↓
Strong Model
```

or:

```text
reasoning requirement = LOW
       ↓
Small Model
```

This means Pinky isn't architecturally tied to:

```text
4B
30B
Qwen
Ollama
```

or any other particular implementation.

---

# 55. Communication between Interactive and Autonomous

The two planes should **not talk to each other through arbitrary LLM prompts**.

Instead:

```text
Interactive
    ↓
structured Task
    ↓
Task System
    ↓
Autonomous
```

and:

```text
Autonomous
    ↓
structured result/event
    ↓
Interactive
```

This creates loose coupling.

Example:

```text
TASK_CREATED
        ↓
Autonomous Execution
        ↓
TASK_COMPLETED
        ↓
Interactive Plane
        ↓
human-facing response
```

This is one of the strongest ideas in the sibling-layer design.

---

# 56. Interactive and autonomous are not isolated worlds

The user may start something that needs autonomous work:

```text
USER
 ↓
Interactive
 ↓
DELEGATE
 ↓
Task
 ↓
Autonomous
```

The autonomous Execution may later need the user:

```text
Autonomous
 ↓
HUMAN_INPUT_REQUIRED
 ↓
Interactive
 ↓
USER
 ↓
answer
 ↓
Autonomous resumes
```

So the relationship is:

```text
Interactive ⇄ Task System ⇄ Autonomous
```

not:

```text
Interactive   Autonomous
      ↘       ↙
       direct communication
```

---

# 57. Deterministic is a genuine sibling

We should not think of deterministic execution as some lesser version of the autonomous system.

It is a first-class execution mode.

For example:

```text
SCHEDULE_DUE
 ↓
Deterministic Execution
 ↓
Send notification
```

There is no reason for an LLM to exist in that path.

This is important for speed, predictability, and resource efficiency.

---

# 58. The complete Active Layer

The consolidated architecture is now roughly:

```text
                           EVENT SOURCES
                                │
                                ▼
                         ┌──────────────┐
                         │ EVENT READERS│
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │ EVENT INTAKE │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │ EVENT STORE  │
                         └──────┬───────┘
                                │
                                ▼
                         ┌──────────────┐
                         │ EVENT ROUTER │
                         └──────┬───────┘
                                │
                    ┌───────────┴───────────┐
                    │                       │
                    ▼                       ▼
              DIRECT ACTION            TRIGGER ENGINE
                                            │
                                            ▼
                                          TASK
                                            │
                              ┌─────────────┴─────────────┐
                              │                           │
                         Triggered                    Scheduled
                              │                           │
                              └─────────────┬─────────────┘
                                            ▼
                                      SCHEDULER
                                            │
                                   ┌────────┴────────┐
                                   ▼                 ▼
                              Priority            Queue
                                   │                 │
                                   └────────┬────────┘
                                            ▼
                                       DISPATCHER
                                            │
                                            ▼
                                        EXECUTION
                                            │
                              ┌─────────────┼─────────────┐
                              ▼             ▼             ▼
                        DETERMINISTIC  INTERACTIVE   AUTONOMOUS
                                              │             │
                                           Small LLM     Strong LLM
```

Around this:

```text
Persistence
Recovery
Condition Engine
Resource Manager
Policy Engine
Observability
```

---

# 59. The central feedback loop

The entire system is cyclic:

```text
EVENT
  ↓
TASK / DIRECT ACTION
  ↓
EXECUTION
  ↓
RESULT / STATE CHANGE
  ↓
EVENT
```

So Pinky is essentially a **closed-loop event-driven execution system**.

The LLM is not the center of the architecture.

The **event/execution cycle is**.

---

# 60. What is now established vs what is still open

This distinction is important before Phase 1.

## Strong conclusions

I consider these sufficiently established to carry into architecture:

```text
Event ≠ Task ≠ Execution
Event = immutable fact
Task = persistent responsibility
Execution = concrete attempt
LLM = execution resource
Agent = reasoning component inside execution
Scheduler = deterministic scheduling subsystem
Three sibling execution modes
Event-driven runtime
Persistent event history
Persistent Task state
Persistent Execution state
LLM invoked on demand
Structured inter-plane communication
At-least-once/idempotent mindset
Recovery is first-class
Waiting is first-class
```

## Still open

These should be decided during Phase 1 architecture:

```text
Exact event schema
Exact Task schema
Exact Execution schema

Event Store technology
Event Bus technology
Database technology

Whether to use full event sourcing or hybrid persistence
Exact scheduler data structures
Exact priority formula
Priority classes
Preemption policy
Concurrency model
Resource model
Queue topology
Wake-up mechanism
Condition engine design
Event subscription model
Execution checkpoint format
Retry semantics
Recovery semantics
Model lifecycle manager
Process boundaries
Thread/async boundaries
```

Those are **architectural decisions**, not research conclusions.

---

# 61. The Phase 1 scope is now very clear

Based on everything we've established, Phase 1 should focus on exactly the area you described:

```text
                    PINKY PHASE 1
                  ACTIVE / INPUT SIDE
                           │
          ┌────────────────┼────────────────┐
          │                │                │
     EVENT SOURCES      CORE STATE       EXECUTION
          │                │                │
    Event Readers     Event Store       Execution
    Event Intake      Tasks             Dispatcher
    Normalization     Triggers          Deterministic
    Classification    Scheduler         Interactive
    Event Router      Priority           Autonomous
                     Queue
                     Recovery
```

Or more linearly:

```text
Event Readers
      ↓
Event Intake
      ↓
Normalization
      ↓
Event Storage
      ↓
Event Routing
      ↓
Trigger Matching
      ↓
Task System
      ↓
Scheduler
      ↓
Priority / Queue
      ↓
Dispatcher
      ↓
Execution Manager
      ↓
Deterministic / Interactive / Autonomous
```

That is a **very good Phase 1 boundary**.

---

# 62. One important architectural correction I'd carry forward

There is one thing I would explicitly change from the earliest drawings.

We initially tended to place:

```text
Event Router
    ↓
Deterministic / Interactive / Autonomous
```

directly.

The more complete model is:

```text
Event
 ↓
Router
 ↓
Task / Direct Action / Execution Wake
 ↓
Scheduler / Dispatcher
 ↓
Execution Mode
```

because **an event isn't necessarily an execution request**.

Sometimes it:

```text
updates state
```

Sometimes:

```text
activates a Task
```

Sometimes:

```text
wakes an existing Execution
```

Sometimes:

```text
causes an immediate deterministic action
```

Sometimes:

```text
does nothing except remain in history
```

That distinction should be built into Phase 1.

---

# 63. The most useful one-line description of Pinky

I'd now describe Pinky as:

> **Pinky is a persistent, event-driven execution runtime that converts environmental and human events into deterministic actions, interactive work, or autonomous Tasks, while keeping scheduling, state, persistence, and execution control outside the LLM.**

That captures almost everything we've established without tying us to a framework.

---

# 64. Phase 0 is therefore complete

I would consider the research/conceptual phase sufficiently mature to move into architecture.

The next phase should **not** be "start coding."

It should be:

# Phase 1 — Architectural Planning

And I'd structure that around concrete boundaries:

```text
1. Event Source Architecture
2. Event Reader Interface
3. Event Intake
4. Event Normalization
5. Event Schema
6. Event Persistence
7. Event Dispatch
8. Trigger/Subcription System
9. Task Model
10. Task Lifecycle
11. Scheduler
12. Priority Model
13. Queue Model
14. Resource/Concurrency Model
15. Dispatcher
16. Execution Model
17. Execution Lifecycle
18. Checkpointing
19. Recovery
20. Deterministic Execution
21. Interactive Execution
22. Autonomous Execution
23. Model Routing
24. Shutdown/Startup semantics
25. Observability and testing
```

And importantly, **we'll design those from the outside in**:

```text
What should happen?
        ↓
What contract represents it?
        ↓
Who owns it?
        ↓
How does it persist?
        ↓
How does it recover?
        ↓
Only then:
what technology implements it?
```

That keeps us from accidentally designing the architecture around LangGraph, Celery, Redis, asyncio, Ollama, or any other tool before we've established what Pinky actually needs.

**This is the point where I would say the conceptual foundation is ready.** We can now start the actual Phase 1 architectural planning.
