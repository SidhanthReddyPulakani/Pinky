Yes. **The idea is technically viable and, with some adjustments, I think it is a cleaner architecture than treating every event identically.** But I would _not_ define it simply as "small LLM = human, big LLM = everything else." There are some important boundaries.

I checked current agent architectures, especially Hermes and OpenHands. Hermes is particularly relevant because it already supports **different models for interactive chat and scheduled jobs**, with per-job model selection and a separate cron fleet. ([GitHub](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md?utm_source=chatgpt.com "hermes-agent/website/docs/user-guide/features/cron.md at main · NousResearch/hermes-agent · GitHub")) OpenHands similarly separates its event-driven agent loop from the model/tool layers. ([GitHub](https://github.com/OpenHands/docs/blob/main/sdk/arch/agent.mdx?utm_source=chatgpt.com "docs/sdk/arch/agent.mdx at main · OpenHands/docs · GitHub"))

## Your idea

You're proposing:

```text
                    EVENTS
                      │
             ┌────────┴────────┐
             │                 │
       HUMAN EVENTS       OTHER EVENTS
             │                 │
             ▼                 ▼
        SMALL LLM          LARGE LLM
             │                 │
       conversation       background
       scheduling         reasoning
       simple tasks       autonomous tasks
```

I think the **separation itself is excellent**.

But I'd change the terminology slightly:

```text
          INTERACTIVE PLANE
                  │
             Small LLM
                  │
        human-facing intelligence


          AUTONOMOUS PLANE
                  │
             Strong LLM
                  │
        task/execution intelligence
```

Because the small model may sometimes need to invoke the stronger model.

---

# 1. Why this makes sense

The two workloads are fundamentally different.

### Human interaction

The user says:

> "What's the weather?"

or:

> "Remind me to call Mom tomorrow at 6."

You don't necessarily need your strongest model.

You need:

- low latency
    
- good instruction following
    
- conversation
    
- intent extraction
    
- scheduling
    
- simple tool selection
    
- concise responses
    

A smaller model is a very reasonable choice.

---

### Autonomous/background work

Now consider:

> "Every morning check my emails, identify anything important, cross-reference my calendar, and prepare a summary."

That's a completely different workload.

You may need:

- planning
    
- multiple tool calls
    
- retrieval
    
- reasoning
    
- error recovery
    
- long context
    
- multi-step execution
    
- deciding whether something is important
    

That's where the stronger model makes sense.

Hermes actually supports this kind of model separation: cron jobs can have a model pinned independently from the interactive chat model. ([GitHub](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md?utm_source=chatgpt.com "hermes-agent/website/docs/user-guide/features/cron.md at main · NousResearch/hermes-agent · GitHub"))

So this isn't merely theoretically possible; **real agent systems already implement the basic idea.**

---

# 2. But here's the first major correction

I wouldn't make:

```text
Human → Small
Everything else → Large
```

a hard rule.

I'd make:

```text
                    EVENT
                      │
                      ▼
               EVENT ROUTER
                      │
            ┌─────────┴─────────┐
            ▼                   ▼
       INTERACTIVE          AUTONOMOUS
            │                   │
         Small LLM          Strong LLM
```

The **event type determines the default execution plane**, but the router can override it.

For example:

### User asks a complex question

> "Research the current state of quantum error correction and compare the major approaches."

This starts in the interactive plane:

```text
User
 ↓
Small LLM
```

But the small model could determine:

```text
This requires substantial research.
```

and delegate:

```text
Small LLM
    ↓
CREATE_TASK
    ↓
Strong LLM
    ↓
research
    ↓
result
    ↓
Small LLM
    ↓
present to user
```

That gives us a very powerful architecture.

---

# 3. The small model becomes the "front desk"

Think of it as:

```text
                         USER
                           │
                           ▼
                    ┌─────────────┐
                    │  SMALL LLM  │
                    │             │
                    │ Understand  │
                    │ Respond     │
                    │ Schedule    │
                    │ Delegate    │
                    └──────┬──────┘
                           │
                 ┌─────────┴─────────┐
                 │                   │
              answer              delegate
                 │                   │
                 ▼                   ▼
               USER              STRONG LLM
                                     │
                                  execute
```

The small model doesn't need to be the "less intelligent version of the agent."

It can be a **specialized interaction model**.

That's an important distinction.

---

# 4. The strong model becomes an execution worker

The strong model could receive things like:

```text
TASK_CREATED
SCHEDULE_DUE
FILE_CHANGED
EMAIL_RECEIVED
WEBHOOK_RECEIVED
TOOL_RESULT
SYSTEM_ALERT
```

and then:

```text
Strong LLM
    │
    ├── reason
    ├── retrieve
    ├── call tools
    ├── observe
    ├── reason again
    └── finish
```

That is much closer to what we normally mean by an autonomous agent.

OpenHands describes its core agent as an event-driven reasoning/action loop where the agent reads events, queries the LLM, executes tools, and produces new events. ([GitHub](https://github.com/OpenHands/docs/blob/main/sdk/arch/agent.mdx?utm_source=chatgpt.com "docs/sdk/arch/agent.mdx at main · OpenHands/docs · GitHub"))

---

# 5. The really interesting part: the two models don't have to be isolated

I'd actually design this:

```text
                     EVENT BUS
                         │
             ┌───────────┴───────────┐
             │                       │
             ▼                       ▼
       INTERACTIVE                AUTONOMOUS
          PLANE                      PLANE
             │                       │
          Small LLM                Big LLM
             │                       │
             └───────────┬───────────┘
                         │
                   Shared Systems
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
            Tools      Memory     Scheduler
```

The models should **not directly communicate through arbitrary prompts**.

Instead, they communicate through structured events/tasks.

For example:

```json
{
  "event": "TASK_CREATED",
  "task_id": "abc123",
  "goal": "Research today's AI news",
  "priority": "normal",
  "created_by": "interactive_agent"
}
```

Then:

```text
Small LLM
   ↓
TASK_CREATED
   ↓
Event Bus
   ↓
Strong LLM
```

And the strong model eventually produces:

```json
{
  "event": "TASK_COMPLETED",
  "task_id": "abc123",
  "result": "...",
  "status": "success"
}
```

Then:

```text
TASK_COMPLETED
      ↓
Interactive plane
      ↓
Small LLM
      ↓
"Here's what I found..."
```

This is much cleaner than:

```text
Big LLM → directly call Small LLM
```

---

# 6. This also solves an important resource problem

Suppose you have:

```text
Qwen 3.5 4B
```

as your interactive model and eventually something much larger as your reasoning model.

You don't necessarily need both loaded constantly.

You could have:

```text
                    Model Manager
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
        Small Model             Strong Model
        loaded often             loaded on demand
```

For example:

```text
User chatting
    ↓
Small model loaded
    ↓
Strong model unloaded
```

Then:

```text
Background task
    ↓
Strong model requested
    ↓
load strong model
    ↓
execute
    ↓
unload / keep warm
```

The model server itself can remain running while models are loaded/unloaded as needed. Ollama supports configurable model keep-alive behavior. This makes this architecture particularly practical for local systems. ([GitHub](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md?utm_source=chatgpt.com "hermes-agent/website/docs/user-guide/features/cron.md at main · NousResearch/hermes-agent · GitHub"))

---

# 7. There's one thing I strongly recommend changing

Don't make the strong model responsible for **all non-human events**.

Some events shouldn't invoke an LLM at all.

For example:

```text
FILE_DELETED
```

doesn't automatically mean:

```text
CALL STRONG LLM
```

Likewise:

```text
TIMER_FIRED
```

might execute a deterministic operation.

Hermes explicitly supports scheduled jobs that run **without an agent/LLM at all**, which is a very good architectural pattern. ([GitHub](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md?utm_source=chatgpt.com "hermes-agent/website/docs/user-guide/features/cron.md at main · NousResearch/hermes-agent · GitHub"))

So we actually want:

```text
                     EVENT
                       │
                       ▼
                 EVENT ROUTER
                       │
       ┌───────────────┼────────────────┐
       ▼               ▼                ▼
 deterministic    small LLM        strong LLM
   handler        interaction       autonomy
```

For example:

```text
Timer → send notification
       ↑
       no LLM required
```

while:

```text
Email received
      ↓
Strong LLM
      ↓
Analyze
```

---

# 8. Therefore the architecture becomes much cleaner

I would currently draw it like this:

```text
                         EVENT SOURCES
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
        Human             Scheduled            External
          │                   │                   │
          └───────────────────┼───────────────────┘
                              ▼
                       ┌──────────────┐
                       │  EVENT BUS   │
                       └──────┬───────┘
                              ▼
                       ┌──────────────┐
                       │ EVENT ROUTER │
                       └──────┬───────┘
                              │
             ┌────────────────┼────────────────┐
             │                │                │
             ▼                ▼                ▼
       Deterministic     Interactive       Autonomous
          Handler          Agent             Agent
                            │                  │
                         Small LLM          Strong LLM
                            │                  │
             ┌──────────────┴──────────────────┘
             │
             ▼
        SHARED SYSTEMS
             │
      ┌──────┼──────┬───────┐
      ▼      ▼      ▼       ▼
    Tools  Memory  State  Scheduler
```

This is, in my opinion, **a better foundation than our previous "everything goes into one agent" design.**

---

# 9. There's an even bigger advantage

The architecture becomes naturally scalable.

Today:

```text
Small LLM = Qwen 3.5 4B
Strong LLM = same Qwen 3.5 4B
```

Nothing changes architecturally.

Later:

```text
Small LLM = Qwen 4B
Strong LLM = Qwen 30B
```

Still nothing changes.

Later:

```text
Small = local 4B
Strong = local 32B
```

Still nothing changes.

And eventually:

```text
Small = local
Strong = remote
```

Still nothing changes.

The **routing contract remains stable**.

---

# 10. One potential weakness

There is a real downside:

### The small LLM becomes a bottleneck.

If you ask it:

> "I need you to monitor my downloads and tell me when my 15GB file finishes, then analyze the downloaded data."

It needs to understand enough to correctly classify/delegate the task.

If the small model misinterprets it, the architecture fails **before the strong model gets involved**.

So the routing layer should not depend entirely on free-form LLM reasoning.

I'd combine:

```text
Rules
+
Structured classification
+
Small LLM
+
Explicit escalation
```

For example:

```text
if event.type == SCHEDULED_TASK:
    → autonomous

if event.type == USER_MESSAGE:
    → interactive

if interactive_agent says:
    complexity > threshold:
        → autonomous

if task requires tools > N:
    → autonomous
```

The LLM helps determine intent; the runtime retains control.

---

# My unbiased verdict

**Yes, I think your two-plane idea is realistic and architecturally sound.**

I'd rate it:

|Aspect|Assessment|
|---|---|
|Technical feasibility|**Excellent**|
|Resource efficiency|**Excellent**|
|Separation of concerns|**Excellent**|
|Scalability|**Excellent**|
|Simplicity|**Better than one giant agent**|
|Risk|**Model-routing mistakes**|
|Main correction|Don't send every non-human event to the strong LLM|
|Recommended|**Yes**|

And there is real precedent for the important pieces: Hermes already separates interactive and cron model selection, supports fresh agent sessions for scheduled jobs, and allows deterministic scheduled jobs to bypass the LLM entirely. ([GitHub](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/cron.md?utm_source=chatgpt.com "hermes-agent/website/docs/user-guide/features/cron.md at main · NousResearch/hermes-agent · GitHub"))

So I would **keep this architecture on the drawing board**:

```text
                 ACTIVE LAYER
                      │
                EVENT ROUTER
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
  Deterministic   Interactive    Autonomous
     System         Agent           Agent
                     │               │
                  Small LLM       Strong LLM
```

The next thing I'd work out is **the exact boundary between Interactive Agent and Autonomous Agent**—specifically, what the small model is allowed to do, what causes escalation to the strong model, and how the two exchange work/results. That's where this design either becomes genuinely robust or turns into two unnecessarily duplicated agents.