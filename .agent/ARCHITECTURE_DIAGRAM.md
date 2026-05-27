# Architecture Diagram: Run Execution Lifecycle

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER / API LAYER                             │
│                  (POST /runs/{run_id}/start)                         │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          RunManager                                  │
│                    (Global Lifecycle Manager)                        │
│                                                                       │
│  • create_run()          - Creates run in database                   │
│  • start_run()           - Instantiates RunExecutor                  │
│  • stop_run()            - Cancels running executor                  │
│  • cleanup_zombie_runs() - Recovers from crashes ★NEW★              │
│                                                                       │
│  Zombie Cleanup Logic:                                               │
│  ┌─────────────────────────────────────────────────┐                │
│  │ For each run with status="running":              │                │
│  │   if graph_type == "automatic":                  │                │
│  │     → Mark as FAILED (interrupted mid-loop)      │                │
│  │   elif graph_type == "manual":                   │                │
│  │     → Revert to IDLE (waiting for user)         │                │
│  └─────────────────────────────────────────────────┘                │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         RunExecutor                                  │
│                      (THE SAFETY NET)                                │
│                   Infrastructure Management ONLY                     │
│                                                                       │
│  async def start(payload):                                           │
│    ┌─────────────────────────────────────────┐                      │
│    │ 1. Set status → RUNNING                 │ ← Infrastructure     │
│    │ 2. await _update_db_status(RUNNING)     │                      │
│    └─────────────────────────────────────────┘                      │
│                                                                       │
│    try:                                                               │
│      ┌─────────────────────────────────────────┐                    │
│      │ 3. final_state = await engine.execute() │                    │
│      └─────────────────────────────────────────┘                    │
│      return final_state  ← No status update! Middlewares handle it  │
│                                                                       │
│    except asyncio.CancelledError:  ← Sad Path                       │
│      ┌─────────────────────────────────────────┐                    │
│      │ Set status → STOPPED                    │                    │
│      │ await _update_db_status(STOPPED)        │                    │
│      └─────────────────────────────────────────┘                    │
│                                                                       │
│    except Exception:  ← Sad Path                                    │
│      ┌─────────────────────────────────────────┐                    │
│      │ Set status → FAILED                     │                    │
│      │ await _update_db_status(FAILED, error)  │                    │
│      └─────────────────────────────────────────┘                    │
│                                                                       │
│  ★ RunExecutor NO LONGER decides COMPLETED vs IDLE                  │
│  ★ That responsibility moved to Middlewares                         │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       WorkflowEngine                                 │
│                    (Pure Execution Engine)                           │
│                                                                       │
│  async def execute_run(payload, config, run_id):                     │
│    1. Create initial SystemState                                     │
│    2. Trigger before_run middlewares                                 │
│    3. Stream through LangGraph execution                             │
│       └─ For each step: trigger after_step middlewares               │
│    4. Trigger after_run middlewares  ★ HAPPY PATH HAPPENS HERE      │
│    5. Return final SystemState                                       │
│                                                                       │
│  ★ Engine has NO concept of database statuses                       │
│  ★ Only knows about RoutingSignals (CONTINUE, ATTACK, END)          │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                 ┌───────────┴───────────┐
                 │                       │
                 ▼                       ▼
  ┌──────────────────────────┐  ┌──────────────────────────┐
  │  AutomaticDatabaseMiddle │  │  ManualDatabaseMiddle   │
  │         ware             │  │        ware             │
  │  (BUSINESS LOGIC)        │  │  (BUSINESS LOGIC)       │
  │                          │  │                         │
  │  after_run():            │  │  after_run():           │
  │  ┌────────────────────┐  │  │  ┌───────────────────┐  │
  │  │ ★ HAPPY PATH       │  │  │  │ ★ HAPPY PATH      │  │
  │  │                    │  │  │  │                   │  │
  │  │ When LangGraph     │  │  │  │ When LangGraph    │  │
  │  │ reaches __end__:   │  │  │  │ reaches __end__:  │  │
  │  │                    │  │  │  │                   │  │
  │  │ Entire test DONE   │  │  │  │ Turn DONE         │  │
  │  │ ↓                  │  │  │  │ ↓                 │  │
  │  │ status=COMPLETED   │  │  │  │ status=IDLE       │  │
  │  │ completed_at=NOW   │  │  │  │ manual_wait=True  │  │
  │  │ final_score        │  │  │  │ Save checkpoint   │  │
  │  │ best_score         │  │  │  │                   │  │
  │  └────────────────────┘  │  │  └───────────────────┘  │
  └──────────────────────────┘  └──────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        SystemState                                   │
│                   (Pure Execution State)                             │
│                                                                       │
│  {                                                                    │
│    "run_id": "run_xyz",                                              │
│    "payload": {...},                                                 │
│    "config": {...},                                                  │
│    "current_turn": {                                                 │
│      "turn_id": "turn_1",                                            │
│      "attack": AttackPayload(...),                                   │
│      "defence": DefencePayload(...),                                 │
│      "evaluation": EvalResult(...)                                   │
│    },                                                                 │
│    "strategy_context": {...},                                        │
│    "routing_signal": "continue" | "attack" | "__end__"              │
│  }                                                                    │
│                                                                       │
│  ★ NO database status strings ("idle", "running", "completed")      │
│  ★ Only knows about routing: CONTINUE, ATTACK, END                  │
│  ★ Pure state - no side effects                                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Architectural Boundaries

### 1. SystemState (Engine State)
- **What it knows**: Routing signals (`CONTINUE`, `ATTACK`, `END`)
- **What it doesn't know**: Database status strings, persistence logic
- **Responsibility**: Pure execution state

### 2. Middlewares (Business Logic)
- **What they know**: Database schemas, run types, business rules
- **What they do**: Translate `__end__` signal to appropriate database status
- **Responsibility**: Happy Path status transitions

#### AutomaticDatabaseMiddleware
```python
after_run():
  __end__ → status="completed" + completed_at
```

#### ManualDatabaseMiddleware
```python
after_run():
  __end__ → status="idle" + manual_wait_active=True
```

### 3. RunExecutor (Infrastructure)
- **What it knows**: asyncio.Task lifecycle, exception handling
- **What it doesn't know**: Business logic (automatic vs manual)
- **Responsibility**: Sad Path status transitions

```python
start():
  → status="running"  (infrastructure start)
  
  catch CancelledError:
    → status="stopped"  (sad path)
  
  catch Exception:
    → status="failed"   (sad path)
```

### 4. RunManager (Global Lifecycle)
- **What it knows**: All executors, server lifecycle events
- **What it does**: Manages executor registry, handles server crashes
- **Responsibility**: Zombie run recovery

```python
cleanup_zombie_runs():
  for each run with status="running":
    if automatic → status="failed"
    if manual → status="idle" + manual_wait_active=True
```

## Status Transition State Machine

```
                    ┌──────────┐
                    │   IDLE   │
                    └─────┬────┘
                          │
                    start_run()
                          │
                    ┌─────▼────┐
                ┌───┤ RUNNING  ├───┐
                │   └──────────┘   │
                │                  │
         CancelledError       Exception
         (user stops)         (crash)
                │                  │
         ┌──────▼──────┐    ┌─────▼────┐
         │   STOPPED   │    │  FAILED  │
         └─────────────┘    └──────────┘
                
                LangGraph reaches __end__
                          │
         ┌────────────────┴────────────────┐
         │                                  │
    graph_type="automatic"         graph_type="manual"
         │                                  │
    ┌────▼─────┐                    ┌──────▼───┐
    │COMPLETED │                    │   IDLE   │
    └──────────┘                    └──────────┘
                                    + manual_wait_active=True
```

## Server Restart Recovery

```
Server Crash
    │
    │ (runs stuck with status="running")
    │
Server Restart
    │
    ▼
cleanup_zombie_runs()
    │
    ├─ Automatic Run (was mid-loop)
    │    └─→ status="failed"
    │        error="Server restarted during execution"
    │
    └─ Manual Run (was waiting for user)
         └─→ status="idle"
             manual_wait_active=True
```

## Benefits of This Architecture

1. **Single Responsibility**: Each component has one clear job
2. **Type Safety**: SystemState doesn't leak database concepts
3. **Testability**: Can test each component in isolation
4. **Maintainability**: Changes to one component don't affect others
5. **Correctness**: Manual runs properly wait for user input
6. **Resilience**: Intelligent recovery from server crashes
