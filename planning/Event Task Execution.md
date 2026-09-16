Exactly. **Event → Task → Execution** should be the next architectural boundary.

We should treat these as three distinct concepts:

```text
EVENT
  ↓
"Something happened / became due"

TASK
  ↓
"Something should be accomplished"

EXECUTION
  ↓
"An attempt is currently carrying out that task"
```

A useful starting example:

```text
08:00
  ↓
EVENT: SCHEDULE_DUE
  ↓
TASK: "Check calendar and identify conflicts"
  ↓
EXECUTION #1
  ↓
LLM → Calendar → Observation → LLM
  ↓
COMPLETED
```

And importantly, the reverse isn't necessarily true:

```text
FILE_CHANGED
    ↓
may produce NO task

TIMER_FIRED
    ↓
may produce a deterministic action

USER_MESSAGE
    ↓
may produce a task

TOOL_COMPLETED
    ↓
may simply resume an existing execution
```

So I would **not** model this as a simple pipeline where every event becomes a task.

The conceptual relationship is more like:

```text
                         EVENT
                           │
                    Event Handling
                           │
             ┌─────────────┼─────────────┐
             │             │             │
             ▼             ▼             ▼
          IGNORE       ACTION        TASK CREATION
                           │             │
                           │             ▼
                           │           TASK
                           │             │
                           │             ▼
                           │         EXECUTION
                           │
                           ▼
                     deterministic
                       handling
```

And an existing task can produce multiple executions:

```text
TASK
 │
 ├── Execution #1 → failed
 │
 ├── Execution #2 → interrupted
 │
 └── Execution #3 → completed
```

That distinction will become **very important** for retries, persistence, scheduling, failures, human approval, and autonomous agents.

### The questions we should answer next

I'd work through these in order:

1. **What exactly is an Event?**
    
    - identity
        
    - source
        
    - type
        
    - payload
        
    - causation
        
    - correlation
        
    - persistence
        
    - ordering
        
2. **What exactly is a Task?**
    
    - goal
        
    - trigger
        
    - constraints
        
    - priority
        
    - lifecycle
        
    - ownership
        
    - recurrence
        
    - dependencies
        
3. **What exactly is an Execution?**
    
    - execution state
        
    - steps
        
    - observations
        
    - checkpoints
        
    - retries
        
    - cancellation
        
    - pause/resume
        
    - completion
        
4. **How do they relate?**
    
    - Can one event create multiple tasks?
        
    - Can one task have multiple executions?
        
    - Can one execution generate events?
        
    - Can events modify existing tasks?
        
    - Can executions create new tasks?
        
5. **Who owns each transition?**
    

```text
Event → Task
    ?
    
Task → Execution
    ?

Execution → Event
    ?
```

6. **Then map this onto the three sibling layers:**
    

```text
                 ACTIVE LAYER
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
  DETERMINISTIC  INTERACTIVE   AUTONOMOUS
        │             │             │
        └─────────────┼─────────────┘
                      │
                 TASK SYSTEM
                      │
              EVENT → TASK → EXECUTION
```

I recommend we **start with Event itself**, define it rigorously, and deliberately avoid thinking about LLMs while doing so. Once the event model is solid, Task and Execution become much easier to derive.


I also checked how durable-execution systems such as Temporal, LangGraph, and OpenHands model events and execution. There is a useful common pattern: events represent things that happened, while execution state is persisted separately or reconstructed from event history. Temporal, for example, explicitly treats its Event History as an append-only record of what happened during a Workflow Execution, and uses it to recover execution after failure. ([GitHub](https://github.com/temporalio/documentation/blob/main/docs/encyclopedia/workflow/workflow-execution/event.mdx?utm_source=chatgpt.com "documentation/docs/encyclopedia/workflow/workflow-execution/event.mdx at main · temporalio/documentation · GitHub"))

---

# 1. What is an Event?

I would define it as:

> **An Event is an immutable record that something happened, was requested, became true, or became due at a particular point in time.**

That definition is deliberately broad.

Examples:

```text
USER_MESSAGE_RECEIVED
TIMER_EXPIRED
FILE_CREATED
TASK_CREATED
TASK_CANCELLED
TOOL_COMPLETED
EXECUTION_FAILED
APPROVAL_RECEIVED
```

But an Event is **not**:

```text
"Check my calendar"
```

That's a task/goal.

Nor:

```text
"Run the calendar agent"
```

That's an execution instruction.

The distinction is:

```text
EVENT
"What happened?"

TASK
"What needs to be accomplished?"

EXECUTION
"What is currently attempting to accomplish it?"
```

---

# 2. The Event should be immutable

This is one of the strongest principles I'd adopt.

Once:

```text
USER_MESSAGE_RECEIVED
```

is recorded, we should never modify it.

If something changes because of that event, we create another event.

For example:

```text
EVENT 1
USER_MESSAGE_RECEIVED
"Remind me at 8 PM"

        ↓

EVENT 2
TASK_CREATED
"Reminder task"

        ↓

EVENT 3
SCHEDULE_CREATED
"20:00"

        ↓

EVENT 4
TASK_DUE

        ↓

EVENT 5
EXECUTION_STARTED

        ↓

EVENT 6
NOTIFICATION_SENT

        ↓

EVENT 7
EXECUTION_COMPLETED
```

This gives us an **event history**.

That pattern is well established in durable execution/event-sourcing systems. Temporal maintains an append-only Event History specifically so execution can recover and be audited; Microsoft describes the event-sourcing pattern similarly, where events are persisted and consumers react to them. ([GitHub](https://github.com/temporalio/documentation/blob/main/docs/encyclopedia/workflow/workflow-execution/event.mdx?utm_source=chatgpt.com "documentation/docs/encyclopedia/workflow/workflow-execution/event.mdx at main · temporalio/documentation · GitHub"))

---

# 3. An Event is a fact, not an instruction

This distinction is extremely important.

Bad:

```text
FILE_CHANGED
→ "Analyze this file"
```

The event should only say:

```text
FILE_CHANGED
```

The Active Layer decides what that means.

Likewise:

```text
TIMER_EXPIRED
```

doesn't mean:

```text
CALL LLM
```

It means:

> A timer condition became true.

The routing/task system decides what should happen.

This is what allows the same event to have different consumers.

For example:

```text
FILE_CREATED
       │
       ├── File Indexer
       │
       ├── Security Scanner
       │
       └── Task Trigger
```

The event doesn't know any of these exist.

---

# 4. This gives us Publisher → Event → Consumers

Conceptually:

```text
                    EVENT
                      │
          ┌───────────┼───────────┐
          ▼           ▼           ▼
       Handler A   Handler B   Handler C
```

For example:

```text
EMAIL_RECEIVED
      │
      ├── Inbox state updater
      ├── Notification system
      └── Task trigger
```

This decoupling is one of the major advantages of event-driven architecture. Event-sourcing systems commonly allow multiple handlers/consumers to react to the same persisted event. ([GitHub](https://github.com/microsoftdocs/architecture-center/blob/main/docs/patterns/event-sourcing.md?utm_source=chatgpt.com "architecture-center/docs/patterns/event-sourcing.md at main · MicrosoftDocs/architecture-center · GitHub"))

---

# 5. Proposed Event structure

I'd start with something like:

```text
Event
│
├── id
├── type
├── source
├── timestamp
├── payload
├── correlation_id
├── causation_id
└── metadata
```

Let's examine them.

---

## `id`

Unique identifier.

```text
event_id = evt_01J...
```

Every event gets one.

This allows:

```text
"What caused this?"
"Was this event already processed?"
"Which execution generated this?"
```

---

## `type`

The semantic identity.

Examples:

```text
USER_MESSAGE_RECEIVED
TIMER_EXPIRED
TASK_CREATED
EXECUTION_STARTED
TOOL_COMPLETED
```

The type should be stable and machine-readable.

---

## `source`

Where did it originate?

For example:

```text
human
scheduler
filesystem
tool
agent
system
external_service
```

This is different from event type.

For example:

```text
type: TASK_CREATED
source: interactive_agent
```

versus:

```text
type: TASK_CREATED
source: autonomous_agent
```

Same event type, different origin.

---

# 6. Timestamp

At minimum:

```text
occurred_at
```

meaning:

> When did the event actually happen?

Potentially we also want:

```text
recorded_at
```

meaning:

> When did the system persist the event?

Those can differ.

For example:

```text
10:00:00
FILE_CREATED

10:00:04
Active Layer receives it

10:00:05
event persisted
```

So:

```text
occurred_at = 10:00:00
recorded_at = 10:00:05
```

This distinction becomes useful for delayed events, crashes, offline devices, etc.

---

# 7. Payload

The actual event-specific data.

For:

```text
FILE_CREATED
```

perhaps:

```json
{
  "path": "/downloads/report.pdf",
  "size": 1827344
}
```

For:

```text
USER_MESSAGE_RECEIVED
```

perhaps:

```json
{
  "message": "Remind me tomorrow at 8",
  "conversation_id": "..."
}
```

The event envelope remains stable while the payload changes according to the event type.

---

# 8. `causation_id`

This one is particularly important.

It answers:

> **What directly caused this event?**

Example:

```text
evt1
USER_MESSAGE_RECEIVED
```

causes:

```text
evt2
TASK_CREATED
```

Therefore:

```text
evt2.causation_id = evt1.id
```

Then:

```text
evt3
EXECUTION_STARTED
```

was caused by:

```text
evt2
```

So:

```text
evt3.causation_id = evt2.id
```

We get:

```text
USER_MESSAGE
     │
     ▼
TASK_CREATED
     │
     ▼
EXECUTION_STARTED
     │
     ▼
TOOL_COMPLETED
     │
     ▼
EXECUTION_COMPLETED
```

This creates a causal chain.

---

# 9. `correlation_id`

This is different.

`causation_id` answers:

> What directly caused me?

`correlation_id` answers:

> **What larger operation does this belong to?**

Suppose a user asks:

> "Research X."

That creates a task:

```text
task_123
```

and execution:

```text
exec_456
```

Then 50 events may occur:

```text
TASK_CREATED
EXECUTION_STARTED
SEARCH_REQUESTED
SEARCH_COMPLETED
DOCUMENT_FOUND
LLM_RESPONSE
TOOL_REQUESTED
TOOL_COMPLETED
...
EXECUTION_COMPLETED
```

They can all share:

```text
correlation_id = task_123
```

So we can retrieve the complete history of that task.

---

# 10. Why both matter

Imagine:

```text
             TASK
               │
               ▼
          EXECUTION
               │
        ┌──────┴──────┐
        ▼             ▼
     TOOL A        TOOL B
        │             │
        ▼             ▼
     result         result
```

Every event can say:

```text
correlation_id = execution/task
```

while:

```text
causation_id
```

forms the precise causal chain.

This is very useful for debugging:

> "Why did this execution happen?"

versus:

> "Which task did this execution belong to?"

---

# 11. `metadata`

This should contain non-semantic information.

For example:

```text
priority
trace_id
origin_device
version
authentication_context
runtime
model
```

But I'd be careful here.

Don't turn metadata into a dumping ground.

Anything that has semantic meaning to the event should be in the proper schema/payload.

---

# 12. Proposed canonical structure

Conceptually:

```json
{
  "id": "evt_123",
  "type": "TASK_CREATED",
  "source": "interactive_agent",

  "occurred_at": "...",
  "recorded_at": "...",

  "correlation_id": "task_456",
  "causation_id": "evt_122",

  "payload": {
    "task_id": "task_456",
    "goal": "Check my calendar tomorrow"
  },

  "metadata": {
    "schema_version": 1
  }
}
```

I would **not** put LLM-specific things into the base Event schema.

For example, avoid:

```text
model_name
prompt
temperature
tokens
reasoning
```

Those belong to an execution/LLM-specific event or telemetry layer.

---

# 13. Events have lifecycle semantics

I think we should distinguish three broad types.

### Fact Events

Something happened.

```text
FILE_CREATED
MESSAGE_RECEIVED
TOOL_COMPLETED
EXECUTION_COMPLETED
```

### Request Events

Something requested a change/action.

```text
TASK_CREATE_REQUESTED
EXECUTION_CANCEL_REQUESTED
APPROVAL_REQUESTED
```

### State-transition Events

Something actually changed state.

```text
TASK_CREATED
TASK_CANCELLED
EXECUTION_STARTED
EXECUTION_PAUSED
EXECUTION_FAILED
```

But there's a subtle design question here.

I would generally prefer **events to describe facts**, rather than commands.

For example:

```text
CANCEL_EXECUTION
```

sounds like a command.

Instead:

```text
EXECUTION_CANCEL_REQUESTED
```

is an event/fact:

> Someone requested cancellation.

Then the system may produce:

```text
EXECUTION_CANCELLED
```

if cancellation actually happened.

That distinction becomes important later.

---

# 14. Event vs Command

This is one of the biggest things we should get right.

### Command

> "Please do this."

```text
CREATE_TASK
CANCEL_EXECUTION
SEND_NOTIFICATION
```

### Event

> "This happened."

```text
TASK_CREATED
EXECUTION_CANCELLED
NOTIFICATION_SENT
```

So:

```text
COMMAND
   ↓
handler
   ↓
EVENT
```

For example:

```text
CREATE_TASK_COMMAND
        ↓
 Task Manager
        ↓
TASK_CREATED_EVENT
```

This means **the Event Bus should not become a Command Bus**.

They can coexist, but conceptually they are different.

---

# 15. Then our Active Layer begins to look like this

```text
                    EVENT SOURCES
                         │
                         ▼
                 ┌──────────────┐
                 │ Event Intake │
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │  Event Store │
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │ Event Router │
                 └──────┬───────┘
                        │
              ┌─────────┼─────────┐
              ▼         ▼         ▼
         Deterministic Interactive Autonomous
```

But there's an important ordering question:

**Do we persist first and route second, or route first and persist second?**

For a durable system, I strongly favor:

```text
Receive
  ↓
Validate
  ↓
Persist
  ↓
Publish/Dispatch
  ↓
Handle
```

rather than:

```text
Receive
  ↓
Handle
  ↓
Persist
```

Why?

Because if the process crashes during handling, we still know the event existed.

Temporal follows this general durability principle: its service persists Event History and uses it as the durable record from which execution can recover. ([GitHub](https://github.com/temporalio/documentation/blob/main/docs/encyclopedia/workflow/workflow-execution/event.mdx?utm_source=chatgpt.com "documentation/docs/encyclopedia/workflow/workflow-execution/event.mdx at main · temporalio/documentation · GitHub"))

---

# 16. But don't make the Event Store equal the entire system state

This is another important distinction.

Suppose we have:

```text
TASK_CREATED
TASK_STARTED
TASK_COMPLETED
```

We don't want to scan 500,000 events every time we ask:

> "What is the task's current status?"

Instead:

```text
EVENT STORE
    │
    ├── authoritative history
    │
    ▼
PROJECTIONS / STATE
    │
    └── current task status
```

So we have:

```text
Event History
     ↓
Projection
     ↓
Current State
```

This is standard event-sourcing thinking. The event log is the historical record; derived views can provide efficient current state. ([GitHub](https://github.com/microsoftdocs/architecture-center/blob/main/docs/patterns/event-sourcing.md?utm_source=chatgpt.com "architecture-center/docs/patterns/event-sourcing.md at main · MicrosoftDocs/architecture-center · GitHub"))

---

# 17. Now let's consider event delivery

An event could be:

```text
PERSISTED
```

but not yet:

```text
PROCESSED
```

So we need to distinguish:

```text
Event exists
```

from:

```text
Consumer handled event
```

For example:

```text
EVENT
TASK_DUE
   │
   ├── persisted ✓
   │
   ├── deterministic handler ✓
   │
   └── autonomous trigger ✓
```

If the autonomous worker crashes:

```text
TASK_DUE
   │
   └── autonomous handler ✗
```

The event still exists.

The system can retry delivery.

This is one reason I don't want events to disappear after being consumed.

---

# 18. This naturally leads to idempotency

Suppose:

```text
TASK_DUE
```

is delivered twice.

Bad implementation:

```text
TASK_DUE
 ↓
create execution
 ↓
create execution
```

Now we have two executions.

We need a stable identity/idempotency rule.

For example:

```text
event_id = evt123
```

and:

```text
consumer = autonomous_scheduler
```

Then:

```text
(evt123, autonomous_scheduler)
```

has already been processed.

Don't process it again.

This becomes extremely important once we introduce retries and crashes.

Temporal similarly has explicit retry/cancellation semantics around Activity Tasks and persists the resulting lifecycle events. ([GitHub](https://github.com/temporalio/documentation/blob/main/docs/encyclopedia/workflow/workflow-execution/event.mdx?utm_source=chatgpt.com "documentation/docs/encyclopedia/workflow/workflow-execution/event.mdx at main · temporalio/documentation · GitHub"))

---

# 19. Events should therefore have identity and ordering, but don't overpromise global ordering

I'd **not** assume:

```text
event 1 < event 2 < event 3
```

globally.

Instead, we care about ordering within a relevant stream/correlation.

For example:

```text
task_123:
    event A
    event B
    event C
```

But unrelated tasks can execute concurrently:

```text
task_A: A1 → A2 → A3

task_B: B1 → B2
```

and there is no reason to force:

```text
A1 → B1 → A2 → B2 → ...
```

This matters enormously for future concurrency.

---

# 20. Event streams

I therefore think we'll eventually have conceptual streams:

```text
SYSTEM STREAM
USER/CONVERSATION STREAM
TASK STREAM
EXECUTION STREAM
```

For example:

```text
task_123
│
├── TASK_CREATED
├── EXECUTION_STARTED
├── TOOL_REQUESTED
├── TOOL_COMPLETED
├── EXECUTION_COMPLETED
```

And:

```text
task_456
│
├── TASK_CREATED
├── EXECUTION_STARTED
├── EXECUTION_PAUSED
├── HUMAN_INPUT_REQUESTED
├── HUMAN_INPUT_RECEIVED
├── EXECUTION_RESUMED
└── EXECUTION_COMPLETED
```

That gives us a very clean mental model.

---

# 21. One correction to our earlier architecture

Earlier we said:

```text
Event → Task → Execution
```

That's useful as the **primary lifecycle**, but it's not literally one-way.

The real system is:

```text
                    EVENTS
                       │
           ┌───────────┼───────────┐
           ▼           ▼           ▼
       create task  update task   control execution
           │           │           │
           ▼           ▼           ▼
          TASK       TASK          EXECUTION
           │
           ▼
       EXECUTION
           │
           ├── produces events
           │
           ▼
         EVENTS
```

So:

> **Events are the connective tissue of the entire Active Layer.**

Not merely the first step.

---

# 22. This is where the three sibling layers fit

Now we can revisit your three-layer design.

```text
                         EVENT
                           │
                    ┌──────┴──────┐
                    │ Active Layer│
                    └──────┬──────┘
                           │
                ┌──────────┼──────────┐
                ▼          ▼          ▼
          DETERMINISTIC INTERACTIVE AUTONOMOUS
                │          │          │
                └──────────┼──────────┘
                           │
                         EVENTS
```

The three siblings **consume and produce events**.

They don't own the global event system.

That's an important architectural boundary.

---

# 23. And now we can define Event in one sentence

I would put this into the architecture specification:

> **An Event is an immutable, persistable fact representing something that occurred, was requested, or became true within or outside the system. Events form the durable causal record through which the Active Layer coordinates Tasks, Executions, and system components.**

That is a strong definition.

---

# 24. Preliminary Event contract

I'd freeze something close to this conceptually:

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

And establish these invariants:

```text
1. Events are immutable.
2. Every event has a unique ID.
3. Events represent facts, not mutable state.
4. Events do not directly contain execution logic.
5. Events may cause Tasks or Executions, but are not Tasks/Executions.
6. Events may be consumed by multiple handlers.
7. Event persistence precedes durable processing.
8. Event processing must be idempotent.
9. Related events can share a correlation ID.
10. Causation IDs establish direct causal relationships.
11. Global event ordering is not assumed.
12. Current state is derived/materialized separately from history.
```

These principles are strongly aligned with the durable-execution/event-driven systems we looked at, particularly Temporal's event history/replay model. ([GitHub](https://github.com/temporalio/documentation/blob/main/docs/encyclopedia/workflow/workflow-execution/event.mdx?utm_source=chatgpt.com "documentation/docs/encyclopedia/workflow/workflow-execution/event.mdx at main · temporalio/documentation · GitHub"))

---

# 25. One more critical distinction: Event History vs Execution History

Don't merge these yet.

We could have:

```text
GLOBAL EVENT HISTORY
```

containing everything:

```text
user events
system events
task events
execution events
tool events
scheduler events
```

while an individual execution has a **filtered execution history**:

```text
EXECUTION #42
│
├── started
├── LLM call
├── tool call
├── observation
├── LLM call
├── tool call
└── completed
```

OpenHands' event-driven agent architecture is useful here: its Agent operates over an Event History while keeping the agent itself stateless between steps. ([GitHub](https://github.com/OpenHands/docs/blob/main/sdk/arch/agent.mdx?utm_source=chatgpt.com "docs/sdk/arch/agent.mdx at main · OpenHands/docs · GitHub"))

LangGraph takes a related approach with persisted graph state/checkpoints and resumable execution. ([LangChain](https://langchain-ai.github.io/langgraphjs/how-tos/edit-graph-state/?utm_source=chatgpt.com "Interrupts - Docs by LangChain"))

This distinction will matter later when we design context.

---

# Where I'd go next

I would now **freeze Event conceptually** and move to:

## **Task**

because Task is where the system changes from:

> "Something happened"

to:

> **"There is something the system is responsible for accomplishing."**

And I think we'll discover that **Task is actually more complicated than Event**.

In particular, we need to distinguish:

```text
Task
├── Goal
├── Trigger
├── Owner
├── Execution policy
├── Priority
├── Constraints
├── Schedule
├── Dependencies
├── Inputs
├── Outputs
├── Lifecycle
└── Recurrence
```

Most importantly, we'll need to answer:

> **Is a scheduled reminder itself a Task, or is the reminder Task merely the thing that gets instantiated when a schedule fires?**

That decision will have a major impact on the architecture.

Good. Let's move to **Task**.

I want to be a little more precise here than the usual "a task is something to do," because Task is going to become the bridge between your **event-driven Active Layer** and the **execution/runtime layer**.

The important distinction is:

> **An Event is a fact. A Task is a durable responsibility. An Execution is an attempt to fulfill that responsibility.**

That gives us:

```text
EVENT
Something happened.

        ↓

TASK
Something now needs to be accomplished.

        ↓

EXECUTION
The system is currently attempting to accomplish it.
```

This separation is consistent with how modern durable-agent runtimes distinguish persistent workflow/task state from individual execution steps. LangGraph, for example, explicitly models tasks as discrete units of work whose results can be checkpointed and resumed, while its runtime separately manages graph execution and state. ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/functional-api?utm_source=chatgpt.com "Functional API overview - Docs by LangChain"))

---

# 1. What exactly is a Task?

My proposed definition:

> **A Task is a persistent declaration of an outcome the system is responsible for achieving, together with the conditions, constraints, and policies governing when and how that outcome should be pursued.**

There are several important words here.

### Persistent

A task can outlive:

- an LLM call
    
- an execution
    
- a process
    
- a reboot
    
- a conversation
    

### Outcome

A task describes **what should eventually be true**, not necessarily how to achieve it.

### Responsibility

The system now has something it is expected to handle.

### Policies

The task can specify things like:

- when to execute
    
- priority
    
- deadline
    
- allowed tools
    
- whether human approval is required
    
- retry behavior
    
- recurrence
    
- model preference
    

---

# 2. Task ≠ Execution

This is probably the most important distinction in this entire section.

Suppose you say:

> "Every morning at 8 AM, check my calendar and tell me if I have conflicts."

That's **one Task**.

But it might have:

```text
Task: T1
    │
    ├── Execution #1 — Sept 15
    ├── Execution #2 — Sept 16
    ├── Execution #3 — Sept 17
    ├── Execution #4 — Sept 18
    └── ...
```

Therefore:

```text
Task = durable responsibility
Execution = one attempt/instance of fulfilling it
```

This becomes particularly important for recurring tasks.

---

# 3. A Task can exist without an active Execution

Consider:

> "Every Sunday, summarize my calendar."

At 3 PM Tuesday:

```text
TASK
status = scheduled
```

There is no active execution.

At Sunday 8 AM:

```text
TASK_DUE
   ↓
EXECUTION_CREATED
```

Now:

```text
TASK
status = running

EXECUTION
status = running
```

After completion:

```text
TASK
status = scheduled

EXECUTION
status = completed
```

The Task survives.

The Execution doesn't need to.

---

# 4. This solves the recurring-task problem

Without this distinction, you might model:

```text
SUNDAY 8 AM
 ↓
create task
```

every week.

But that loses the identity of the underlying responsibility.

Instead:

```text
TASK
id = T123
schedule = every Sunday 08:00
```

Then:

```text
Occurrence 1 → Execution E1
Occurrence 2 → Execution E2
Occurrence 3 → Execution E3
```

So:

```text
             TASK T123
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
       E1       E2       E3
      Sun1     Sun2     Sun3
```

This is much cleaner.

---

# 5. But is a schedule itself a Task?

This was one of the questions we identified earlier.

I think the answer should be:

> **No. A schedule is a trigger/policy attached to a Task.**

For example:

```text
Task
────────────────────
Goal:
Check calendar for conflicts

Trigger:
Every day at 08:00

Execution:
Autonomous
```

The schedule says:

> **When should the Task become eligible for execution?**

It doesn't define the task itself.

This separation lets us support other triggers:

```text
Task
 ├── schedule trigger
 ├── event trigger
 ├── condition trigger
 └── manual trigger
```

---

# 6. This gives us an important concept: Task Trigger

A Task can have one or more activation conditions.

For example:

### Scheduled

```text
08:00 every day
```

### Event-driven

```text
when FILE_CREATED
```

### Conditional

```text
when temperature > 30°C
```

### Human-triggered

```text
when user asks
```

### Dependency-driven

```text
when Task A completes
```

So:

```text
TASK
 │
 └── Trigger Policy
       │
       ├── schedule
       ├── event
       ├── condition
       ├── dependency
       └── manual
```

The Task itself doesn't need to care where its trigger came from.

---

# 7. Example: user-created task

User says:

> "Tomorrow at 9, remind me to submit my application."

The Interactive Plane might create:

```text
TASK_CREATED
```

with:

```text
goal:
    Remind user to submit application

trigger:
    2026-09-16 09:00

execution_mode:
    deterministic
```

Notice something interesting.

**This doesn't need an LLM.**

At 9 AM:

```text
SCHEDULE_DUE
   ↓
Task T1
   ↓
Deterministic Execution
   ↓
Notification
```

The strong model never needs to wake up.

This is precisely why our three sibling execution layers matter.

---

# 8. Now consider a more complex task

User:

> "Every morning, check my emails and tell me if there's anything important."

Task:

```text
TASK T2

Goal:
    Identify important email received since previous run.

Trigger:
    Daily at 08:00

Execution:
    Autonomous

Capabilities:
    email.read

Output:
    summary

Priority:
    normal
```

At 8 AM:

```text
SCHEDULE_DUE
      ↓
Task T2
      ↓
Execution E7
      ↓
Autonomous Agent
```

The Task itself doesn't contain:

```text
"call Gmail"
"then summarize"
"then call calendar"
```

Those are **execution decisions**.

---

# 9. Task should describe WHAT, not HOW

This is a major architectural principle I'd establish.

Bad:

```text
Task:
1. Call Gmail API
2. Get emails
3. Filter them
4. Send LLM prompt
5. Summarize
```

That's an execution plan.

Better:

```text
Task:

Goal:
Identify important emails from the previous 24 hours.

Constraints:
Do not modify email.

Output:
Concise summary.

Trigger:
08:00 daily.
```

Then the Autonomous Agent decides how to accomplish it.

This is analogous to the distinction between a workflow's durable task definition and the individual operations used to execute it. LangGraph's task abstraction is intentionally a discrete unit of work that can be retried/checkpointed, rather than being the entire global workflow definition. ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/functional-api?utm_source=chatgpt.com "Functional API overview - Docs by LangChain"))

---

# 10. Task has a lifecycle

I'd propose:

```text
DRAFT
  ↓
ACTIVE
  ↓
READY
  ↓
RUNNING
  ↓
COMPLETED
```

But we need more states.

A more realistic state machine:

```text
                 ┌─────────────┐
                 │    DRAFT    │
                 └──────┬──────┘
                        │
                     activate
                        │
                        ▼
                 ┌─────────────┐
                 │    ACTIVE   │
                 └──────┬──────┘
                        │
                    trigger
                        │
                        ▼
                 ┌─────────────┐
                 │    READY    │
                 └──────┬──────┘
                        │
                      start
                        │
                        ▼
                 ┌─────────────┐
                 │   RUNNING   │
                 └──────┬──────┘
                        │
             ┌──────────┼──────────┐
             ▼          ▼          ▼
         COMPLETED    FAILED     PAUSED
                           │         │
                           │         └── resume
                           │
                         retry
                           │
                           ▼
                        READY
```

But there's an important question:

**Should `RUNNING` actually be a Task state?**

I would say **yes, but carefully**.

The Task's lifecycle describes its responsibility.

The Execution has its own lifecycle.

So:

```text
TASK
status = RUNNING

EXECUTION
status = RUNNING
```

are related but separate.

---

# 11. Task state vs Execution state

This is crucial.

Suppose:

```text
Task T1
"Check email every morning"
```

Execution E1 fails because Gmail is temporarily unavailable.

Task:

```text
ACTIVE
```

Execution:

```text
FAILED
```

That's completely valid.

The Task itself hasn't failed.

Only **this attempt** failed.

Therefore:

```text
Task status ≠ Execution status
```

---

# 12. Execution lifecycle

We'll fully design this next, but conceptually:

```text
CREATED
   ↓
QUEUED
   ↓
RUNNING
   │
   ├── PAUSED
   ├── WAITING
   ├── FAILED
   └── COMPLETED
```

Task:

```text
ACTIVE
```

can have:

```text
Execution #1 → FAILED
Execution #2 → RUNNING
```

This distinction is exactly what allows durable systems to retry work without destroying the underlying task.

LangGraph's retry and checkpointing model makes a similar distinction: individual work can be retried, while durable state remains available for recovery. ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/fault-tolerance?utm_source=chatgpt.com "Fault tolerance - Docs by LangChain"))

---

# 13. Proposed Task structure

I'd start with:

```text
Task
│
├── id
├── goal
├── status
├── creator
├── created_at
├── updated_at
│
├── trigger
│
├── execution_policy
│
├── constraints
│
├── priority
│
├── deadline
│
├── dependencies
│
├── input
│
├── output_spec
│
└── metadata
```

Let's break these down.

---

# 14. `id`

Unique persistent identity.

```text
task_01J...
```

This identity remains stable across executions.

---

# 15. `goal`

The most important field.

Example:

```text
"Check my calendar for conflicts."
```

or:

```text
"Notify me when the download completes."
```

or:

```text
"Research the latest developments in local AI agents."
```

This is the semantic objective.

The autonomous model can reason from this.

---

# 16. `status`

Current Task lifecycle state.

Possible values:

```text
DRAFT
ACTIVE
PAUSED
BLOCKED
COMPLETED
CANCELLED
EXPIRED
```

Notice I would **not** necessarily include `RUNNING` here.

Why?

Because the Task may have multiple executions.

The execution knows whether it is running.

The Task knows whether its responsibility is currently active.

This leads to a cleaner model:

```text
Task
status = ACTIVE

Execution
status = RUNNING
```

---

# 17. `creator`

Who created the task?

Possible values:

```text
human
interactive_agent
autonomous_agent
system
external_service
```

Example:

```text
creator = interactive_agent
```

because the small LLM interpreted the user's request.

Or:

```text
creator = autonomous_agent
```

if the strong agent creates a follow-up task.

---

# 18. `trigger`

This is where scheduling belongs.

Conceptually:

```text
trigger:
    type = schedule
    specification = "08:00 daily"
```

or:

```text
trigger:
    type = event
    event_type = FILE_CREATED
```

or:

```text
trigger:
    type = dependency
    task_id = T123
    condition = completed
```

Or:

```text
trigger:
    type = manual
```

---

# 19. Execution policy

This is where our three sibling layers become relevant.

For example:

```text
execution_policy:

    preferred_mode:
        autonomous

    preferred_model:
        strong

    allowed_modes:
        deterministic
        autonomous
```

But I wouldn't encode:

```text
small_model = X
big_model = Y
```

inside the Task.

That's infrastructure configuration.

Instead:

```text
reasoning_requirement = high
```

or:

```text
execution_mode = autonomous
```

and the Model Router decides which actual model to use.

This is important for future portability.

---

# 20. Constraints

These define boundaries.

Example:

```text
constraints:
    read_only = true
    allowed_tools = [
        calendar.read
    ]
    max_duration = 300
```

For a financial task:

```text
constraints:
    cannot_execute_transactions = true
```

For a file task:

```text
constraints:
    allowed_paths = [...]
```

The Task should carry **authorization/policy constraints**, not merely instructions to the LLM.

---

# 21. Priority

This becomes important when you have multiple pending tasks.

For example:

```text
CRITICAL
HIGH
NORMAL
LOW
BACKGROUND
```

Suppose:

```text
Task A — summarize email — LOW
Task B — user explicitly requested action — HIGH
Task C — security alert — CRITICAL
```

The execution manager should be able to prioritize them without consulting an LLM.

---

# 22. Deadline

Different from schedule.

Schedule:

> When should I try?

Deadline:

> By when should this be accomplished?

For example:

```text
trigger:
    08:00 tomorrow

deadline:
    12:00 tomorrow
```

A task could also have:

```text
deadline = 2026-09-20
```

without any schedule.

---

# 23. Dependencies

This is extremely useful.

Suppose:

```text
Task A:
Download dataset

Task B:
Analyze dataset
```

Then:

```text
B depends on A
```

So:

```text
A
↓
COMPLETED
↓
TASK B becomes READY
↓
Execution B
```

This is another reason Tasks cannot simply be transient execution requests.

---

# 24. Input

Task-specific data.

Example:

```text
input:
{
    "calendar_id": "primary",
    "lookahead_days": 7
}
```

This should be structured where possible.

---

# 25. Output specification

The Task should describe what kind of result is expected.

For example:

```text
output_spec:
    type = summary
```

or:

```text
output_spec:
    type = boolean
```

or:

```text
output_spec:
    type = file
```

or:

```text
output_spec:
    type = notification
```

This becomes useful for deterministic processing and validation.

---

# 26. Recurrence

I would **not** make recurrence a completely separate object from scheduling.

Conceptually:

```text
trigger:
    schedule:
        start
        recurrence
        timezone
        end_condition
```

Example:

```text
trigger:
    type: schedule

    schedule:
        recurrence: daily
        time: 08:00
        timezone: Asia/Kolkata
```

Then one Task produces repeated Executions.

---

# 27. Now let's revisit the reminder question

User:

> "Remind me tomorrow at 8."

I'd create:

```text
TASK T1

goal:
    Remind user about X

trigger:
    2026-09-16 08:00

execution_mode:
    deterministic

output:
    notification
```

At 8:

```text
SCHEDULE_DUE
     ↓
T1
     ↓
Execution E1
     ↓
Deterministic handler
     ↓
Notification
     ↓
E1 COMPLETED
     ↓
T1 COMPLETED
```

No LLM.

---

# 28. But recurring reminder

> "Remind me every Monday at 8."

Now:

```text
TASK T2

goal:
    Remind user about X

trigger:
    weekly Monday 08:00

status:
    ACTIVE
```

Then:

```text
T2
│
├── E1 → completed
├── E2 → completed
├── E3 → completed
└── E4 → ...
```

The Task remains active.

---

# 29. Autonomous recurring task

> "Every morning analyze my calendar."

Same structure:

```text
TASK T3
status = ACTIVE

trigger:
    daily 08:00

execution_policy:
    autonomous

goal:
    Analyze calendar for conflicts
```

Then:

```text
08:00
 ↓
SCHEDULE_DUE
 ↓
Execution E1
 ↓
Autonomous
 ↓
complete

next day

 ↓
SCHEDULE_DUE
 ↓
Execution E2
```

Very clean.

---

# 30. One-shot autonomous task

> "Research this now."

Task:

```text
T4

trigger:
    immediate

recurrence:
    none

execution:
    autonomous
```

Then:

```text
T4
 ↓
E1
 ↓
complete
 ↓
T4 COMPLETED
```

---

# 31. Event-triggered task

Suppose:

> "When I download a PDF, summarize it."

Task:

```text
T5

trigger:
    event:
        FILE_CREATED
        extension = .pdf

goal:
    summarize newly created PDF

execution:
    autonomous
```

Then:

```text
FILE_CREATED
      ↓
Event Router
      ↓
Trigger Matcher
      ↓
T5 eligible
      ↓
E1
      ↓
Strong LLM
```

Again, the Task survives until explicitly cancelled.

---

# 32. This gives us a Trigger Matcher

I think this is going to be part of the Active Layer:

```text
                   EVENT
                     │
                     ▼
               Event Router
                     │
                     ▼
              Trigger Matcher
                     │
              ┌──────┼──────┐
              ▼      ▼      ▼
             T1     T2     T3
```

The matcher answers:

> **Does this Event activate any Tasks?**

That is deterministic infrastructure.

The LLM should not answer this.

---

# 33. This also allows multiple tasks to respond to one event

For:

```text
FILE_CREATED
```

we might have:

```text
Task A:
Index file

Task B:
Scan for malware

Task C:
Summarize PDF
```

So:

```text
             FILE_CREATED
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
         T1       T2       T3
          │        │        │
         E1       E2       E3
```

They can execute concurrently.

That's powerful.

---

# 34. And one Task can be triggered by multiple event types

For example:

> "Analyze my downloads whenever a new dataset arrives."

Maybe:

```text
FILE_CREATED
DOWNLOAD_COMPLETED
EXTERNAL_DATASET_READY
```

all satisfy the trigger.

Then:

```text
Event A ─┐
Event B ─┼→ Task
Event C ─┘
```

But we need to be careful about duplicate activations.

That's where Task/Execution identity and idempotency come back.

---

# 35. Trigger ≠ execution request

This distinction is subtle but critical.

Suppose:

```text
FILE_CREATED
```

matches Task T1.

That doesn't necessarily mean:

```text
CREATE EXECUTION
```

immediately.

The Active Layer may first check:

```text
Task active?
Dependencies satisfied?
Already executing?
Within concurrency limit?
Past deadline?
Policy allows execution?
```

Only then:

```text
Execution created
```

So:

```text
EVENT
 ↓
Trigger match
 ↓
Task eligibility
 ↓
Execution creation
```

That's the real lifecycle.

---

# 36. We can now formulate the relationship precisely

```text
EVENT
    │
    │ may trigger
    ▼
TASK
    │
    │ may instantiate
    ▼
EXECUTION
    │
    │ produces
    ▼
EVENT
```

This is the central cycle:

```text
        ┌──────────────────────┐
        │                      │
        ▼                      │
      EVENT ──→ TASK ──→ EXECUTION
        ▲                         │
        │                         │
        └─────────────────────────┘
```

That is much more accurate than a linear pipeline.

---

# 37. What about tasks created by agents?

This is where your two-agent architecture becomes interesting.

### Interactive agent

User:

> "Every morning summarize my emails."

Small LLM produces:

```text
CREATE_TASK
```

The Task Manager creates:

```text
TASK_CREATED
```

The Interactive Agent doesn't own the Task.

It merely **requested its creation**.

---

### Autonomous agent

Strong LLM might discover:

> "I should monitor this folder for future files."

It can request:

```text
CREATE_TASK
```

Then the exact same Task Manager handles it.

This is important:

> **Agents should request Tasks. They should not own the Task lifecycle.**

---

# 38. This keeps the Active Layer authoritative

```text
             Interactive
                  │
             CREATE_TASK
                  │
                  ▼
            ┌────────────┐
            │ Task       │
            │ Manager    │
            └─────┬──────┘
                  │
            TASK_CREATED
```

And:

```text
             Autonomous
                  │
             CREATE_TASK
                  │
                  ▼
            Task Manager
```

Same interface.

No special case.

---

# 39. Now think about cancellation

User:

> "Stop the daily email summary."

Interactive Agent should not directly kill some process.

It requests:

```text
CANCEL_TASK
task_id = T3
```

Active Layer:

```text
Task Manager
     ↓
TASK_CANCEL_REQUESTED
     ↓
cancel policy
     ↓
TASK_CANCELLED
```

If an execution is currently running:

```text
T3
│
└── E17 RUNNING
       ↓
EXECUTION_CANCEL_REQUESTED
       ↓
EXECUTION_CANCELLED
```

Then:

```text
T3 = CANCELLED
```

This is exactly why separating Task and Execution matters.

---

# 40. Human interruption

Suppose the Autonomous Agent says:

> "I need your approval before sending this email."

Execution becomes:

```text
WAITING_FOR_HUMAN
```

The Task remains:

```text
ACTIVE
```

Then:

```text
HUMAN_APPROVAL_RECEIVED
```

causes:

```text
Execution → RUNNING
```

LangGraph's interrupt mechanism demonstrates this pattern directly: execution state is persisted when interrupted, waits indefinitely for external input, and resumes using the persisted state. ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/interrupts?utm_source=chatgpt.com "Interrupts - Docs by LangChain"))

OpenAI's Agents SDK similarly treats human-in-the-loop and handoffs as first-class runtime concepts rather than requiring the application to fake them through conversation. ([OpenAI GitHub](https://openai.github.io/openai-agents-python/?utm_source=chatgpt.com "OpenAI Agents SDK"))

---

# 41. What should a Task NOT contain?

I would explicitly prohibit these from the core Task model:

### ❌ Conversation history

That's Context/Conversation state.

### ❌ Full LLM prompt

That's model execution configuration.

### ❌ Tool-call history

That's Execution history.

### ❌ Current LLM reasoning

That's Execution state.

### ❌ Current context window

That's runtime/context management.

### ❌ Raw event history

That's Event Store/history.

### ❌ Model-specific settings

That's Model Policy.

This keeps Task small and stable.

---

# 42. The Task should be surprisingly boring

That's a good thing.

Something like:

```text
Task
────────────────────────────
id
goal
status

trigger
execution_policy

constraints
priority
deadline
dependencies

input
output_spec

created_by
created_at
updated_at
```

That's it.

The intelligence belongs elsewhere.

---

# 43. Preliminary Task state machine

I'd propose this:

```text
                 ┌──────────┐
                 │  DRAFT   │
                 └────┬─────┘
                      │ activate
                      ▼
                 ┌──────────┐
          ┌──────│  ACTIVE  │──────┐
          │      └────┬─────┘      │
          │           │             │
       pause       trigger       cancel
          │           │             │
          ▼           ▼             ▼
      ┌────────┐    READY       CANCELLED
      │ PAUSED │      │
      └───┬────┘      │
          │           │
       resume         │
          │           │
          └──────┬────┘
                 ▼
               READY
                 │
              execute
                 │
                 ▼
            execution(s)
                 │
          ┌──────┴──────┐
          ▼             ▼
       success         failure
          │             │
          ▼             ▼
      COMPLETED       retry/blocked
```

But there is one thing I would change:

**`READY` may be better represented as Execution state rather than Task state.**

If the task is active but its trigger has fired, that's probably:

```text
Task = ACTIVE
Execution = QUEUED
```

rather than:

```text
Task = READY
```

I lean toward that cleaner separation.

---

# 44. Therefore, the cleaner model is

### Task lifecycle

```text
DRAFT
ACTIVE
PAUSED
BLOCKED
COMPLETED
CANCELLED
EXPIRED
```

### Execution lifecycle

```text
CREATED
QUEUED
RUNNING
WAITING
PAUSED
COMPLETED
FAILED
CANCELLED
```

Then:

```text
Task ACTIVE
   │
   ├── Execution #1 COMPLETED
   ├── Execution #2 FAILED
   └── Execution #3 RUNNING
```

That's much cleaner.

---

# 45. Now we can define the three concepts very precisely

## Event

> An immutable fact about something that happened, was requested, or became true.

## Task

> A persistent responsibility describing an outcome the system is expected to achieve.

## Execution

> A concrete attempt to fulfill a Task under a particular set of runtime conditions.

And the lifecycle becomes:

```text
EVENT
  │
  │ triggers
  ▼
TASK
  │
  │ instantiated
  ▼
EXECUTION
  │
  │ produces
  ▼
EVENT
```

---

# 46. One important consequence: "Task" is not necessarily AI

This is worth emphasizing.

Tasks can be:

```text
DETERMINISTIC
INTERACTIVE
AUTONOMOUS
```

For example:

```text
Task:
Send notification at 8 PM.

→ Deterministic
```

```text
Task:
Ask user for missing information.

→ Interactive
```

```text
Task:
Research the latest AI papers and summarize findings.

→ Autonomous
```

So our three sibling layers aren't competing Task systems.

They are **execution modes for Tasks**.

That's a much stronger abstraction.

---

# 47. The resulting architecture is now becoming coherent

```text
                         EVENTS
                            │
                            ▼
                    ┌──────────────┐
                    │ Active Layer │
                    │              │
                    │ Event Store  │
                    │ Event Router │
                    │ Trigger Match│
                    │ Task Manager │
                    │ Scheduler    │
                    └──────┬───────┘
                           │
                         TASK
                           │
                    Execution Policy
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
    DETERMINISTIC      INTERACTIVE      AUTONOMOUS
          │                │                │
          │             Small LLM       Strong LLM
          │                │                │
          └────────────────┼────────────────┘
                           │
                       EXECUTION
                           │
                           ▼
                         EVENTS
```

This is the architecture I'd be comfortable building on.

---

# 48. One thing I would _not_ lock down yet

I don't want to finalize whether:

```text
Task
```

is stored as a normal mutable record **or** whether its lifecycle is entirely event-sourced.

There are three possibilities:

### A. Mutable Task + immutable Event History

```text
Task DB
+
Event Store
```

Simple and practical.

### B. Event-sourced Task

```text
Events
 ↓
Task Projection
```

More rigorous, more complex.

### C. Hybrid

```text
Events = authoritative history
Task = materialized current state
```

I currently favor **C**.

It gives us:

```text
Event history
    ↓
Task state projection
```

while keeping normal Task queries cheap.

This is conceptually aligned with event-sourcing and with LangGraph's distinction between persisted history/checkpoints and current materialized state. ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/persistence?utm_source=chatgpt.com "Persistence - Docs by LangChain"))

---

# 49. And now Execution becomes the really interesting part

We've now got:

```text
EVENT
│
│ trigger
▼
TASK
│
│ instantiate
▼
EXECUTION
```

The next question is:

> **What actually happens inside an Execution?**

That's where we get into:

```text
Execution
│
├── attempt
├── steps
├── context
├── model invocation
├── tool invocation
├── observations
├── checkpoints
├── waiting
├── retries
├── errors
├── human intervention
└── completion
```

And this is where **LangGraph, OpenAI Agents SDK, and durable-execution systems become directly relevant**.

For example, LangGraph persists checkpoints and task results specifically so execution can resume without recomputing completed work; it also treats retries, timeouts, interrupts, and error handling as runtime concerns. ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/fault-tolerance?utm_source=chatgpt.com "Fault tolerance - Docs by LangChain"))

The OpenAI Agents SDK takes a somewhat different approach: an agent run manages an LLM/tool loop, with handoffs, guardrails, sessions, and human-in-the-loop support around that loop. ([OpenAI GitHub](https://openai.github.io/openai-agents-python/?utm_source=chatgpt.com "OpenAI Agents SDK"))

So **Execution is where we should compare these architectures carefully**, rather than blindly adopting one.

---

## Current conceptual contract

I'd freeze our current understanding as:

```text
EVENT
Immutable fact.
       │
       │ may activate
       ▼
TASK
Persistent responsibility.
       │
       │ may instantiate
       ▼
EXECUTION
Concrete attempt.
       │
       │ produces
       ▼
EVENT
```

With:

```text
TASK
├── Goal
├── Trigger
├── Constraints
├── Priority
├── Dependencies
├── Execution Policy
└── Lifecycle
```

and:

```text
EXECUTION
├── Runtime State
├── Steps
├── Context
├── Attempts
├── Tool Calls
├── Model Calls
├── Checkpoints
├── Waiting/Interrupts
└── Result
```

**Next, I would go deep into Execution itself**, because that is where we decide what "an agent is running" actually means—whether the LLM is called once, repeatedly, event-by-event, how it sleeps, how it resumes, what survives a crash, how retries work, and how an execution can remain alive for hours/days without keeping an LLM process continuously active.

Absolutely. Now we get to the **most important part of the architecture: Execution**.

The previous two layers were relatively conceptual:

```text
Event      = something happened
Task       = something needs to be accomplished
Execution  = actually doing it
```

Execution is where the system becomes an **agent runtime**.

And after looking at how LangGraph, OpenAI Agents SDK, Temporal, and other agent runtimes handle this, there is one conclusion I want to establish very strongly:

> **An agent does not need to remain continuously "alive" for an autonomous task to remain alive.**

The **Execution state** remains alive/persistent. The **LLM process only needs to be active when reasoning is required.**

That distinction is fundamental.

---

# 1. First: what actually is an Execution?

I'd define it as:

> **An Execution is a runtime instance representing one attempt to fulfill a Task, including its current state, progress, interactions, waiting conditions, failures, and eventual outcome.**

So:

```text
Task T123
│
│ instantiate
▼
Execution E456
```

The Task says:

> "Analyze my emails every morning."

The Execution says:

> "I'm currently analyzing today's emails."

---

# 2. The most important misconception: the LLM isn't the Execution

This is where many agent architectures become confused.

You might initially imagine:

```text
EXECUTION
   │
   └── LLM process stays alive
           │
           ├── thinks
           ├── waits
           ├── thinks
           └── thinks
```

That's generally **not what you want**.

Instead:

```text
EXECUTION
   │
   ├── persisted state
   ├── current step
   ├── waiting condition
   ├── task information
   └── context
          │
          │ when reasoning required
          ▼
        LLM
          │
          ▼
     result/action
          │
          ▼
     persisted state
```

The LLM is a **compute resource used by the Execution**.

It is not the persistent identity of the Execution.

LangGraph's persistence model demonstrates this very explicitly: graph state is checkpointed, and execution can be resumed later from persisted state. ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/persistence?utm_source=chatgpt.com "Persistence - Docs by LangChain"))

Temporal takes the concept even further: workflows can remain durable across crashes, outages, and waits lasting seconds, days, or years, without requiring the original process to remain continuously executing. ([Temporal Docs](https://docs.temporal.io/?utm_source=chatgpt.com "Temporal Platform Documentation"))

---

# 3. This answers the "How does the LLM stay active?" question

It doesn't have to.

Consider:

```text
Task:
Every day at 08:00 analyze calendar.
```

At:

```text
07:00
```

nothing needs to happen.

You have:

```text
Task = ACTIVE
Execution = none
LLM = idle/off
```

At 08:00:

```text
SCHEDULE_DUE
     ↓
Execution created
     ↓
LLM activated
     ↓
reason
     ↓
tool call
     ↓
LLM activated again
     ↓
complete
```

After completion:

```text
Execution = COMPLETED
LLM = idle/off
```

This is the correct mental model.

---

# 4. An LLM call is more like a CPU burst

Think about a traditional operating system.

A process might need CPU time:

```text
PROCESS
   ↓
CPU
   ↓
compute
   ↓
I/O wait
   ↓
CPU
```

Similarly:

```text
AGENT EXECUTION
      ↓
     LLM
      ↓
  reasoning
      ↓
    TOOL
      ↓
   waiting
      ↓
     LLM
      ↓
  reasoning
```

The Execution persists through all of this.

---

# 5. The Agent Loop

Now we can look at what happens when the LLM **is** active.

The OpenAI Agents SDK describes the basic agent loop very clearly:

1. Call the model.
    
2. Inspect its result.
    
3. If final output → finish.
    
4. If tool call → execute tool and give result back to model.
    
5. If handoff → switch agent and continue.
    
6. Repeat until completion or a turn limit. ([OpenAI GitHub](https://openai.github.io/openai-agents-python/running_agents/?utm_source=chatgpt.com "Running agents - OpenAI Agents SDK"))
    

Conceptually:

```text
             ┌──────────────┐
             │    START     │
             └──────┬───────┘
                    ↓
             ┌──────────────┐
             │   LLM CALL   │
             └──────┬───────┘
                    ↓
             What did LLM say?
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
    FINAL        TOOL CALL     HANDOFF
       │            │            │
       ▼            ▼            ▼
     DONE         TOOL         NEW AGENT
                    │            │
                    └─────┬──────┘
                          ↓
                       LLM CALL
```

That's the core of an agent.

But **our architecture should put another layer around that loop.**

---

# 6. Execution is larger than the Agent Loop

I'd model it as:

```text
TASK
 │
 ▼
EXECUTION
 │
 ├── Runtime Controller
 │
 ├── State
 │
 ├── Context
 │
 ├── Agent Loop
 │      │
 │      ├── LLM
 │      ├── Tool
 │      ├── LLM
 │      └── ...
 │
 ├── Checkpointing
 │
 ├── Interrupt handling
 │
 ├── Retry handling
 │
 └── Completion
```

The Agent Loop is **inside** the Execution.

This distinction will become very useful for Jarvis later, even though we're intentionally not designing Jarvis right now.

---

# 7. Execution should be stateful

Imagine this execution:

```text
Execution E1

Goal:
Research AI agent architectures.

Step 1:
Search sources ✓

Step 2:
Read sources ✓

Step 3:
Compare architectures → currently running
```

We need persistent state:

```text
E1
├── status = RUNNING
├── current_step = 3
├── completed_steps = [1,2]
├── pending_step = 3
└── ...
```

If the computer crashes:

```text
💥
```

we should be able to restart:

```text
load E1
 ↓
restore state
 ↓
continue Step 3
```

rather than:

```text
start research from scratch
```

LangGraph's checkpoint system explicitly supports this kind of recovery. It saves graph state at execution boundaries and can resume after failures from the last successful checkpoint; it even persists successful writes from other tasks in a failed super-step so they don't have to be recomputed. ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/persistence?utm_source=chatgpt.com "Persistence - Docs by LangChain"))

---

# 8. Checkpointing is therefore part of Execution

I'd make this an explicit responsibility:

```text
Execution Runtime
│
├── execute
├── checkpoint
├── resume
├── pause
├── retry
└── terminate
```

A checkpoint might contain:

```text
execution_id
task_id

status
current_step

working_state
context_reference

completed_actions
pending_action

retry_count

waiting_for

timestamp
```

But there is a very important rule:

> **Don't blindly checkpoint the entire LLM context after every token.**

Checkpoint **logical execution state**, not every transient detail.

---

# 9. Execution Steps

We need a concept below Execution:

```text
Execution
   │
   ├── Step 1
   ├── Step 2
   ├── Step 3
   └── Step 4
```

A Step is a discrete unit of work.

For example:

```text
Execution:
"Analyze calendar"

Step 1:
Retrieve calendar

Step 2:
Analyze events

Step 3:
Identify conflicts

Step 4:
Generate notification
```

But there's an important subtlety:

**The LLM does not necessarily know all these steps beforehand.**

The agent may dynamically generate them.

For example:

```text
LLM
 ↓
Tool call: calendar.search
 ↓
Observation
 ↓
LLM
 ↓
Tool call: calendar.get_event
 ↓
Observation
 ↓
LLM
 ↓
Final
```

The Execution runtime records these as actual steps.

---

# 10. Step ≠ LLM call

Another critical distinction.

A Step might be:

```text
CALL_LLM
```

or:

```text
CALL_TOOL
```

or:

```text
WAIT
```

or:

```text
REQUEST_HUMAN_INPUT
```

or:

```text
VALIDATE_RESULT
```

So:

```text
Execution
│
├── Step
│     └── LLM call
│
├── Step
│     └── Tool call
│
├── Step
│     └── LLM call
│
└── Step
      └── Completion
```

This lets us reason about the Execution independently from any particular model provider.

---

# 11. A more complete Execution state machine

I'd start with:

```text
                    CREATED
                       │
                       ▼
                    QUEUED
                       │
                       ▼
                    RUNNING
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
     WAITING         PAUSED         FAILED
        │              │              │
        │              │            retry
        │              │              │
        │              │              ▼
        │              │            QUEUED
        │              │
      resume         resume
        │              │
        └──────┬───────┘
               ▼
            RUNNING
               │
        ┌──────┴───────┐
        ▼              ▼
    COMPLETED       CANCELLED
```

And I'd distinguish:

### WAITING

The execution cannot proceed because it is waiting for something.

Examples:

```text
waiting for timer
waiting for external API
waiting for human
waiting for another task
```

### PAUSED

Someone/system explicitly suspended the execution.

That distinction will matter.

---

# 12. Waiting is extremely important

Consider:

> "Wait until tomorrow at 9 AM, then check the calendar."

A naïve implementation:

```text
while now < 9am:
    sleep(1)
```

That's terrible.

You're tying up a runtime process unnecessarily.

Instead:

```text
Execution
status = WAITING

wake_at = tomorrow 09:00
```

Persist it.

Then:

```text
process can terminate
```

At 09:00:

```text
TIMER_EVENT
     ↓
Execution E1
     ↓
resume
```

This is exactly the sort of durable waiting that workflow engines are designed to support. Temporal's central promise is that durable workflow state survives process/infrastructure failure and can resume much later. ([Temporal Docs](https://docs.temporal.io/?utm_source=chatgpt.com "Temporal Platform Documentation"))

---

# 13. This is how an "always-on agent" actually works

This is worth emphasizing because it's often misunderstood.

You don't necessarily have:

```text
24/7 LLM
```

You have:

```text
24/7 EVENT / TASK / EXECUTION INFRASTRUCTURE
```

which can trigger:

```text
LLM
```

when required.

Architecture:

```text
                ACTIVE SYSTEM
                     │
        ┌────────────┼────────────┐
        │            │            │
    Scheduler      Events      User input
        │            │            │
        └────────────┼────────────┘
                     ▼
               Task Manager
                     │
                     ▼
                Executions
                     │
              when reasoning
                     │
                     ▼
                    LLM
```

The **system is always available**.

The LLM is **on demand**.

---

# 14. This has major implications for local AI

Suppose your local machine has:

```text
Qwen
```

running through Ollama.

You don't necessarily need:

```text
Ollama → continuously generating
```

Instead:

```text
Ollama server
      │
      │ waiting for requests
      ▼
Event occurs
      │
      ▼
Execution needs reasoning
      │
      ▼
LLM request
      │
      ▼
Ollama generates
      │
      ▼
response
      │
      ▼
Execution continues
```

Depending on the serving stack, the model weights may remain loaded in memory for a while or be unloaded after an idle period, but that is a **resource-management concern**, not an agent-lifecycle concern.

---

# 15. This also makes multiple LLMs straightforward

Remember your earlier architecture:

```text
Small LLM
Interactive

Strong LLM
Autonomous
```

Now the Execution layer can choose:

```text
Execution Policy
       │
       ▼
Model Router
       │
 ┌─────┴─────┐
 ▼           ▼
Small       Strong
LLM         LLM
```

For example:

```text
Task:
"Remind me tomorrow"

Execution:
DETERMINISTIC
→ no LLM
```

```text
Task:
"Help me schedule this"

Execution:
INTERACTIVE
→ small LLM
```

```text
Task:
"Research this topic and prepare a report"

Execution:
AUTONOMOUS
→ strong LLM
```

The Task doesn't care which physical model performs the reasoning.

---

# 16. Execution Policy

This is where we can formalize that.

Something like:

```text
ExecutionPolicy

mode:
    deterministic
    interactive
    autonomous

reasoning_requirement:
    none
    low
    medium
    high

model_preference:
    optional

max_turns:
    ...

timeout:
    ...

retry_policy:
    ...

human_approval:
    ...
```

But again:

**policy ≠ actual model identity.**

The model router can determine:

```text
reasoning_requirement = HIGH
        ↓
local strong model
```

or:

```text
reasoning_requirement = HIGH
        ↓
cloud model
```

depending on future deployment.

---

# 17. Execution Context

This is where our earlier discussions about context management become relevant.

The Execution shouldn't simply say:

```text
send everything to LLM
```

Instead:

```text
Execution
   │
   ▼
Context Builder
   │
   ├── Task
   ├── relevant state
   ├── relevant memories
   ├── recent observations
   ├── tool results
   └── current objective
          │
          ▼
        LLM
```

This means **context is constructed per reasoning step**.

Not:

```text
Execution starts
↓
dump entire history into LLM
↓
keep growing it forever
```

That distinction will become extremely important later.

---

# 18. LLM invocation is therefore a sub-operation

Something like:

```text
Execution E1
│
├── Step 1
│     └── Context Assembly
│
├── Step 2
│     └── LLM Invocation
│
├── Step 3
│     └── Tool Execution
│
├── Step 4
│     └── Observation
│
├── Step 5
│     └── Context Assembly
│
├── Step 6
│     └── LLM Invocation
│
└── Step 7
      └── Completion
```

This gives us a very clean separation:

```text
Execution Runtime
       │
       ├── controls lifecycle
       ├── manages state
       ├── handles persistence
       ├── invokes tools
       └── invokes LLM
```

The LLM itself doesn't control the entire runtime.

---

# 19. Tool calls

The same principle applies to tools.

LLM says:

```text
CALL calendar.search(...)
```

The Execution Runtime should:

```text
1. Validate tool call
2. Check permissions
3. Check constraints
4. Execute tool
5. Capture result
6. Persist result
7. Return observation to LLM
```

So:

```text
LLM
 ↓
Tool Request
 ↓
Execution Runtime
 ↓
Authorization
 ↓
Tool
 ↓
Result
 ↓
Persist
 ↓
LLM
```

The OpenAI Agents SDK follows this basic model: tools are callable capabilities, the runner executes tool calls and feeds their results back into the agent loop. ([OpenAI GitHub](https://openai.github.io/openai-agents-python/running_agents/?utm_source=chatgpt.com "Running agents - OpenAI Agents SDK"))

---

# 20. Why authorization must sit outside the LLM

Suppose the LLM decides:

```text
send_email(...)
```

The model should not be the ultimate authority.

Instead:

```text
LLM
 ↓
REQUEST
 ↓
Policy Engine
 ├── allowed?
 ├── parameters valid?
 ├── human approval?
 └── constraints?
        │
        ▼
      TOOL
```

This is particularly important for autonomous agents.

OpenAI's Agents SDK, for example, supports tools that require approval and pauses the run until approval is supplied. ([OpenAI GitHub](https://openai.github.io/openai-agents-python/human_in_the_loop/?utm_source=chatgpt.com "Human-in-the-loop - OpenAI Agents SDK"))

LangGraph likewise models human approval as an interrupt around execution, with state checkpointed before waiting. ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/interrupts?utm_source=chatgpt.com "Interrupts - Docs by LangChain"))

---

# 21. Human approval becomes a WAITING Execution

Suppose:

```text
Autonomous Agent
    ↓
"Send email"
```

Policy:

```text
send_email requires approval
```

Then:

```text
Execution
status = WAITING

waiting_for:
    HUMAN_APPROVAL

checkpoint:
    saved
```

LLM:

```text
not running
```

Process:

```text
doesn't need to stay alive
```

Later:

```text
USER APPROVES
      ↓
APPROVAL_RECEIVED
      ↓
Execution resumes
      ↓
LLM/tool continues
```

Both OpenAI Agents SDK and LangGraph explicitly support this pause/resume pattern. ([OpenAI GitHub](https://openai.github.io/openai-agents-python/human_in_the_loop/?utm_source=chatgpt.com "Human-in-the-loop - OpenAI Agents SDK"))

---

# 22. What happens if the computer crashes?

Suppose:

```text
Execution E1

Step 1 ✓
Step 2 ✓
Step 3 → running
```

Computer crashes.

After restart:

```text
Runtime starts
 ↓
load incomplete executions
 ↓
E1 = recoverable
 ↓
restore checkpoint
 ↓
continue
```

The key question becomes:

> What exactly is safe to repeat?

This is where **idempotency** becomes critical.

LangGraph explicitly recommends placing API calls inside checkpointed tasks and designing them to be idempotent because a step may execute again after failure. ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/functional-api?utm_source=chatgpt.com "Functional API overview - Docs by LangChain"))

---

# 23. Exactly-once execution is usually the wrong goal

This is important.

It is extremely difficult to guarantee:

```text
"this external action happens exactly once"
```

under arbitrary crashes.

Imagine:

```text
Execution
 ↓
send_email()
 ↓
email server accepts email
 ↓
computer crashes
```

Did the action happen?

The local system doesn't know.

If we retry:

```text
send_email()
```

we might send twice.

Therefore robust systems generally use combinations of:

```text
idempotency keys
deduplication
transactional state
reconciliation
retry policies
```

rather than pretending exactly-once external side effects are universally achievable.

This should be part of our architecture from the beginning.

---

# 24. Execution attempts

Therefore I'd introduce:

```text
Execution
    │
    ├── Attempt 1
    ├── Attempt 2
    └── Attempt 3
```

For example:

```text
Execution E1
status = FAILED
attempt = 1
```

Retry:

```text
Execution E1
attempt = 2
status = RUNNING
```

This is different from creating:

```text
Execution E2
```

because it's still the same logical attempt to fulfill the Task occurrence.

---

# 25. Execution vs Attempt

I recommend:

```text
Task
  ↓
Execution
  ↓
Attempt
  ↓
Steps
```

Example:

```text
Task T1
"Analyze today's emails"

Execution E1
"Sept 15 occurrence"

Attempt A1
"first runtime attempt"

Steps:
  S1
  S2
  S3
```

If it fails:

```text
Attempt A1 → FAILED

Attempt A2 → RUNNING
```

This gives us a very rich failure model.

---

# 26. Why this is useful

Suppose:

```text
Task T1
Execution E1

Attempt 1:
LLM timeout

Attempt 2:
Gmail timeout

Attempt 3:
success
```

We can distinguish:

```text
Task succeeded
Execution succeeded
Attempts 1 and 2 failed
Attempt 3 succeeded
```

Without conflating everything.

---

# 27. Execution can also spawn another Task

This is another important point.

Suppose an autonomous agent discovers:

> "This requires user approval tomorrow."

It could create:

```text
Task T2
```

while its current execution remains:

```text
E1 = completed
```

So:

```text
Execution E1
    │
    └── TASK_CREATED event
              │
              ▼
           Task T2
```

This creates chains of work.

---

# 28. Execution can also wait for another Task

Suppose:

```text
Task A
Download dataset

Task B
Analyze dataset
```

B depends on A.

Execution B:

```text
WAITING
waiting_for = Task A
```

When A completes:

```text
TASK_COMPLETED(A)
       ↓
Dependency Resolver
       ↓
Execution B becomes QUEUED
```

No LLM required.

---

# 29. Execution can therefore be event-driven internally

This is the really interesting part.

Instead of thinking:

```text
while not finished:
    think()
```

we can think:

```text
Execution state
      │
      ▼
What event happened?
      │
      ▼
What should happen next?
      │
      ├── LLM
      ├── Tool
      ├── Wait
      ├── Human
      ├── Retry
      └── Complete
```

So an agent runtime is fundamentally a **state machine reacting to events**.

The LLM is one possible decision-making component inside that state machine.

---

# 30. This is a major architectural insight

The system isn't:

```text
LLM
 ↓
tools
 ↓
LLM
 ↓
tools
```

That's only the **reasoning loop**.

The complete system is:

```text
                    EVENT
                      │
                      ▼
                Execution State
                      │
                      ▼
                Runtime Decision
                      │
          ┌───────────┼────────────┐
          ▼           ▼            ▼
        LLM         TOOL         WAIT
          │           │            │
          └───────────┼────────────┘
                      ▼
                 New State
                      │
                      ▼
                    EVENT
```

That's much closer to how a robust autonomous system should be designed.

---

# 31. Now we can define "agent"

This gives us a surprisingly clean definition:

> **An Agent is a reasoning component capable of making decisions within an Execution; it is not itself the persistent Execution.**

That's a very useful architectural boundary.

So:

```text
Execution
    │
    └── Agent
          │
          └── LLM
```

rather than:

```text
Agent = LLM = Execution
```

These are three different concepts.

---

# 32. What "Agent is running" actually means

People often say:

> "My agent is running."

Technically that could mean several things:

### A. Runtime is running

```text
Event/Task infrastructure = active
```

### B. Execution is active

```text
Execution = RUNNING
```

### C. Agent loop is active

```text
LLM is currently reasoning
```

### D. Model server is loaded

```text
Model weights resident in RAM/VRAM
```

These are **not the same thing**.

For a local AI system, this distinction is extremely important.

---

# 33. A realistic local architecture

Eventually, something like:

```text
                 LOCAL MACHINE
┌──────────────────────────────────────────┐
│                                          │
│              Active Runtime              │
│                                          │
│  ┌─────────┐    ┌─────────────┐          │
│  │ Events  │───→│ Task Engine │          │
│  └─────────┘    └──────┬──────┘          │
│                        │                 │
│                        ▼                 │
│                 Execution Engine         │
│                        │                 │
│              ┌─────────┼─────────┐       │
│              ▼         ▼         ▼       │
│          Determ.   Interactive Autonomous│
│                         │         │       │
│                         ▼         ▼       │
│                      Small     Strong     │
│                       LLM       LLM       │
│                                          │
└──────────────────────────────────────────┘
```

The machine is always running the **runtime**.

The models are invoked when necessary.

---

# 34. But do we actually need the runtime always running?

For a truly local autonomous system, generally **yes**, at least some lightweight process must be available if you expect it to react immediately to external events.

But that process does not have to be an LLM.

It might just be:

```text
scheduler
event listener
task database
execution manager
```

For example:

```text
RAM:
Runtime = 100 MB

LLM:
loaded only when needed
```

This is vastly more efficient than:

```text
24/7 LLM inference loop
```

---

# 35. The scheduler itself is not an agent

This is another distinction worth freezing.

```text
Scheduler
```

doesn't reason.

It says:

```text
08:00 reached
```

and generates:

```text
SCHEDULE_DUE
```

Then:

```text
Task Engine
```

decides:

```text
Which task does this correspond to?
```

Then:

```text
Execution Engine
```

decides:

```text
How should it execute?
```

Then:

```text
Agent
```

may reason.

That gives:

```text
Scheduler
   ↓
Event
   ↓
Task
   ↓
Execution
   ↓
Agent
   ↓
LLM
```

Very clean.

---

# 36. This also explains external events

Suppose:

```text
New email
```

External integration:

```text
Email Listener
     ↓
EMAIL_RECEIVED
```

Then:

```text
Event Router
     ↓
Task Trigger Matcher
```

Then perhaps:

```text
Task:
"Summarize important emails"
```

Then:

```text
Execution
```

Then:

```text
Strong LLM
```

Again, **the email listener doesn't invoke the LLM directly**.

That would couple infrastructure to intelligence.

---

# 37. Execution should therefore have a "wake reason"

I think this is a useful field.

```text
wake_reason
```

Examples:

```text
TASK_TRIGGERED
TOOL_RESULT
TIMER_EXPIRED
HUMAN_INPUT
DEPENDENCY_COMPLETED
RETRY
SYSTEM_RECOVERY
EXTERNAL_EVENT
```

Then the runtime knows why the execution became runnable.

Example:

```text
Execution E1

status:
    QUEUED

wake_reason:
    HUMAN_INPUT
```

This is extremely useful for debugging.

---

# 38. Execution also needs a wake condition

When waiting:

```text
status = WAITING
```

we should know:

```text
waiting_for:
    timer
```

or:

```text
waiting_for:
    human
```

or:

```text
waiting_for:
    task:T123
```

or:

```text
waiting_for:
    event:EMAIL_RECEIVED
```

or:

```text
waiting_for:
    external_operation
```

So:

```text
WAITING
├── condition
├── timeout
└── wake policy
```

---

# 39. Execution can then be modeled as a state transition system

Something like:

```text
State + Event
      ↓
Transition
      ↓
New State + Actions
```

For example:

```text
WAITING_FOR_HUMAN
+
HUMAN_APPROVAL_RECEIVED
        ↓
RUNNING
+
resume agent
```

Or:

```text
RUNNING
+
TOOL_COMPLETED
        ↓
RUNNING
+
invoke LLM
```

Or:

```text
RUNNING
+
TASK_COMPLETED
        ↓
COMPLETED
```

This is much more deterministic than letting the LLM control the runtime itself.

---

# 40. The LLM should make decisions, not control durability

This is one of the architectural principles I'd strongly recommend.

Bad:

```text
LLM:
"I'll wait until tomorrow."

Python:
time.sleep(86400)
```

Better:

```text
LLM decision:
WAIT_UNTIL(2026-09-16T09:00)

Runtime:
persist waiting state
schedule wake event
terminate current execution process
```

Then tomorrow:

```text
SCHEDULE_DUE
 ↓
resume Execution
 ↓
LLM
```

The model expresses the desired action.

The runtime implements it.

---

# 41. Same principle for retries

LLM shouldn't say:

```text
retry in 5 minutes
```

and then sleep.

Instead:

```text
Execution
 ↓
retry policy
 ↓
RETRY_AT = 5 minutes
 ↓
WAITING
```

Then:

```text
timer
 ↓
EXECUTION_RETRY_DUE
 ↓
QUEUED
```

This makes retries durable.

---

# 42. Same principle for human interaction

LLM says:

```text
I need approval.
```

Runtime:

```text
WAITING_FOR_HUMAN
```

UI:

```text
Approval request
```

Human responds:

```text
APPROVED
```

Runtime:

```text
resume execution
```

Again:

```text
LLM expresses
Runtime enforces
```

---

# 43. Now compare the major architectures

### OpenAI Agents SDK

Very good at:

```text
Agent
 ↓
LLM
 ↓
Tool
 ↓
LLM
```

It provides a built-in loop, tools, sessions, handoffs, guardrails, and HITL. ([OpenAI GitHub](https://openai.github.io/openai-agents-python/?utm_source=chatgpt.com "OpenAI Agents SDK"))

But for truly long-running durable workflows, its own documentation points toward integrations such as Temporal, Dapr, or Restate. ([OpenAI GitHub](https://openai.github.io/openai-agents-python/running_agents/?utm_source=chatgpt.com "Running agents - OpenAI Agents SDK"))

### LangGraph

Much closer to:

```text
State
 ↓
Node
 ↓
Checkpoint
 ↓
Node
 ↓
Interrupt
 ↓
Resume
```

It explicitly provides persistence, fault tolerance, interrupts, replay, and long-running execution. ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/persistence?utm_source=chatgpt.com "Persistence - Docs by LangChain"))

### Temporal

Much closer to:

```text
Durable Workflow
 ↓
Activities
 ↓
Timers
 ↓
Retries
 ↓
Signals
 ↓
Continue
```

Its fundamental concern is making execution survive crashes and infrastructure failure over arbitrary durations. ([Temporal Docs](https://docs.temporal.io/?utm_source=chatgpt.com "Temporal Platform Documentation"))

---

# 44. For our architecture, I'd combine the ideas rather than copy any one

The conceptual stack becomes:

```text
                    ACTIVE SYSTEM
                          │
                 ┌────────┴────────┐
                 │  Event System    │
                 └────────┬────────┘
                          │
                       Tasks
                          │
                    Executions
                          │
                ┌─────────┴─────────┐
                │ Execution Runtime │
                └─────────┬─────────┘
                          │
               ┌──────────┼──────────┐
               ▼          ▼          ▼
            Step        Wait       Interrupt
               │
               ▼
          Agent Loop
               │
          ┌────┴────┐
          ▼         ▼
         LLM       Tool
```

This is a strong architecture.

---

# 45. The complete lifecycle now

Let's put everything together.

User:

> "Every morning at 8, check my calendar and tell me if I have conflicts."

### Step 1 — Interactive

```text
USER_MESSAGE_RECEIVED
        ↓
Small LLM
        ↓
CREATE_TASK_REQUEST
```

### Step 2 — Task Engine

```text
Task created

T123
goal = identify calendar conflicts
trigger = daily 08:00
execution_mode = autonomous
```

### Step 3 — Nothing happens overnight

```text
T123 = ACTIVE
No Execution
No LLM
```

### Step 4 — Scheduler

```text
08:00
 ↓
SCHEDULE_DUE
```

### Step 5 — Trigger Matcher

```text
SCHEDULE_DUE
 ↓
T123 matches
```

### Step 6 — Execution Engine

```text
Execution E456
status = QUEUED
```

### Step 7 — Agent

```text
E456
 ↓
Context assembly
 ↓
Strong LLM
```

### Step 8 — Tool

```text
LLM
 ↓
calendar.search
 ↓
results
```

### Step 9 — Agent resumes

```text
results
 ↓
LLM
 ↓
"Two conflicts found."
```

### Step 10 — Completion

```text
E456 = COMPLETED
```

### Step 11 — Output event

```text
EXECUTION_COMPLETED
```

### Step 12 — Task remains active

```text
T123 = ACTIVE
```

Tomorrow:

```text
repeat
```

That is the entire autonomous lifecycle.

---

# 46. And now we can finally answer the original question you asked at the very beginning

You originally asked, essentially:

> **How does a local AI agent stay active? What triggers it?**

The answer is:

### It usually shouldn't be the LLM that stays active.

Instead:

```text
                    ALWAYS AVAILABLE
                         │
             ┌───────────┴───────────┐
             │                       │
         Event System            Scheduler
             │                       │
             └───────────┬───────────┘
                         ▼
                       Tasks
                         │
                         ▼
                     Executions
                         │
                  when reasoning
                         ▼
                        LLM
                         │
                    tool calls
                         │
                         ▼
                  execution state
                         │
                         ▼
                       Events
```

The **runtime stays alive**.

The **Task stays persistent**.

The **Execution state stays persistent**.

The **LLM wakes up when reasoning is required**.

---

# 47. Our three layers now become even cleaner

Remember your earlier architecture:

```text
DETERMINISTIC
INTERACTIVE
AUTONOMOUS
```

We can now interpret them as **execution strategies**, not different event systems.

```text
                         TASK
                           │
                   Execution Policy
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
   DETERMINISTIC      INTERACTIVE      AUTONOMOUS
          │                │                │
          │                ▼                ▼
          │             Small LLM       Strong LLM
          │
          ▼
       No LLM
```

And that's actually a very powerful abstraction.

---

# 48. One thing I would change from our earlier terminology

I would now avoid saying:

> "The autonomous agent is running."

Instead, architecturally:

> **"An autonomous Execution is active."**

The autonomous agent/model is merely the reasoning engine currently being invoked by that execution.

That distinction will prevent a _lot_ of architectural problems later.

---

# 49. The resulting hierarchy

I think we now have a very solid hierarchy:

```text
SYSTEM
│
├── EVENT SYSTEM
│
├── TASK SYSTEM
│
└── EXECUTION SYSTEM
      │
      ├── Execution State
      ├── Attempts
      ├── Steps
      ├── Waiting
      ├── Interrupts
      ├── Checkpoints
      ├── Retry
      │
      └── Agent Runtime
             │
             ├── Context Assembly
             ├── LLM
             ├── Tools
             └── Observations
```

And importantly:

```text
Event
  ≠ Task
  ≠ Execution
  ≠ Agent
  ≠ LLM
```

They are distinct abstractions.

---

# 50. I think we should freeze this before moving on

The three core contracts are now:

### Event

```text
Immutable fact.
```

### Task

```text
Persistent responsibility.
```

### Execution

```text
Durable attempt to fulfill a responsibility.
```

And:

```text
Event
  ↓
may activate
  ↓
Task
  ↓
creates
  ↓
Execution
  ↓
invokes when necessary
  ↓
Agent / LLM / Tools
  ↓
produces
  ↓
Event
```

That gives us the foundation for the **Active Layer**.

---

## The next thing I'd investigate

There is one remaining architectural question before we start designing concrete components:

> **Who/what is responsible for waking the system up?**

Because we now have several fundamentally different kinds of wake-ups:

```text
USER MESSAGE
SCHEDULE
FILE CHANGE
NETWORK EVENT
DEVICE EVENT
TOOL RESULT
TASK COMPLETION
HUMAN APPROVAL
EXTERNAL WEBHOOK
CONDITION BECOMES TRUE
RETRY TIMER
SYSTEM STARTUP
RECOVERY AFTER CRASH
```

This takes us directly into the **Event Intake / Event Bus / Scheduler / Trigger Engine / Execution Dispatcher** problem.

And I think we should examine that next **before discussing any concrete code or LangGraph implementation**, because that's where the actual architecture of the Active Layer gets determined.

Yes. I think this is the right point to do a **formal event taxonomy before designing the architecture**.

I researched this against current event-driven and agent-runtime patterns, particularly durable workflow systems and agent runtimes. The important finding is that there isn't one universal taxonomy of "agent events"; instead, mature systems distinguish **external stimuli, temporal triggers, workflow/runtime events, state changes, and agent-internal events**. AWS's current guidance for agentic systems, for example, explicitly treats user requests, file uploads, sensor signals, and model results as events that can trigger downstream work. ([AWS Documentation](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-serverless/event-driven-architecture.html?utm_source=chatgpt.com "Event-driven architecture: The backbone of serverless AI - AWS Prescriptive Guidance")) Temporal focuses on durable timers, workflow state, signals, retries and recovery, while OpenAI's Agents SDK exposes agent/tool/handoff lifecycle events and durable pause/resume state. ([Temporal Docs](https://docs.temporal.io/?utm_source=chatgpt.com "Temporal Platform Documentation"))

The taxonomy below is therefore **our architectural taxonomy**, informed by those systems—not a claim that an external standard defines exactly these 14 categories.

---

# 1. First principle: what qualifies as an Event?

I'd define an Event as:

> **A discrete occurrence that may cause the system to evaluate whether some state, task, execution, or agent behavior should change.**

An event should answer:

```text
WHAT happened?
WHEN did it happen?
WHERE did it originate?
WHAT entity does it concern?
WHAT data accompanies it?
```

For example:

```text
EVENT
type: EMAIL_RECEIVED
source: gmail
timestamp: ...
entity: message_123
payload: {...}
```

But importantly:

> **An event does not imply that anything must happen.**

It is simply a fact.

```text
EMAIL_RECEIVED
      │
      ├── no matching trigger → record only
      │
      └── matching trigger → activate task
```

That distinction will be extremely important later.

---

# 2. The master taxonomy

I would currently use these 14 categories:

|#|Category|Primary source|
|---|---|---|
|1|Human|User/UI/voice|
|2|Temporal|Clock/scheduler|
|3|System|OS/runtime|
|4|Application|Application services|
|5|External|External services|
|6|Device|Hardware/peripherals|
|7|Network|Connectivity/network stack|
|8|File/Data|Files/databases/data streams|
|9|Task|Task subsystem|
|10|Execution|Execution runtime|
|11|Agent/LLM|Model/runtime|
|12|Condition/State|State transition engine|
|13|Recovery/Lifecycle|Runtime lifecycle|
|14|Composite|Event correlation/aggregation|

Now let's go through each one carefully.

---

# 3. Human Events

These are events originating from a person.

Examples:

```text
USER_MESSAGE
VOICE_INPUT
TEXT_INPUT
USER_CLICK
USER_SELECTION
USER_APPROVAL
USER_REJECTION
USER_CONFIRMATION
USER_CANCELLATION
USER_CORRECTION
USER_FEEDBACK
USER_INTERRUPT
```

## Can it happen spontaneously?

**Yes.**

The system doesn't schedule:

> "At 10:32 user will ask something."

The human produces the event.

## What produces it?

Potential sources:

```text
GUI
CLI
voice interface
mobile client
keyboard shortcut
API
web interface
```

## Listener?

**Yes.**

Something has to receive user interaction.

For example:

```text
UI
 ↓
Input Adapter
 ↓
USER_MESSAGE
```

## Polling?

Generally **no**.

You want event-driven input.

For example:

```text
HTTP request
WebSocket message
GUI callback
microphone stream
```

rather than:

```text
while True:
    check_if_user_said_something()
```

---

## Scheduler?

**No.**

The human is the trigger.

## Creates Task?

Potentially.

Example:

> "Every Monday remind me to submit the report."

```text
USER_MESSAGE
 ↓
Interactive LLM
 ↓
CREATE_TASK
```

But:

> "What's the weather?"

doesn't necessarily create a persistent Task.

---

## Wakes Execution?

Potentially.

For example:

```text
USER_APPROVAL
 ↓
WAITING Execution
 ↓
RUNNING
```

OpenAI's current agent runtime explicitly models human approval as an interruption that pauses a run and later resumes it from serialized run state. ([OpenAI GitHub](https://openai.github.io/openai-agents-js/guides/human-in-the-loop/?utm_source=chatgpt.com "Human-in-the-loop | OpenAI Agents SDK"))

## Can interrupt?

**Yes — highest practical priority in many systems.**

A user request should normally be able to interrupt background autonomous work.

## Require LLM?

Sometimes.

```text
"Schedule a meeting tomorrow"
→ LLM useful
```

but:

```text
Cancel task #123
→ deterministic
```

## Priority

I'd classify raw human interaction as:

```text
CRITICAL / VERY HIGH
```

but the **content** can subsequently change the resulting task priority.

## Can be lost?

Potentially disastrous.

A user message should generally be durably acknowledged once accepted.

## Persistence?

**Yes.**

At minimum:

```text
event_id
timestamp
source
input
conversation/session
```

---

# 4. Temporal Events

These are generated by time.

Examples:

```text
TIMER_EXPIRED
SCHEDULE_DUE
DELAY_COMPLETE
CRON_TRIGGER
DEADLINE_REACHED
TIMEOUT
RECURRING_INTERVAL
```

Example:

```text
2026-09-16 08:00
       ↓
SCHEDULE_DUE
```

## Spontaneous?

Not really.

They are **clock-derived**.

## Producer?

```text
Scheduler
Timer subsystem
Clock
```

## Listener?

The scheduler itself is effectively the listener.

## Polling?

This is interesting.

A naïve scheduler could poll:

```text
every second → check timers
```

But production systems can use timer queues / OS timers / durable scheduling mechanisms.

Temporal explicitly provides durable timers and workflow execution that can survive outages and resume much later. ([Temporal Docs](https://docs.temporal.io/?utm_source=chatgpt.com "Temporal Platform Documentation"))

## Creates Task?

Sometimes.

For:

```text
every morning → check calendar
```

the schedule activates an existing Task.

So:

```text
SCHEDULE_DUE
 ↓
Task T123
 ↓
Execution
```

not necessarily:

```text
SCHEDULE_DUE
 ↓
new Task every time
```

---

## Wakes Execution?

**Yes.**

This is one of their primary purposes.

```text
WAITING
   ↓
TIMER_EXPIRED
   ↓
RUNNING
```

## Interrupt?

Normally **no**, unless the scheduled event has high priority.

## LLM?

Usually **no**.

The temporal event itself is deterministic.

The work it triggers may require an LLM.

## Priority

Depends on associated Task.

A deadline:

```text
DEADLINE_REACHED
```

could be critical.

A routine:

```text
DAILY_MEMORY_MAINTENANCE
```

could be low.

## Can be lost?

Potentially catastrophic for important schedules.

Therefore:

**persistent scheduling is required.**

---

# 5. System Events

Events generated by the operating system or runtime environment.

Examples:

```text
SYSTEM_STARTED
SYSTEM_SHUTDOWN
SYSTEM_SLEEP
SYSTEM_RESUME
PROCESS_STARTED
PROCESS_STOPPED
MEMORY_PRESSURE
CPU_PRESSURE
BATTERY_LOW
POWER_CONNECTED
POWER_DISCONNECTED
OS_NOTIFICATION
USER_LOGGED_IN
USER_LOGGED_OUT
```

Potentially:

```text
SCREEN_LOCKED
SCREEN_UNLOCKED
```

## Spontaneous?

Yes.

## Producer?

```text
OS
runtime
system services
```

## Listener?

Yes.

Usually through:

```text
OS API
system hooks
service callbacks
```

## Polling?

Depends on OS API.

Prefer native event notifications where available.

## Scheduler?

No.

## Creates Task?

Usually no.

But it can activate one.

Example:

```text
BATTERY_LOW
 ↓
Task: save/checkpoint active work
```

## Wakes Execution?

Yes.

Example:

```text
SYSTEM_RESUMED
 ↓
Recovery Manager
 ↓
resume incomplete executions
```

## Interrupt?

Potentially.

For example:

```text
BATTERY_CRITICAL
```

could cause background work to be suspended.

## LLM?

Generally no.

## Priority

System safety events can be:

```text
CRITICAL
```

Routine events:

```text
LOW
```

## Persistence?

Important events should be persisted.

But not every low-level OS event needs to be stored forever.

---

# 6. Application Events

These are generated by applications or services inside the system.

Examples:

```text
EMAIL_RECEIVED
CALENDAR_UPDATED
MESSAGE_SENT
DOWNLOAD_COMPLETED
DATABASE_UPDATED
APPLICATION_STARTED
APPLICATION_ERROR
MEDIA_FINISHED
DOCUMENT_CREATED
```

Imagine a calendar service:

```text
calendar
   ↓
CALENDAR_EVENT_CREATED
```

## Spontaneous?

Yes.

The application can generate them whenever its state changes.

## Producer?

```text
application
service
plugin
integration
```

## Listener?

Yes.

## Polling?

Ideally no.

For services with webhooks/events:

```text
service → webhook → event intake
```

For services that don't provide events:

```text
polling adapter → detect change → event
```

This is an important distinction.

---

# 7. External Events

These originate outside our system.

Examples:

```text
Gmail webhook
GitHub webhook
Slack event
weather alert
bank transaction
cloud service event
API callback
IoT service event
```

AWS's event-driven agent guidance explicitly includes external occurrences such as uploads and sensor signals as event sources. ([AWS Documentation](https://docs.aws.amazon.com/prescriptive-guidance/latest/agentic-ai-serverless/event-driven-architecture.html?utm_source=chatgpt.com "Event-driven architecture: The backbone of serverless AI - AWS Prescriptive Guidance"))

## Spontaneous?

Yes.

From our system's perspective.

## Producer?

External system.

## Listener?

Usually an:

```text
External Event Adapter
```

For example:

```text
GitHub
 ↓
Webhook
 ↓
GitHub Adapter
 ↓
GITHUB_PR_OPENED
```

## Polling?

Depends entirely on external system.

Preferred:

```text
webhook / push
```

Fallback:

```text
polling
```

## Scheduler?

Only for polling.

## Creates Task?

Potentially.

Example:

```text
GITHUB_PR_OPENED
 ↓
Task:
Review PR
```

## Wakes Execution?

Yes.

## Interrupt?

Potentially.

An urgent external alert may preempt background work.

## LLM?

Sometimes.

The event itself doesn't require an LLM.

The response might.

## Priority

Should be assigned based on source/event semantics.

---

# 8. Device Events

Hardware-generated events.

Examples:

```text
USB_CONNECTED
USB_DISCONNECTED
BLUETOOTH_DEVICE_CONNECTED
BLUETOOTH_DEVICE_DISCONNECTED
MICROPHONE_AVAILABLE
CAMERA_AVAILABLE
SENSOR_READING
BUTTON_PRESS
KEY_PRESS
MOUSE_EVENT
HEADPHONES_CONNECTED
```

## Spontaneous?

Yes.

## Producer?

Hardware/OS.

## Listener?

Usually.

## Polling?

Depends on device.

Prefer:

```text
interrupt
callback
OS event
```

Polling may be unavoidable for some hardware.

## Scheduler?

No.

## Task?

Potentially.

Example:

```text
HEADPHONES_CONNECTED
 ↓
Task:
switch audio profile
```

## LLM?

Usually unnecessary.

Some higher-level interpretation could use one.

---

# 9. File/Data Events

This category is broader than just filesystem events.

### Filesystem

```text
FILE_CREATED
FILE_MODIFIED
FILE_DELETED
FILE_MOVED
DIRECTORY_CHANGED
```

### Data

```text
DATABASE_RECORD_CREATED
DATABASE_RECORD_UPDATED
DATASET_UPDATED
STREAM_MESSAGE_RECEIVED
```

## Producer

Could be:

```text
OS
database
application
data pipeline
```

## Listener?

Yes.

Filesystem watchers can provide events.

## Polling?

Prefer watchers.

For example:

```text
FILE_CHANGED
```

rather than:

```text
every 2 seconds:
    scan directory
```

But some systems only expose polling APIs.

## Task?

Potentially.

Example:

```text
FILE_CREATED
 ↓
Task:
summarize document
```

## LLM?

Potentially.

```text
PDF_CREATED
 ↓
extract text
 ↓
LLM summarize
```

## Priority

Usually normal/low unless explicitly configured.

## Persistence?

The raw file event may not need indefinite persistence.

But if it activates a Task/Execution, that resulting relationship should be persisted.

---

# 10. Task Events

Now we're inside our own task subsystem.

Examples:

```text
TASK_CREATED
TASK_UPDATED
TASK_ENABLED
TASK_DISABLED
TASK_TRIGGERED
TASK_DUE
TASK_EXPIRED
TASK_CANCELLED
TASK_COMPLETED
TASK_FAILED
TASK_RETRY_REQUESTED
TASK_BLOCKED
TASK_UNBLOCKED
```

These are extremely important because the system starts becoming **self-reactive**.

Example:

```text
TASK_COMPLETED
 ↓
Task B dependency satisfied
 ↓
TASK_UNBLOCKED
```

## Spontaneous?

They arise from system activity.

## Producer?

```text
Task Manager
Scheduler
Execution Manager
User
```

## Listener?

Yes—the rest of the runtime may subscribe.

## Polling?

No.

These should be internally event-driven.

## Scheduler?

Some require scheduler involvement.

## Create Task?

Potentially.

For example:

```text
TASK_FAILED
 ↓
Retry policy
 ↓
new attempt
```

or:

```text
TASK_COMPLETED
 ↓
recurring task
 ↓
schedule next occurrence
```

## Wake Execution?

Absolutely.

```text
TASK_TRIGGERED
 ↓
Execution created
```

## Interrupt?

Potentially.

## LLM?

Usually no.

The **task's execution** may use one.

---

# 11. Execution Events

These describe what is happening to an individual Execution.

Examples:

```text
EXECUTION_CREATED
EXECUTION_QUEUED
EXECUTION_STARTED
EXECUTION_PAUSED
EXECUTION_RESUMED
EXECUTION_WAITING
EXECUTION_WAKE
EXECUTION_COMPLETED
EXECUTION_FAILED
EXECUTION_CANCELLED
EXECUTION_TIMEOUT
EXECUTION_RETRY
```

Then lower-level events:

```text
STEP_STARTED
STEP_COMPLETED
STEP_FAILED

TOOL_REQUESTED
TOOL_STARTED
TOOL_COMPLETED
TOOL_FAILED

CHECKPOINT_CREATED
```

This is closely related to the event model exposed by agent runtimes: OpenAI's Agents SDK, for example, exposes lifecycle events for agent starts/ends, handoffs, tool starts/ends and other run activity. ([OpenAI GitHub](https://openai.github.io/openai-agents-js/guides/agents/?utm_source=chatgpt.com "Agents | OpenAI Agents SDK"))

## Why do we need them?

Because an Execution can become an **event source itself**.

Example:

```text
Execution A completed
        ↓
EXECUTION_COMPLETED
        ↓
Task B dependency satisfied
```

This is how autonomous chains can emerge without an LLM explicitly orchestrating everything.

---

# 12. Agent / LLM Events

Now we reach events generated by the reasoning layer.

Examples:

```text
LLM_REQUESTED
LLM_STARTED
LLM_TOKEN_STREAM
LLM_COMPLETED
LLM_FAILED

TOOL_REQUESTED
TOOL_APPROVAL_REQUIRED
TOOL_COMPLETED

AGENT_STARTED
AGENT_COMPLETED
AGENT_HANDOFF
AGENT_INTERRUPTED

REASONING_FAILED
OUTPUT_INVALID
GUARDRAIL_TRIGGERED
```

OpenAI's current SDK explicitly models events such as `agent_start`, `agent_end`, handoffs, tool start/end, and run interruptions. ([OpenAI GitHub](https://openai.github.io/openai-agents-js/guides/agents/?utm_source=chatgpt.com "Agents | OpenAI Agents SDK"))

## Spontaneous?

They arise during agent execution.

## Producer?

```text
Agent runtime
LLM runtime
tool runtime
```

## Listener?

Yes.

Primarily:

```text
Execution Manager
Observability
UI
```

## Polling?

No.

## Scheduler?

Normally no.

## Creates Task?

Potentially.

For example, an agent could determine:

> "This requires a follow-up tomorrow."

That should ideally produce a **structured Task creation request**, rather than letting raw model text directly modify the scheduler.

## Wakes Execution?

Yes.

Especially:

```text
TOOL_COMPLETED
HUMAN_APPROVAL
LLM_COMPLETED
```

## Interrupt?

Yes.

A model-generated approval request can suspend an execution. OpenAI's documented HITL mechanism does exactly this: a tool call can produce an interruption, the run state is serialized, and the run is resumed after approval/rejection. ([OpenAI GitHub](https://openai.github.io/openai-agents-js/guides/human-in-the-loop/?utm_source=chatgpt.com "Human-in-the-loop | OpenAI Agents SDK"))

## Priority?

Usually inherited from the Execution.

An individual token event should **not** compete with a user event in the global scheduler.

That's an important architectural boundary.

---

# 13. Condition / State-Change Events

This is a particularly powerful category.

An event doesn't always mean:

> "Something happened."

It can mean:

> **"A condition that we care about has become true."**

Examples:

```text
BATTERY_BELOW_10_PERCENT
TEMPERATURE_ABOVE_THRESHOLD
CALENDAR_CONFLICT_EXISTS
FILE_COUNT_EXCEEDS_LIMIT
TASKS_OVERDUE
PERSON_HAS_NOT_REPLIED
NETWORK_UNAVAILABLE
MODEL_READY
USER_IS_IDLE
```

This category requires careful design.

Suppose:

```text
battery = 9%
```

Is that an event?

Not necessarily.

It is a **state**.

The event is:

```text
BATTERY_CROSSED_BELOW_10_PERCENT
```

That distinction prevents repeated triggers.

Bad:

```text
09:00 → battery 9%
09:01 → battery 9%
09:02 → battery 9%
...
```

Good:

```text
battery 11%
     ↓
battery 9%
     ↓
THRESHOLD_CROSSED
```

---

# 14. Conditions are where polling becomes legitimate

Suppose we want:

> "Tell me when CPU usage remains above 90% for five minutes."

There may not be a native event for this.

We may need:

```text
sensor
 ↓
sampling
 ↓
condition evaluator
 ↓
condition becomes true
 ↓
EVENT
```

So:

```text
Polling
    ↓
State observation
    ↓
Condition engine
    ↓
Event
```

This means **polling is not inherently bad**.

Polling is bad when used unnecessarily.

A condition that cannot otherwise be observed may legitimately require it.

---

# 15. Recovery / Lifecycle Events

These are crucial for the architecture we're discussing.

Examples:

```text
RUNTIME_STARTED
RUNTIME_STOPPING
RUNTIME_STOPPED

RECOVERY_STARTED
RECOVERY_COMPLETED
RECOVERY_FAILED

CHECKPOINT_LOADED
ORPHANED_EXECUTION_FOUND
STALE_EXECUTION_FOUND

MODEL_STARTED
MODEL_STOPPED
MODEL_LOAD_FAILED
```

Suppose the machine crashes.

On restart:

```text
SYSTEM_STARTED
       ↓
RUNTIME_STARTED
       ↓
RECOVERY_STARTED
       ↓
load persistent state
       ↓
find RUNNING executions
       ↓
determine which can resume
       ↓
RECOVERY_COMPLETED
```

Durable workflow systems explicitly treat crash recovery as a first-class concern. Temporal's core model is that execution can resume after crashes, network failures, or infrastructure outages. ([Temporal Docs](https://docs.temporal.io/?utm_source=chatgpt.com "Temporal Platform Documentation"))

---

# 16. Composite Events

This is the most advanced category.

Sometimes no individual event should trigger anything.

But a **combination** should.

Example:

```text
EMAIL_RECEIVED
+
EMAIL_FROM_IMPORTANT_PERSON
+
USER_IS_IDLE
```

→

```text
IMPORTANT_EMAIL_REVIEW
```

Or:

```text
BATTERY_LOW
+
GPU_BUSY
+
NO_USER_INTERACTION
```

→

```text
SUSPEND_BACKGROUND_AI
```

Or:

```text
TASK_FAILED
+
RETRY_LIMIT_REACHED
+
TASK_PRIORITY = HIGH
```

→

```text
ESCALATE_FAILURE
```

This requires an **event correlation / condition engine**.

---

# 17. Composite events are where the architecture gets interesting

We now have:

```text
Raw Events
    ↓
Event Correlation
    ↓
Condition
    ↓
Derived Event
```

Example:

```text
EMAIL_RECEIVED
      │
      ├── sender = boss
      ├── contains "urgent"
      └── deadline < 24h
                │
                ▼
       IMPORTANT_EMAIL_DETECTED
```

That derived event can then trigger:

```text
Task
 ↓
Execution
 ↓
LLM
```

This keeps the LLM out of simple event correlation when deterministic rules are sufficient.

---

# 18. Now let's answer the 10 questions systematically

Here's the high-level matrix.

|Event Type|Spontaneous|Listener|Polling|Scheduler|Task|Wake Execution|Interrupt|LLM|Persistence|
|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|
|Human|✓|✓|Usually no|No|Maybe|✓|✓|Maybe|**Yes**|
|Temporal|Clock|Scheduler|Maybe|**Yes**|Maybe|✓|Maybe|No|**Yes**|
|System|✓|✓|Maybe|No|Maybe|✓|✓|Rare|Selective|
|Application|✓|✓|Maybe|No|Maybe|✓|Maybe|Maybe|Selective|
|External|✓|✓|Maybe|Only if polling|Maybe|✓|Maybe|Maybe|**Yes**|
|Device|✓|✓|Maybe|No|Maybe|✓|Maybe|Rare|Selective|
|Network|✓|✓|Maybe|No|Maybe|✓|✓|Maybe|Selective|
|File/Data|✓|✓|Maybe|No|Maybe|✓|Maybe|Maybe|Selective|
|Task|Derived|Internal|No|Maybe|✓|✓|✓|Rare|**Yes**|
|Execution|Derived|Internal|No|No|Maybe|✓|✓|Maybe|**Yes**|
|Agent/LLM|Derived|Internal|No|No|Maybe|✓|✓|**Yes**|**Yes**|
|Condition|Derived|Condition engine|**Maybe**|Maybe|Maybe|✓|Maybe|Maybe|**Yes**|
|Recovery|✓|Runtime|No|No|Maybe|**Yes**|✓|Rare|**Yes**|
|Composite|Derived|Correlator|Maybe|Maybe|Maybe|✓|Maybe|Maybe|**Yes**|

This is the first major architectural table I'd keep.

---

# 19. But I want to make one correction to the word "scheduler"

We previously said:

> "We need a scheduler that schedules events if they require LLM action."

I would now modify that.

The scheduler should **not care whether an event requires an LLM**.

That's a downstream concern.

Instead:

```text
Scheduler
    ↓
makes something runnable
```

Then:

```text
Dispatcher
    ↓
determines execution strategy
```

Then:

```text
Execution Policy
    ↓
deterministic / interactive / autonomous
```

Then potentially:

```text
Model Router
    ↓
LLM
```

So:

```text
Scheduler
≠
LLM Scheduler
```

It is a **work scheduling system**.

---

# 20. This gives us a cleaner pipeline

I would now model the Active Layer as:

```text
                   EVENT SOURCES
                        │
                        ▼
                ┌───────────────┐
                │ Event Readers │
                └───────┬───────┘
                        │
                        ▼
                ┌───────────────┐
                │ Event Intake  │
                └───────┬───────┘
                        │
                        ▼
                ┌───────────────┐
                │ Normalization │
                └───────┬───────┘
                        │
                        ▼
                ┌───────────────┐
                │ Event Storage │
                └───────┬───────┘
                        │
                        ▼
                ┌───────────────┐
                │ Event Router  │
                └───────┬───────┘
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
       Direct Runtime         Trigger Engine
          Action                  │
                                  ▼
                                Task
                                  │
                                  ▼
                              Scheduler
                                  │
                                  ▼
                           Priority Manager
                                  │
                                  ▼
                              Dispatcher
                                  │
                                  ▼
                             Execution
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
               Deterministic  Interactive   Autonomous
                    │             │             │
                                  ▼             ▼
                              Small LLM     Strong LLM
```

That's becoming a very coherent architecture.

---

# 21. Event Readers vs Event Intake

This distinction should also be explicit.

### Event Reader

Knows how to communicate with a particular source.

Examples:

```text
KeyboardReader
MicrophoneReader
FileSystemReader
CalendarReader
GmailReader
BluetoothReader
SystemReader
SchedulerReader
```

Its job:

> **Observe a source and emit raw events.**

### Event Intake

Knows how to accept events into the system.

Its job:

```text
validate
normalize
assign ID
timestamp
deduplicate
persist
publish
```

Therefore:

```text
GmailReader
     ↓
raw Gmail event
     ↓
Event Intake
     ↓
canonical event
```

This is an excellent separation.

---

# 22. Event Storage is not the Event Bus

Another distinction I'd make now.

### Event Storage

Answers:

> "What happened?"

### Event Bus / Dispatcher

Answers:

> "Who needs to know that it happened?"

So:

```text
                   Event
                     │
             ┌───────┴───────┐
             ▼               ▼
        Event Store       Event Bus
             │               │
       historical       live routing
```

You want both concepts even if they are implemented by the same technology initially.

---

# 23. Event persistence should have levels

We shouldn't blindly persist every microscopic event forever.

I'd classify events:

### Level 1 — Durable business events

```text
USER_MESSAGE
TASK_CREATED
TASK_COMPLETED
EXECUTION_FAILED
USER_APPROVAL
```

Persist strongly.

### Level 2 — operational events

```text
MODEL_STARTED
TOOL_COMPLETED
CHECKPOINT_CREATED
```

Persist for observability/recovery.

### Level 3 — high-frequency telemetry

```text
LLM_TOKEN_STREAM
MOUSE_MOVED
CPU_SAMPLE
```

Don't necessarily put every occurrence into the permanent event store.

Instead:

```text
metrics/log stream
```

This distinction will save us from building an enormous event database full of noise.

---

# 24. Event priority should also be multi-dimensional

I would **not** store only:

```text
priority = HIGH
```

Eventually we want something more like:

```text
priority:
    urgency
    importance
    user_initiated
    deadline
    interruptibility
    resource_cost
```

For example:

```text
User asks question
urgency = high
user_initiated = true
deadline = none
```

while:

```text
Nightly embedding maintenance
urgency = low
importance = medium
user_initiated = false
```

The scheduler can derive an effective priority.

Something conceptually like:

```text
effective_priority =
    urgency
    + importance
    + deadline_pressure
    + user_interaction_bonus
    - resource_cost_penalty
```

I would **not** finalize the mathematical formula yet. That belongs to the architectural planning phase.

---

# 25. Priority also needs aging

Otherwise you can get starvation.

Suppose:

```text
HIGH priority tasks
```

keep arriving.

Then:

```text
LOW priority task
```

might never execute.

So the scheduler eventually needs:

```text
priority aging
```

Conceptually:

```text
time_waiting ↑
       ↓
effective priority ↑
```

This is standard scheduling reasoning and will be important for autonomous background work.

---

# 26. We also need preemption rules

Not every high-priority event should forcibly kill whatever is running.

There are different levels:

```text
RUN AFTER CURRENT STEP
```

```text
PAUSE EXECUTION
```

```text
CANCEL EXECUTION
```

```text
IMMEDIATE INTERRUPT
```

For example:

### User question

Probably:

```text
finish current safe boundary
→ execute user request
```

### System shutdown

```text
checkpoint
→ stop
```

### Emergency system event

Potentially:

```text
immediate cancellation
```

This means priority and **preemption policy** should be separate concepts.

---

# 27. We also need deduplication

Imagine a webhook gets delivered twice:

```text
EMAIL_RECEIVED
event_id = abc
```

and again:

```text
EMAIL_RECEIVED
event_id = abc
```

We don't want:

```text
Task created
Task created
Execution
Execution
```

So Event Intake needs:

```text
event identity
deduplication
idempotency
```

External event systems commonly require this kind of defensive design because delivery and processing can be retried.

This will also matter enormously for our scheduler.

---

# 28. Event ordering is another issue

Consider:

```text
TASK_CREATED
TASK_CANCELLED
```

If they arrive out of order:

```text
TASK_CANCELLED
TASK_CREATED
```

we could resurrect a cancelled task.

Therefore certain event streams need:

```text
sequence
version
timestamp
causal relationship
```

Not every event requires global ordering.

That's actually important:

> **We should not try to impose one global event order across the entire system.**

Different domains can have their own ordering guarantees.

---

# 29. Event causality

I'd also eventually want:

```text
caused_by
```

For example:

```text
USER_MESSAGE
   │
   └── caused TASK_CREATED
              │
              └── caused EXECUTION_CREATED
                         │
                         └── caused TOOL_REQUESTED
```

This gives us a causal chain:

```text
User
 ↓
Event
 ↓
Task
 ↓
Execution
 ↓
Tool
 ↓
Result
 ↓
Event
```

That will be invaluable for debugging an autonomous system.

---

# 30. And now we can see the Active Layer as a feedback system

This is probably the biggest result from this research.

It isn't:

```text
INPUT → LLM → OUTPUT
```

It's:

```text
                     ┌──────────────────────┐
                     │                      │
                     ▼                      │
                  EVENTS                    │
                     │                      │
                     ▼                      │
                   TASKS                    │
                     │                      │
                     ▼                      │
                EXECUTIONS                  │
                     │                      │
                     ▼                      │
                ACTIONS / LLM               │
                     │                      │
                     ▼                      │
                STATE CHANGES ──────────────┘
```

The system continuously converts:

```text
state changes → events → work → actions → new state changes
```

That's much closer to a true autonomous runtime.

---

# 31. The most important boundaries I'd preserve

At this point, I would freeze these conceptual boundaries:

### Event

**Fact**

```text
Something happened.
```

### Trigger

**Rule**

```text
When this event occurs, consider activating X.
```

### Task

**Responsibility**

```text
Something needs to be accomplished.
```

### Schedule

**Temporal constraint**

```text
When may/should the task become runnable?
```

### Priority

**Resource ordering**

```text
Which runnable work deserves resources first?
```

### Execution

**Runtime attempt**

```text
Actually perform the task.
```

### Agent

**Reasoning capability**

```text
Determine what to do next.
```

### LLM

**Reasoning engine**

```text
Generate a decision/action based on context.
```

### Tool

**Capability**

```text
Perform an external/system operation.
```

That separation is extremely strong.

---

# 32. One final thing: "event requires LLM" is not really an event property

I'd change the terminology slightly.

Instead of:

```text
Event:
requires_llm = true
```

I'd use:

```text
Event
 ↓
Trigger
 ↓
Task
 ↓
Execution Policy
 ↓
reasoning requirement
 ↓
Model selection
```

Because the same event could lead to different behavior.

For example:

```text
FILE_CREATED
```

could mean:

```text
Task A:
backup file
→ deterministic
```

or:

```text
Task B:
summarize file
→ LLM
```

or:

```text
Task C:
classify document
→ small LLM
```

or:

```text
Task D:
research implications
→ strong LLM
```

So **the event itself doesn't dictate the intelligence level**.

The resulting work does.

---

# 33. Where we've reached

I think our conceptual Active Layer is now:

```text
                         SOURCES
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
             ┌─────────────┴─────────────┐
             │                           │
       Direct Runtime               Trigger Engine
             │                           │
             │                           ▼
             │                         TASK
             │                           │
             │                           ▼
             │                       SCHEDULER
             │                           │
             │                           ▼
             │                      PRIORITY QUEUE
             │                           │
             └──────────────┬────────────┘
                            ▼
                       DISPATCHER
                            │
                            ▼
                        EXECUTION
                            │
                 ┌──────────┼──────────┐
                 ▼          ▼          ▼
             Deterministic Interactive Autonomous
                            │          │
                            ▼          ▼
                         Small LLM   Strong LLM
```

And around all of it:

```text
             ┌─────────────────────────────┐
             │ CONDITION / CORRELATION     │
             │ RECOVERY / PERSISTENCE      │
             │ PRIORITY / PREEMPTION       │
             │ OBSERVABILITY               │
             └─────────────────────────────┘
```

---

## What I would **not** design yet

I agree with your plan: **do not jump into code or LangGraph yet.**

We now have enough understanding to do something much more valuable first:

### Next: summarize and freeze our findings

I'd produce a formal **Phase 0 / Research Findings document** containing:

1. **What an agent runtime actually is**
    
2. **Event → Task → Execution**
    
3. **The three execution modes**
    
4. **LLM lifecycle**
    
5. **Complete event taxonomy**
    
6. **Event properties**
    
7. **Event readers**
    
8. **Event intake**
    
9. **Event persistence**
    
10. **Trigger system**
    
11. **Task model**
    
12. **Scheduler**
    
13. **Priority model**
    
14. **Queueing**
    
15. **Dispatcher**
    
16. **Execution lifecycle**
    
17. **Waiting / wake-up**
    
18. **Interrupt / preemption**
    
19. **Retries / recovery**
    
20. **LLM/model routing**
    
21. **Human interaction**
    
22. **Condition/composite events**
    
23. **Failure and delivery semantics**
    
24. **What should be deterministic vs LLM-driven**
    
25. **Open architectural questions**
    

Then, **only after that**, we move to **Phase 1 architectural planning** and turn those findings into actual components/interfaces/data flows.

That Phase 1 can then specifically cover the **input side and Active Layer** you described:

```text
Event Readers
→ Event Intake
→ Normalization
→ Classification
→ Event Store
→ Event Router
→ Trigger Engine
→ Tasks
→ Scheduler
→ Priority Manager
→ Queue
→ Dispatcher
→ Execution Manager
```

with persistence, recovery, deduplication, ordering, and LLM invocation boundaries defined explicitly.

I think that is the right order. We have now done enough conceptual research that we **should not start coding until we write that consolidated specification**.

Yes. I think we should **finish the scheduler as its own design problem** before consolidation. It is one of the most important pieces because it sits between "something should happen" and "something is actually executed."

I also want to correct one earlier simplification: the scheduler should not be thought of as merely a component that handles `at 8:00`. A serious scheduler for an agent runtime needs to coordinate **time, eligibility, priority, resources, dependencies, concurrency, interruption, retries, and recovery**.

Current workflow/task systems reinforce this separation. Celery, for example, separates routing, queues, ETA/countdown, priority, expiration and worker execution; it also warns that worker prefetching can undermine apparent priority ordering. ([Celery Documentation](https://docs.celeryq.dev/en/main/userguide/routing.html?utm_source=chatgpt.com "Routing Tasks — Celery 5.6.2 documentation")) LangGraph similarly treats persistence, interruption and resumption as runtime concerns rather than simply "calling the model." ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/interrupts?utm_source=chatgpt.com "Interrupts - Docs by LangChain"))

Let's design ours from first principles.

---

# 1. What exactly is the Scheduler?

Our definition should be:

> **The Scheduler determines when eligible work becomes runnable and which runnable work should receive execution resources.**

That gives us three different concepts:

```text
Task
  ↓
Should this task run?
  ↓
Eligibility
  ↓
When can it run?
  ↓
Scheduling
  ↓
Which runnable work gets resources?
  ↓
Dispatch
```

This means:

**Scheduler ≠ Executor**

and

**Scheduler ≠ Task Manager**

and

**Scheduler ≠ Queue**

Those are related but different responsibilities.

---

# 2. The complete scheduler pipeline

I'd model it like this:

```text
                         TASK
                           │
                           ▼
                  ┌─────────────────┐
                  │ Eligibility     │
                  │ Evaluation      │
                  └────────┬────────┘
                           │
                ┌──────────┼───────────┐
                │          │           │
             blocked     waiting     eligible
                │          │           │
                │          │           ▼
                │          │      RUNNABLE
                │          │           │
                │          │           ▼
                │          │      PRIORITY
                │          │           │
                │          │           ▼
                │          │        QUEUE
                │          │           │
                │          │           ▼
                │          │      DISPATCHER
                │          │           │
                │          │           ▼
                │          │       EXECUTION
                │          │
                └──────────┴───────────────
```

The scheduler is therefore fundamentally managing **state transitions**.

---

# 3. A Task should not simply be "scheduled"

A task can exist in several states before execution.

I'd propose:

```text
CREATED
  ↓
PENDING
  ↓
WAITING
  ↓
ELIGIBLE
  ↓
QUEUED
  ↓
DISPATCHED
  ↓
RUNNING
```

And from various points:

```text
PAUSED
BLOCKED
CANCELLED
EXPIRED
FAILED
COMPLETED
```

But there's an important distinction:

### `WAITING`

The task cannot run **yet**.

Example:

```text
"Remind me at 8 PM."
```

### `BLOCKED`

The task cannot run because a prerequisite isn't satisfied.

Example:

```text
Task B requires Task A to complete.
```

### `ELIGIBLE`

All conditions necessary for execution are satisfied.

```text
time reached
dependencies satisfied
task enabled
resource policy permits execution
```

### `QUEUED`

The task is eligible but is waiting for an execution resource.

That's a critical distinction.

---

# 4. The scheduler should not wake up every second and inspect everything

A naïve implementation might be:

```text
while True:
    tasks = get_all_tasks()

    for task in tasks:
        if task.should_run():
            queue(task)

    sleep(1)
```

I would explicitly avoid building the architecture around that.

It creates:

- unnecessary polling
    
- poor scalability
    
- timing inaccuracies
    
- duplicate scheduling risks
    
- complicated recovery
    
- unnecessary database queries
    

Instead, the scheduler should maintain **future wake-up points**.

For example:

```text
Task A → 08:00
Task B → 08:30
Task C → 14:00
Task D → tomorrow
```

The scheduler knows the next relevant time is:

```text
08:00
```

and sleeps until then, subject to external events and system constraints.

Celery's ETA scheduler similarly uses a timer mechanism rather than requiring application-level constant scanning, while also exposing a timer precision setting. ([Celery Documentation](https://docs.celeryq.dev/en/main/userguide/configuration.html?utm_source=chatgpt.com "Configuration and defaults — Celery 5.6.2 documentation"))

---

# 5. But there are two fundamentally different scheduling mechanisms

This is important.

## Temporal scheduling

```text
AT 08:00
IN 20 MINUTES
EVERY DAY
EVERY MONDAY
```

versus:

## Event-driven scheduling

```text
WHEN EMAIL_RECEIVED
WHEN USER_APPROVES
WHEN FILE_CREATED
WHEN TASK_COMPLETES
WHEN NETWORK_AVAILABLE
```

So:

```text
             SCHEDULER
                 │
        ┌────────┴────────┐
        ▼                 ▼
   TIME ENGINE       EVENT ENGINE
```

The **time engine** handles temporal eligibility.

The **event engine** responds to events that make tasks eligible.

---

# 6. Then there's condition scheduling

This is a third mechanism.

Example:

> "When the CPU stays below 20%, run the model."

Or:

> "When I haven't used the computer for 30 minutes."

Or:

> "When my calendar becomes free."

These aren't simple events or times.

They're:

```text
STATE
 ↓
CONDITION EVALUATION
 ↓
CONDITION BECOMES TRUE
 ↓
TASK ELIGIBLE
```

So I'd have:

```text
                   ELIGIBILITY
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       Temporal      Event       Condition
```

That's much cleaner than forcing everything into cron-like scheduling.

---

# 7. Recurring tasks

Recurring tasks deserve special treatment.

Suppose:

```text
Every Monday at 08:00
```

We should **not** think:

```text
create task
execute
create another task
execute
...
```

Instead:

```text
Task Definition
     │
     ├── recurrence rule
     │
     └── next occurrence
```

Example:

```text
Task:
Morning Brief

Schedule:
FREQ=DAILY
TIME=08:00

next_run:
2026-09-16 08:00
```

After execution:

```text
completed occurrence
       ↓
calculate next occurrence
       ↓
2026-09-17 08:00
```

This gives us one persistent Task with many execution instances.

That's an important distinction:

> **Task ≠ Execution**

---

# 8. This means recurring scheduling needs an Occurrence concept

I'd actually introduce:

```text
Task
  │
  ├── Schedule
  │
  └── Occurrence
          │
          ▼
       Execution
```

For example:

```text
Task: Daily News Summary

Occurrence #182
2026-09-15 08:00
        ↓
Execution #981
```

Next day:

```text
Occurrence #183
2026-09-16 08:00
        ↓
Execution #982
```

This gives us clean history.

---

# 9. What if a recurring execution is still running?

Suppose:

```text
Daily Research
08:00 → starts
```

and it's still running at:

```text
08:05
```

while the next occurrence is due.

We need a recurrence policy.

Possible:

```text
SKIP
QUEUE
PARALLEL
DELAY
```

For example:

### Skip

```text
08:00 running
09:00 occurrence arrives
→ skip
```

### Queue

```text
08:00 running
09:00 occurrence arrives
→ queue next execution
```

### Parallel

```text
08:00 running
09:00 occurrence arrives
→ start another
```

### Delay

```text
08:00 running
09:00 arrives
→ run after current completes
```

This should be a **task scheduling policy**, not hardcoded scheduler behavior.

---

# 10. Dependencies

Now consider:

```text
Task A
   ↓
Task B
   ↓
Task C
```

Task B should not simply be scheduled at a time.

It has:

```text
dependency:
A must complete
```

Therefore:

```text
Task B
state = BLOCKED
```

Then:

```text
TASK_A_COMPLETED
        ↓
dependency evaluator
        ↓
Task B becomes eligible
```

This means the scheduler needs to understand **dependency satisfaction**, but it doesn't need to execute the dependency itself.

---

# 11. Dependency types

I'd eventually support several forms.

### Task dependency

```text
B waits for A
```

### Event dependency

```text
B waits for EVENT_X
```

### Time dependency

```text
B waits until 18:00
```

### Condition dependency

```text
B waits until condition X
```

### Human dependency

```text
B waits for user approval
```

### Composite dependency

```text
A completed
AND
18:00 reached
AND
network available
```

This naturally leads to an **eligibility expression**.

---

# 12. Eligibility should be explicit

A task might have:

```text
eligible_when:

time >= 18:00
AND
dependency_A == completed
AND
network == available
AND
task.enabled == true
```

The scheduler evaluates this.

Conceptually:

```text
                TASK
                  │
                  ▼
          Eligibility Engine
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
      Time    Dependencies Conditions
       │          │          │
       └──────────┼──────────┘
                  ▼
              ELIGIBLE?
```

This is better than scattering scheduling logic throughout the codebase.

---

# 13. Then priority starts

Once a task becomes eligible:

```text
ELIGIBLE
   ↓
RUNNABLE
```

Now the scheduler asks:

> Which runnable work should execute first?

This is where priority belongs.

---

# 14. Priority should NOT be a single number initially

I'd model priority as several dimensions.

```text
PriorityContext

urgency
importance
deadline
user_initiated
age
interruptibility
resource_cost
```

Then derive:

```text
effective_priority
```

For example:

```text
User request:
urgency = high
user_initiated = true

Nightly indexing:
urgency = low
user_initiated = false
```

The scheduler can rank them.

---

# 15. Deadline pressure

This deserves its own concept.

Suppose:

```text
Task A
priority = medium
deadline = tomorrow
```

and:

```text
Task B
priority = medium
deadline = 5 minutes
```

B should rise automatically.

Therefore:

```text
deadline proximity
```

should affect effective priority.

But don't turn this into a giant opaque formula yet.

I'd make the architecture support:

```text
PriorityPolicy
```

and keep the initial policy simple.

---

# 16. Priority aging

We discussed this earlier, and I think it should be part of the design.

Suppose:

```text
Low priority task
waiting = 2 hours
```

Its effective priority should eventually increase.

Otherwise autonomous maintenance could starve forever.

Conceptually:

```text
base priority
      +
waiting-time bonus
      +
deadline pressure
      +
user urgency
      =
effective priority
```

Again, exact scoring comes later.

---

# 17. Priority is not the same as queue

This is extremely important.

You can have:

```text
Queue:
    task A
    task B
    task C
```

and:

```text
Priority:
    B > A > C
```

The queue is the **waiting collection**.

Priority is the **ordering policy**.

A priority queue is an implementation possibility, but the concepts should remain separate.

Celery demonstrates why this matters: broker-level priority isn't always a strict execution-order guarantee because workers may prefetch tasks. ([Celery Documentation](https://docs.celeryq.dev/en/main/userguide/routing.html?utm_source=chatgpt.com "Routing Tasks — Celery 5.6.2 documentation"))

For our local single-machine system, we can control this more tightly.

---

# 18. Resource-aware scheduling

This is where our architecture becomes particularly relevant to local AI.

Suppose:

```text
Runnable tasks:

A → deterministic
B → small LLM
C → strong LLM
D → filesystem operation
E → network operation
```

We don't want one giant queue.

We could have:

```text
                Dispatcher
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
  Deterministic   LLM Pool    External I/O
     Queue           │             Queue
                     │
              ┌──────┴──────┐
              ▼             ▼
          Small LLM     Strong LLM
```

The scheduler chooses work, but the dispatcher checks resource availability.

---

# 19. Resource constraints

A task can specify:

```text
requires:
    cpu
    gpu
    llm
    network
    filesystem
```

And potentially:

```text
llm_model = strong
gpu_memory = 4GB
```

or:

```text
network = required
```

The scheduler doesn't necessarily know hardware details. It can consult a **Resource Manager**.

```text
Scheduler
    ↓
Dispatcher
    ↓
Resource Manager
    ↓
Can this execute?
```

---

# 20. This prevents an important failure

Imagine:

```text
Strong LLM execution running
```

and another task requests:

```text
Strong LLM
```

We shouldn't:

```text
start another model invocation blindly
```

Instead:

```text
RESOURCE_UNAVAILABLE
       ↓
remain queued
       ↓
resource becomes available
       ↓
dispatch
```

That makes the system naturally backpressure-aware.

---

# 21. Concurrency limits

Each resource can have limits.

Example:

```text
CPU tasks:
max concurrency = 4

Network tasks:
max concurrency = 8

Small LLM:
max concurrency = 1

Strong LLM:
max concurrency = 1
```

This is especially realistic for a local machine.

The scheduler therefore operates under:

```text
Priority
+
Eligibility
+
Dependencies
+
Resource availability
+
Concurrency limits
```

---

# 22. User interaction should get special treatment

This connects to the architecture we discussed earlier.

Suppose:

```text
Autonomous research execution
```

is running.

Then:

```text
USER_MESSAGE
```

arrives.

We don't want:

```text
user message → ordinary queue
```

and potentially wait behind ten autonomous tasks.

Instead:

```text
USER EVENT
    ↓
Interactive lane
    ↓
priority override
    ↓
dispatcher
```

So I'd explicitly define:

```text
INTERACTIVE
AUTONOMOUS
DETERMINISTIC
```

as **execution classes**.

Not necessarily three separate schedulers.

---

# 23. I would use one scheduler with multiple lanes

Something like:

```text
                         SCHEDULER
                             │
          ┌──────────────────┼──────────────────┐
          ▼                  ▼                  ▼
    Interactive          Autonomous        Deterministic
       Lane                 Lane               Lane
          │                  │                  │
          └──────────────────┼──────────────────┘
                             ▼
                       Global Policy
                             │
                             ▼
                         Dispatcher
```

This is better than three completely independent schedulers because we still need global resource arbitration.

---

# 24. But interactive work should not always preempt everything

Consider:

```text
System shutdown
```

versus:

```text
User asks:
"What's 2+2?"
```

System shutdown should win.

So priority is still global.

Something like:

```text
SYSTEM_CRITICAL
      ↓
USER_INTERACTIVE
      ↓
TIME_CRITICAL
      ↓
AUTONOMOUS_HIGH
      ↓
AUTONOMOUS_NORMAL
      ↓
BACKGROUND
```

These are **classes**, not necessarily the final numeric priorities.

---

# 25. Preemption needs its own policy

I strongly recommend we separate:

```text
priority
```

from:

```text
preemption policy
```

Because:

```text
HIGH priority
```

doesn't necessarily mean:

```text
kill whatever is running
```

Possible policies:

```text
RUN_NEXT
PREEMPT_AT_SAFE_POINT
PAUSE
CANCEL
FORCE_CANCEL
```

For an LLM execution:

```text
User message arrives
        ↓
current model generation
        ↓
cancel generation
        ↓
save execution state
        ↓
interactive request
```

But for a filesystem operation:

```text
file write
```

we may need to finish an atomic operation before switching.

---

# 26. Therefore Execution needs scheduling boundaries

This is where the Scheduler and Execution Manager meet.

An execution should expose safe boundaries:

```text
START
STEP_COMPLETE
TOOL_COMPLETE
LLM_COMPLETE
CHECKPOINT
WAIT
```

At those points:

```text
Scheduler can reconsider priorities.
```

LangGraph's durable execution model is relevant here: checkpoints occur at execution boundaries, and smaller steps provide finer-grained recovery/resumption points. ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/persistence?utm_source=chatgpt.com "Persistence - Docs by LangChain"))

---

# 27. Waiting is not failure

This is another thing we should formalize.

An execution can intentionally become:

```text
WAITING
```

because it needs:

```text
time
event
human input
resource
dependency
external response
```

For example:

```text
Execution
   ↓
WAITING_FOR_USER
```

or:

```text
Execution
   ↓
WAITING_FOR_TIME
```

or:

```text
Execution
   ↓
WAITING_FOR_RESOURCE
```

The scheduler is responsible for waking it when the condition is satisfied.

---

# 28. This means the scheduler is also a wake-up manager

That's a major responsibility.

```text
WAITING EXECUTION
        │
        ├── time → Timer
        │
        ├── event → Event subscription
        │
        ├── human → Input event
        │
        ├── resource → Resource availability
        │
        └── dependency → Task event
```

All of those can cause:

```text
WAKE
 ↓
ELIGIBILITY CHECK
 ↓
RUNNABLE
```

So the scheduler isn't only:

> "What runs next?"

It's also:

> **"What should become runnable next?"**

---

# 29. Expiration

Every scheduled task may need:

```text
expires_at
```

Example:

> "Remind me to join the meeting at 10:00."

If the task is still queued at:

```text
11:00
```

it may no longer be useful.

So:

```text
scheduled_at
expires_at
```

should be distinct.

Celery exposes both ETA and expiration semantics, which is a good indication that these should be separate scheduling concepts. ([Celery Documentation](https://docs.celeryq.dev/en/main/reference/celery.app.task.html?utm_source=chatgpt.com "celery.app.task — Celery 5.6.2 documentation"))

---

# 30. Misfires

This is one of the biggest scheduler concerns.

Suppose:

```text
Task scheduled: 08:00
```

but:

```text
Machine was powered off
07:00 → 10:00
```

At 10:00:

> What happens?

Possible policies:

```text
RUN_IMMEDIATELY
SKIP
RUN_IF_WITHIN_WINDOW
RESCHEDULE
```

Example:

```text
Daily news at 08:00
machine wakes at 10:00

→ probably skip
```

But:

```text
Submit report at 08:00
machine wakes at 10:00

→ probably run immediately
```

This must be **task-specific policy**.

---

# 31. Scheduler persistence

This is non-negotiable.

If the process crashes:

```text
Scheduler memory:
gone
```

If schedules only lived there:

```text
tasks disappear
```

So persistent state must contain at least:

```text
Task
Schedule
next_run
status
priority
dependencies
retry state
execution references
```

The scheduler can rebuild its in-memory structures after restart.

---

# 32. But don't persist the queue as the source of truth

I'd make:

```text
Persistent Task/Execution State
           │
           ▼
       Scheduler
           │
           ▼
    In-memory runnable queue
```

The queue is a **derived runtime structure**.

This gives us recovery.

If the process crashes:

```text
restart
 ↓
load persistent tasks/executions
 ↓
reconstruct eligible work
 ↓
rebuild queues
```

That's much safer.

---

# 33. Scheduler crash recovery

Suppose:

```text
Task A
status = RUNNING
```

and machine crashes.

On restart:

```text
Task A
status = RUNNING
```

is suspicious.

The scheduler shouldn't simply assume it finished.

Recovery needs to determine:

```text
Was execution completed?
Was it checkpointed?
Was it interrupted?
Can it resume?
Should it retry?
```

That belongs to the Execution/Recovery layer, but the Scheduler must cooperate.

---

# 34. Exactly-once is dangerous to assume

We should design around:

```text
at-least-once delivery
```

and:

```text
idempotent execution
```

rather than assuming:

```text
exactly once
```

For example:

```text
scheduler says execute task
 ↓
worker starts
 ↓
worker crashes before acknowledgement
```

Did it execute?

Maybe.

Therefore retrying could produce duplicates.

LangGraph's current durable-execution guidance explicitly emphasizes idempotency around side effects because execution may be replayed/re-run after failures. ([Docs by LangChain](https://docs.langchain.com/oss/python/langgraph/use-functional-api?utm_source=chatgpt.com "Use the functional API - Docs by LangChain"))

Our system should therefore distinguish:

```text
execution identity
attempt identity
idempotency key
```

---

# 35. Retry policy

The scheduler shouldn't blindly retry everything.

Tasks need a retry policy:

```text
max_attempts
backoff
retryable_errors
non_retryable_errors
jitter
```

Example:

```text
network timeout
→ retry

invalid user input
→ don't retry

LLM malformed output
→ perhaps retry/reason again

permission denied
→ probably wait for user/system change
```

And:

```text
retry
```

should create another **attempt**, not another logical Task.

---

# 36. Backoff

For repeated failures:

```text
attempt 1 → immediate
attempt 2 → 5 sec
attempt 3 → 30 sec
attempt 4 → 5 min
```

This prevents:

```text
failure
→ retry
→ failure
→ retry
→ failure
→ ...
```

from consuming the entire runtime.

---

# 37. Rate limiting

Scheduler should eventually support:

```text
no more than X executions / minute
```

or:

```text
no more than X calls to service Y
```

This is especially important for external APIs.

Celery treats rate limits as distinct from priority and notes that global limits may require queue-level coordination rather than simply worker-local limits. ([Celery Documentation](https://docs.celeryq.dev/en/latest/userguide/tasks.html?highlight=request&utm_source=chatgpt.com "Tasks — Celery 5.6.2 documentation"))

For us:

```text
Task policy
    ↓
RateLimitPolicy
    ↓
Eligibility
```

---

# 38. Fairness

Suppose we have:

```text
Autonomous Task A
Autonomous Task B
Autonomous Task C
```

A should not consume every available execution slot.

We could eventually support:

```text
weighted fairness
```

or:

```text
round-robin
```

within priority bands.

For Phase 1, I would keep this simple.

But the architecture must not make fairness impossible later.

---

# 39. Scheduler should support cancellation

Cancellation can come from:

```text
user
task expiration
system shutdown
dependency invalidation
policy
resource pressure
execution failure
```

Then:

```text
TASK_CANCELLED
```

must be durable.

And importantly:

> Cancellation is a state transition, not merely removing something from a queue.

Because it may already be:

```text
queued
running
waiting
paused
```

---

# 40. Scheduler and event system interaction

Now we can connect everything we've discussed.

Example:

```text
USER:
"Remind me at 8 PM to check my email."
```

### Step 1

Human Event:

```text
USER_MESSAGE
```

### Step 2

Interactive agent interprets it.

### Step 3

Creates:

```text
TASK_CREATED
```

with:

```text
schedule = 20:00
```

### Step 4

Scheduler stores:

```text
next_run = 20:00
```

### Step 5

At 20:00:

```text
SCHEDULE_DUE
```

### Step 6

Task becomes:

```text
ELIGIBLE
```

### Step 7

Scheduler evaluates:

```text
priority
resource
concurrency
```

### Step 8

Creates:

```text
EXECUTION
```

### Step 9

Dispatcher decides:

```text
interactive? no
autonomous? yes
```

### Step 10

Model router decides:

```text
strong LLM
```

### Step 11

Execution runs.

### Step 12

Completion:

```text
EXECUTION_COMPLETED
```

### Step 13

Recurring? No.

Task complete.

That's the full lifecycle.

---

# 41. Event-triggered scheduling

Now:

> "Whenever I receive an important email, summarize it."

Task:

```text
trigger:
EMAIL_RECEIVED
condition:
importance >= HIGH
```

No temporal schedule.

Instead:

```text
EMAIL_RECEIVED
      ↓
Event Router
      ↓
Trigger Engine
      ↓
Condition
      ↓
Task eligible
      ↓
Scheduler
      ↓
Priority
      ↓
Execution
```

This is why I don't want us to call the component merely a "cron scheduler."

It's really an **execution scheduling subsystem**.

---

# 42. Human interaction has a different path

User says:

> "What is 2 + 2?"

We don't need:

```text
Task
Schedule
Queue
```

We can do:

```text
USER_MESSAGE
      ↓
Interactive Lane
      ↓
Execution
      ↓
Small LLM
      ↓
Response
```

So **not all work passes through the scheduling machinery**.

But the scheduler should still be capable of coordinating it when contention exists.

That's an important distinction.

---

# 43. I would therefore define three paths

### Immediate path

```text
Event
 ↓
Execution
```

For immediate deterministic/interactive work.

### Scheduled path

```text
Event
 ↓
Task
 ↓
Schedule
 ↓
Scheduler
 ↓
Execution
```

### Triggered autonomous path

```text
Event
 ↓
Trigger
 ↓
Task
 ↓
Eligibility
 ↓
Scheduler
 ↓
Execution
```

That gives us flexibility without making everything a Task.

---

# 44. Scheduler architecture

At the architectural level, I think the scheduler should contain these conceptual components:

```text
┌──────────────────────────────────────────┐
│               SCHEDULER                  │
│                                          │
│  ┌──────────────┐   ┌─────────────────┐ │
│  │ Time Engine  │   │ Event Wake      │ │
│  └──────┬───────┘   │ Manager         │ │
│         │            └───────┬─────────┘ │
│         │                    │           │
│         └──────────┬─────────┘           │
│                    ▼                     │
│           ┌────────────────┐             │
│           │ Eligibility    │             │
│           │ Engine         │             │
│           └───────┬────────┘             │
│                   ▼                      │
│           ┌────────────────┐             │
│           │ Runnable Set   │             │
│           └───────┬────────┘             │
│                   ▼                      │
│           ┌────────────────┐             │
│           │ Priority       │             │
│           │ Manager       │             │
│           └───────┬────────┘             │
│                   ▼                      │
│           ┌────────────────┐             │
│           │ Queue Manager  │             │
│           └───────┬────────┘             │
└───────────────────┼──────────────────────┘
                    ▼
               DISPATCHER
```

Then outside it:

```text
Persistence
Recovery
Resource Manager
Execution Manager
Event Bus
```

---

# 45. Scheduler inputs

The scheduler shouldn't only receive Tasks.

It should receive signals from:

```text
Task Manager
Event Router
Timer Engine
Condition Engine
Execution Manager
Resource Manager
Recovery Manager
Human Interaction
System Lifecycle
```

For example:

```text
TASK_CREATED
TASK_UPDATED

TIMER_DUE

EVENT_OCCURRED

DEPENDENCY_COMPLETED

RESOURCE_AVAILABLE

EXECUTION_COMPLETED

EXECUTION_FAILED

SYSTEM_RESUMED
```

These are scheduler stimuli.

---

# 46. Scheduler outputs

It should produce things like:

```text
TASK_ELIGIBLE
TASK_QUEUED
EXECUTION_DISPATCHED
TASK_DEFERRED
TASK_EXPIRED
TASK_SKIPPED
EXECUTION_PREEMPT_REQUESTED
```

Those are events themselves.

So:

```text
Scheduler
   ↓
Scheduler Event
   ↓
Event Bus
```

This keeps the architecture decoupled.

---

# 47. One subtle but important point: the scheduler should be deterministic

I would strongly recommend:

> **The scheduler itself should not use the LLM.**

It should not ask:

> "Which task seems more important?"

The LLM can help **create/configure** a Task:

> "Schedule a reminder tomorrow."

But once the Task exists:

```text
scheduler = deterministic
```

Priority rules:

```text
deterministic
```

Time:

```text
deterministic
```

Dependencies:

```text
deterministic
```

Resource constraints:

```text
deterministic
```

The LLM belongs in:

```text
Task interpretation
Planning
Execution
Reasoning
```

not in the scheduler's critical path.

That will make the runtime dramatically more reliable.

---

# 48. The scheduler should also not depend on the LLM being loaded

This matters for local AI.

Imagine:

```text
LLM unloaded
```

The scheduler should still be able to:

```text
wake
schedule
prioritize
queue
retry
cancel
recover
```

Then when an execution requiring an LLM is dispatched:

```text
Model unavailable
       ↓
Resource Manager
       ↓
load model / wait
```

The scheduler remains alive.

This is exactly the kind of separation you want in a local autonomous system.

---

# 49. Scheduler lifecycle

I'd give the scheduler its own lifecycle:

```text
INITIALIZING
     ↓
LOADING_STATE
     ↓
REBUILDING_SCHEDULE
     ↓
READY
     ↓
RUNNING
     ↓
DRAINING
     ↓
STOPPED
```

On startup:

```text
persistent state
      ↓
recover
      ↓
rebuild timers
      ↓
rebuild runnable queues
      ↓
scheduler ready
```

On shutdown:

```text
stop accepting new scheduling
      ↓
finish/checkpoint safe work
      ↓
persist scheduler state
      ↓
stop
```

---

# 50. What happens if the scheduler itself crashes?

This is why I prefer the persistent-state model.

After restart:

```text
Persistent Task Store
        ↓
Scheduler Recovery
        ↓
reconstruct:
    timers
    waiting tasks
    runnable tasks
    dependencies
    retry timers
```

We don't need to persist every internal queue mutation if the durable task state is authoritative.

---

# 51. The scheduler should have a "wake-up reason"

This will be useful for debugging.

Every scheduling transition could have:

```text
wake_reason
```

Examples:

```text
TIME_REACHED
EVENT_RECEIVED
DEPENDENCY_COMPLETED
RESOURCE_AVAILABLE
USER_APPROVED
RETRY_BACKOFF_EXPIRED
SYSTEM_RECOVERED
```

Then if something goes wrong, we can answer:

> Why did this task execute?

instead of debugging a mysterious queue.

---

# 52. We also need scheduling provenance

For every execution:

```text
execution_id
task_id
trigger_event_id
schedule_occurrence_id
priority_decision
dispatch_reason
```

Then we can reconstruct:

```text
Why did this execute?
```

Example:

```text
Execution #421

Task:
Daily Research

Triggered by:
Occurrence #81

Schedule:
08:00

Priority:
HIGH

Why HIGH:
deadline proximity

Dispatched:
08:03

Delay:
3 minutes

Reason:
Strong LLM resource occupied
```

That level of observability will become incredibly useful.

---

# 53. What I think the Scheduler should NOT do

This is equally important.

The scheduler should **not**:

- interpret natural language
    
- decide what the user meant
    
- reason about arbitrary problems
    
- build prompts
    
- select memories
    
- perform tools
    
- execute LLM calls
    
- maintain conversation history
    
- perform business logic
    
- directly manipulate external services
    

Instead:

```text
Scheduler
→ when/which/eligibility/priority
```

while:

```text
Execution
→ how the work is actually performed
```

and:

```text
Agent
→ reasoning about what should happen
```

---

# 54. The resulting separation

I think we now have a very clean division:

```text
                 EVENT SYSTEM
                      │
                      ▼
                 TASK SYSTEM
                      │
                      ▼
              ┌───────────────┐
              │   SCHEDULER   │
              │               │
              │ when?         │
              │ eligible?     │
              │ priority?     │
              │ queue?        │
              └───────┬───────┘
                      │
                      ▼
                 DISPATCHER
                      │
                      ▼
                 EXECUTION
                      │
             ┌────────┴────────┐
             ▼                 ▼
       Deterministic       Agent Runtime
                               │
                        ┌──────┴──────┐
                        ▼             ▼
                    Small LLM      Strong LLM
```

This is, in my view, a much stronger architecture than putting "scheduler" inside the agent.

---

# 55. The scheduler's core state machine

I'd ultimately expect something close to:

```text
                    CREATED
                       │
                       ▼
                    PENDING
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
       WAITING       BLOCKED      READY
          │            │            │
          │            │            ▼
          │            │         QUEUED
          │            │            │
          │            │            ▼
          │            │       DISPATCHED
          │            │            │
          │            │            ▼
          │            │         RUNNING
          │            │          /   \
          │            │         /     \
          │            │      SUCCESS  FAILURE
          │            │        │         │
          │            │        ▼         ▼
          │            │    COMPLETED   RETRY
          │            │                  │
          └────────────┴──────────────────┘
```

And side exits:

```text
CANCELLED
EXPIRED
SKIPPED
```

---

# 56. The most important distinction: Task State vs Execution State

I want this explicitly preserved.

A Task can be:

```text
ACTIVE
```

while its current Execution is:

```text
WAITING
```

Example:

> "Every morning summarize my emails."

The Task remains active.

Execution #15:

```text
COMPLETED
```

Execution #16:

```text
WAITING
```

etc.

So:

```text
Task
 ├── schedule
 ├── trigger
 ├── policy
 └── executions[]
```

This is fundamental to recurring/autonomous behavior.

---

# 57. My proposed scheduler contract

At the conceptual API level:

```text
submit(task)
cancel(task)
pause(task)
resume(task)

notify(event)
notify_resource_change(resource)

get_next_wakeup()
evaluate(task)

queue(task)
dequeue(task)

dispatch(task)

recover()
shutdown()
```

But I would **not implement this API yet**.

We're still in research/design.

---

# 58. What Phase 1 will eventually need

When we finally move to architecture, I expect the scheduler portion to break into something roughly like:

```text
Scheduler
│
├── Schedule Registry
│
├── Timer Manager
│
├── Wake Manager
│
├── Eligibility Engine
│
├── Dependency Manager
│
├── Priority Manager
│
├── Runnable Queue
│
├── Resource-Aware Dispatcher
│
├── Retry Manager
│
├── Expiration Manager
│
├── Concurrency Manager
│
├── Preemption Manager
│
└── Recovery Manager
```

**But:** these are conceptual responsibilities, not necessarily 12 Python classes.

We should resist overengineering the first implementation.

---

# 59. What I would implement in Phase 1

When we eventually architect Phase 1, I would start with only the mechanisms we actually need:

### Core

```text
Task Registry
Schedule Registry
Timer Manager
Eligibility Engine
Priority Queue
Dispatcher
Execution Manager
```

### Reliability

```text
Persistence
Recovery
Retry
Expiration
Idempotency
```

### Later

```text
Advanced conditions
fairness
resource-aware scheduling
complex dependency graphs
preemption
rate limiting
```

But the **interfaces should leave room for them**.

---

# 60. The final conceptual model

After digging into the scheduler, I think our Event → Task → Execution model should now be:

```text
EVENT
 │
 │ "Something happened."
 ▼
TRIGGER / DIRECT ROUTE
 │
 │ "Does this event cause work?"
 ▼
TASK
 │
 │ "What responsibility exists?"
 ▼
ELIGIBILITY
 │
 │ "Can it run?"
 ├───────────────┐
 │               │
NO              YES
 │               │
WAIT/BLOCK       ▼
             SCHEDULER
                 │
        ┌────────┼────────┐
        ▼        ▼        ▼
      WHEN    PRIORITY  RESOURCES
        │        │        │
        └────────┼────────┘
                 ▼
               QUEUE
                 │
                 ▼
             DISPATCH
                 │
                 ▼
             EXECUTION
                 │
                 ▼
              RESULT
                 │
                 ▼
               EVENT
```

That last arrow is critical:

```text
RESULT → EVENT
```

because it closes the autonomous loop.

---

## The scheduler research/design is now substantially complete

I would freeze these conclusions before consolidation:

1. **Scheduler is not a cron system.**
    
2. **Scheduler is not an executor.**
    
3. **Scheduler is not an LLM.**
    
4. **Task and Execution are separate entities.**
    
5. **Recurring Tasks need Occurrences.**
    
6. **Eligibility is separate from scheduling.**
    
7. **Waiting, blocked, eligible and queued are different states.**
    
8. **Time, events and conditions can independently make work eligible.**
    
9. **Priority is separate from queueing.**
    
10. **Priority should be multi-factor, not just HIGH/MEDIUM/LOW.**
    
11. **Priority and preemption are separate policies.**
    
12. **Resource availability affects dispatch.**
    
13. **Interactive work needs a protected/high-priority execution lane.**
    
14. **The scheduler itself should be deterministic and LLM-independent.**
    
15. **Persistent state is authoritative; runtime queues are derived.**
    
16. **Recovery must reconstruct scheduling state after restart.**
    
17. **Retries create new execution attempts, not new logical tasks.**
    
18. **Expiration and misfire policies are first-class scheduling concerns.**
    
19. **Idempotency is required because exactly-once execution cannot simply be assumed.**
    
20. **Scheduler transitions should themselves generate events.**
    
21. **Scheduling provenance should explain why and when something executed.**
    
22. **The scheduler is fundamentally an eligibility + ordering + wake-up + dispatch-coordination system.**
    

And one particularly important conclusion for the architecture:

> **The Scheduler should not decide what an agent should do. It decides when already-defined work is eligible and which eligible work should receive execution resources.**

That boundary will prevent the Active Layer from becoming a giant "agent brain" with scheduling logic mixed into reasoning.

**I think we should now move to consolidation exactly as you proposed:** first consolidate _all_ findings—event taxonomy, event intake, Task model, scheduler, priority, execution lifecycle, three execution lanes, persistence/recovery, and LLM boundaries—into one coherent set of principles. Then we can design **Phase 1 architecture** from that specification rather than discovering fundamental boundaries while coding.
