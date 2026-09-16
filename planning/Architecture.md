Let's start.

# Pinky — Phase 1: Architectural Planning

We'll begin with the **Event/Input side**, because everything downstream depends on the guarantees established here.

The first thing I want to do is **not** choose technologies. We need to establish the contracts and responsibilities first.

Our Phase 1 architecture will be developed in this order:

```text
                    EXTERNAL WORLD
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
          Human       System        External
          Events      Events        Events
             │            │            │
             └────────────┼────────────┘
                          ▼
                   ┌─────────────┐
                   │Event Readers│
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │ Event Intake│
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │Event Storage│
                   └──────┬──────┘
                          ▼
                   ┌─────────────┐
                   │Event Router │
                   └──────┬──────┘
                          ▼
                ┌────────────────────┐
                │ Trigger / State    │
                │ Evaluation         │
                └─────────┬──────────┘
                          ▼
                       TASKS
                          │
                          ▼
                     SCHEDULER
                          │
                  ┌───────┴───────┐
                  ▼               ▼
               RUNNABLE         WAITING
                  │
                  ▼
                QUEUE
                  │
                  ▼
              DISPATCHER
                  │
       ┌──────────┼──────────┐
       ▼          ▼          ▼
 Deterministic Interactive Autonomous
                  │          │
               Small LLM  Strong LLM
```

We'll work through this from left to right.

---

# 1. First architectural boundary: Event Sources

The outside world is not Pinky.

Pinky observes the outside world through **Event Sources**.

An Event Source is anything capable of producing information relevant to Pinky.

Examples:

```text
Human
├── keyboard
├── terminal
├── GUI
├── microphone
└── API

Operating System
├── process
├── power
├── network
├── system lifecycle
└── notifications

Filesystem
├── file created
├── file modified
├── file deleted
└── directory changed

Applications
├── calendar
├── email
├── browser
├── messaging
└── other applications

External Services
├── APIs
├── webhooks
└── remote events

Devices
├── sensors
├── peripherals
└── hardware state

Time
├── scheduled time
├── timeout
├── deadline
└── delay
```

But there is an important distinction:

> **An Event Source is not necessarily an Event Reader.**

For example:

```text
Filesystem
    │
    ▼
Filesystem Reader
    │
    ▼
Pinky Event
```

The filesystem exists independently of Pinky.

The reader is Pinky's mechanism for observing it.

---

# 2. Event Readers

An Event Reader has one responsibility:

> **Observe a source and convert observations into candidate Pinky events.**

It should not:

* create Tasks
* call an LLM
* execute tools
* decide priority
* schedule autonomous work
* perform business logic

For example:

```text
FilesystemReader
      │
      │ observes
      ▼
OS filesystem event
      │
      │ converts
      ▼
FILE_CREATED
```

Likewise:

```text
CalendarReader
      │
      ▼
calendar provider
      │
      ▼
CALENDAR_EVENT_STARTED
```

And:

```text
UserInputReader
      │
      ▼
USER_MESSAGE_RECEIVED
```

This gives us a clean adapter boundary.

---

# 3. The crucial problem: readers behave differently

This is where the event taxonomy becomes practically important.

Some sources are naturally **push-based**.

Example:

```text
Webhook
   ↓
Pinky
```

Others are **listener-based**:

```text
Filesystem watcher
   ↓
callback
   ↓
Pinky
```

Others are **poll-based**:

```text
Every 30 seconds
      ↓
check Gmail
      ↓
new message?
      ↓
event
```

Others are **scheduler-driven**:

```text
08:00
 ↓
TIME_REACHED
```

And some are **user-driven**:

```text
user types
 ↓
message
```

Therefore Pinky should not have one universal mechanism called:

```text
EventListener
```

that pretends all sources work identically.

Instead, the conceptual interface should accommodate multiple observation strategies.

---

# 4. Reader categories

I would initially classify readers as:

### Push Reader

External system actively pushes data.

```text
Webhook
IPC
OS callback
```

### Listener Reader

Pinky subscribes to a source.

```text
filesystem watcher
socket
device listener
```

### Polling Reader

Pinky periodically asks a source whether something changed.

```text
email
API
some application state
```

### Scheduled Reader

Time itself generates observations.

```text
timer
deadline
delay
cron-like schedule
```

### Interactive Reader

Waits for direct human input.

```text
terminal
GUI
voice
```

This classification matters because **the active layer has to keep all of these alive simultaneously**.

---

# 5. The Event Reader Manager

We therefore need something responsible for the readers themselves.

Conceptually:

```text
                 Reader Manager
                       │
       ┌───────────────┼────────────────┐
       ▼               ▼                ▼
Filesystem        Calendar          User Input
 Reader             Reader             Reader
       │               │                │
       └───────────────┼────────────────┘
                       ▼
                  Event Intake
```

Its responsibilities should be limited to reader lifecycle:

```text
start
stop
restart
health
configuration
```

It should know:

```text
Which readers exist?
Which are enabled?
Are they alive?
Do they need restarting?
```

It should **not** determine what an event means.

---

# 6. Reader failure

This is important for a local always-on system.

Suppose:

```text
Gmail Reader
     ↓
crashes
```

That should not mean:

```text
Pinky crashes
```

Instead:

```text
Reader failure
      ↓
READER_FAILED
      ↓
Reader Manager
      ↓
restart
```

Potentially:

```text
retry
 ↓
backoff
 ↓
disable after repeated failure
 ↓
alert
```

This introduces our first use of the **Recovery/Lifecycle event category**.

---

# 7. Event Intake

Readers should produce **candidate events**.

They should not necessarily be trusted to construct the final canonical event representation.

So:

```text
Reader
  ↓
Candidate Event
  ↓
Event Intake
  ↓
Canonical Event
```

Event Intake is the first point where Pinky says:

> "This is now an event in my system."

---

# 8. Event Intake responsibilities

I would make Event Intake responsible for:

```text
validation
normalization
identity
timestamps
source metadata
deduplication
persistence
publication
```

Potential flow:

```text
Candidate Event
      │
      ▼
Validate
      │
      ▼
Normalize
      │
      ▼
Assign Event ID
      │
      ▼
Attach timestamps
      │
      ▼
Deduplicate
      │
      ▼
Persist
      │
      ▼
Publish
```

This ordering matters.

We should **persist before considering the event successfully accepted**.

---

# 9. Why persistence comes before publication

Consider:

```text
Event arrives
 ↓
publish
 ↓
consumer receives it
 ↓
Pinky crashes
 ↓
event never persisted
```

We've lost the event.

Instead:

```text
Event arrives
 ↓
persist
 ↓
publish
```

Now:

```text
Pinky crashes
 ↓
event exists
```

Recovery can rediscover it.

This gives us the basic durability guarantee:

> Once Event Intake acknowledges an event, the event must be recoverable.

---

# 10. Deduplication

This is unavoidable.

Readers can produce duplicate events.

For example, a polling reader might do:

```text
poll 1 → email #123
poll 2 → email #123
```

Or a webhook might be delivered twice.

Therefore an event needs an identity strategy.

Potentially:

```text
event_id
```

for Pinky's identity, plus:

```text
source_event_id
```

for the source's identity.

Then:

```text
source = gmail
source_event_id = 12345
```

can be recognized as already processed.

But this cannot be universal.

Some sources don't provide stable event IDs.

Then we may need a source-specific deduplication key.

We'll define this properly when we design the Event schema.

---

# 11. Canonical Event

After Intake, every event should conform to one canonical envelope.

Something approximately like:

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

But I don't want to freeze this schema yet.

We first need to determine:

* which fields are mandatory
* which are optional
* which belong in metadata
* how versioning works
* how event types are represented
* how payload schemas are validated

That's our next design problem.

---

# 12. Event Intake should be deterministic

This is worth explicitly establishing.

We don't want:

```text
event
 ↓
LLM
 ↓
"what type of event is this?"
```

for ordinary events.

Instead:

```text
source adapter
 ↓
known event type
 ↓
validation
```

For example:

```text
FilesystemReader
 ↓
FILE_CREATED
```

not:

```text
FilesystemReader
 ↓
"Something happened involving a file..."
 ↓
LLM
 ↓
FILE_CREATED
```

The LLM should enter later when semantic interpretation is actually required.

---

# 13. But human input is different

Human input is a particularly interesting case.

We may receive:

```text
"Remind me to call Mom tomorrow at 8."
```

The raw event is:

```text
USER_MESSAGE_RECEIVED
```

The **event classification is deterministic**.

The **meaning of the message** may require the Interactive LLM.

So:

```text
USER_MESSAGE_RECEIVED
        ↓
Event Intake
        ↓
Event Router
        ↓
Interactive Execution
        ↓
Small LLM
        ↓
"User wants a scheduled reminder."
        ↓
CREATE_TASK command
```

This preserves the boundary between:

```text
event classification
```

and:

```text
semantic interpretation
```

---

# 14. Event Router

After an event is persisted, we need to determine what happens next.

That's the Router.

Conceptually:

```text
                    Event
                      │
                      ▼
                Event Router
                      │
        ┌─────────────┼──────────────┐
        ▼             ▼              ▼
    State Update   Trigger Match   Direct Action
                       │
                       ▼
                     Task
```

But I would actually make one more distinction.

The Router shouldn't be a giant `if/else` system containing the business logic of Pinky.

It should primarily answer:

> **Which subsystem should receive this event?**

---

# 15. Event consumers

That suggests a more scalable architecture:

```text
                    EVENT
                      │
                 Event Store
                      │
                 Event Router
                      │
       ┌──────────────┼───────────────┐
       ▼              ▼               ▼
 State Projector  Trigger Engine   Lifecycle
                                       │
                                       ▼
                                  other consumers
```

Potential consumers include:

```text
Task Trigger Engine
Execution Wake Engine
Condition Engine
State Projectors
Notification System
Observability
Recovery
```

This is significantly better than making one Router understand every possible consequence of every event.

---

# 16. One event can have multiple consumers

Example:

```text
FILE_CREATED
```

could simultaneously cause:

```text
State Projector
     ↓
record file

Trigger Engine
     ↓
activate "summarize new PDFs"

Observability
     ↓
record event

Condition Engine
     ↓
re-evaluate condition
```

This is why an event system is more useful than direct function calls.

---

# 17. Event → Task is not always one-to-one

We should explicitly establish:

```text
1 Event → 0 Tasks
1 Event → 1 Task
1 Event → N Tasks
```

For example:

```text
EMAIL_RECEIVED
```

might activate:

```text
Task A: classify email
Task B: check if urgent
Task C: update CRM
```

Potentially all three.

Conversely:

```text
FILE_CREATED
```

may activate nothing.

---

# 18. Event → existing Execution

There's another path we need:

```text
Event
 ↓
Wake condition matcher
 ↓
Existing Execution
 ↓
resume
```

Example:

```text
Autonomous Execution
      ↓
WAITING_FOR_EMAIL
```

Later:

```text
EMAIL_RECEIVED
      ↓
Wake matcher
      ↓
Execution resumes
```

This is why we shouldn't model every event reaction as creating a new Task.

---

# 19. The first major subsystem boundary

At this point we have:

```text
┌──────────────────────────────────────────┐
│              EVENT SUBSYSTEM             │
│                                          │
│  Sources → Readers → Intake → Store      │
│                         ↓                │
│                      Router              │
└───────────────────────┬──────────────────┘
                        │
                        ▼
                 Work Activation
```

And **Work Activation** is where we transition from the Event domain into Task/Execution/Scheduler territory.

That's an important architectural boundary.

---

# 20. Next: Task activation

Now we can move one layer deeper.

Suppose:

```text
FILE_CREATED
```

arrives.

The Trigger Engine evaluates registered Task triggers:

```text
Task A:
when PDF created in /research
```

```text
Task B:
when anything created in /downloads
```

The event matches both.

We get:

```text
FILE_CREATED
       │
       ▼
Trigger Engine
       │
       ├────→ Task A
       │
       └────→ Task B
```

But **neither Task necessarily executes immediately**.

Instead we create or activate work:

```text
Task A
  ↓
Occurrence / activation
  ↓
Scheduler
```

This distinction is where our next architectural layer begins.

---

# 21. The next thing we should design

I recommend we now go deeply into:

## **Task Activation + Scheduler Architecture**

Specifically:

```text
Event
 ↓
Trigger Match
 ↓
Task Activation
 ↓
Eligibility
 ↓
Runnable
 ↓
Priority Calculation
 ↓
Queue
 ↓
Resource Admission
 ↓
Dispatch
```

And we'll answer the hard questions:

* Does every Task activation create an Execution?
* Where does an Occurrence fit?
* Who owns eligibility?
* Is scheduling event-driven, timer-driven, or both?
* How do we implement thousands of future timers?
* How are priorities calculated?
* How do interactive requests jump ahead?
* How does autonomous work avoid starvation?
* What happens when the system is overloaded?
* Can deterministic work bypass the LLM queues?
* How do retries enter the scheduler?
* How do waiting Executions re-enter it?
* What exactly happens after a crash?
* How do we prevent duplicate Executions?
* How do deadlines affect priority?
* How do recurring Tasks behave when executions overlap?

**That is the core of the Scheduler design, and I think we should solve it before moving to the Execution Manager.**
