# FortiPrompt — Architecture

## Overview

FortiPrompt is an adversarial testing engine for AI systems. It drives automated red-teaming runs — generating attack prompts, forwarding them to a target system (the "defence"), and evaluating the results — using a graph-based execution model built on LangGraph.

---

## Layer Diagram

```
┌──────────────────────────────────────────────────────────┐
│                        API / WebSocket                    │
│          FastAPI (runs.py, discovery.py, data.py)        │
│          Socket.IO (real-time progress events)           │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                      RunManager                          │
│   Owns run lifecycle (IDLE → RUNNING → COMPLETED/FAILED) │
│   Instantiates WorkflowEngine per run                    │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────────────┐
│                   WorkflowEngine                         │
│   Builds the LangGraph StateGraph via GraphBuilder       │
│   Wraps node execution with registered middlewares       │
│   Streams SystemState through the graph                  │
└──────┬─────────────────┬────────────────────┬────────────┘
       │                 │                    │
  ┌────▼────┐     ┌──────▼──────┐     ┌──────▼──────┐
  │  Nodes  │     │  Strategy   │     │ Middlewares  │
  │         │     │             │     │              │
  │ attack  │     │ route()     │     │ Database     │
  │ defence │     │ execute_    │     │ WebSocket    │
  │ eval    │     │ generation()│     │ Logging      │
  │ router  │     │             │     │              │
  └────┬────┘     └──────┬──────┘     └──────────────┘
       │                 │
  ┌────▼─────────────────▼────┐
  │        Providers           │
  │  OpenAI / Gemini / Ollama  │
  └────────────────────────────┘
```

---

## Core Concepts

### SystemState

`SystemState` (defined in `engine/state.py`) is a `TypedDict` that flows through every node in the LangGraph graph. It carries:

- `current_turn` — attack, defence, and evaluation payloads for the current cycle
- `strategy_context` — persistent memory owned by the strategy (turn counter, history, etc.)
- `routing_signal` — set by the strategy to tell the router node where to go next
- `run_id`, `payload`, `config`, `start_time` — run-level metadata

LangGraph calls the `merge_turn_data` and `merge_context` reducer functions automatically when multiple nodes write to the same key. Both reducers use `deepcopy` to prevent cross-turn state mutation.

### Strategy

Every run has exactly one `AttackStrategy` (from `strategies/base.py`). The strategy owns two responsibilities:

1. **Generation** — `execute_generation(state)` produces the `AttackPayload` for a turn.
2. **Routing** — `route(state)` returns a `RoutingSignals` constant that tells the `RouterNode` what to do after evaluation (loop for another attack, or end the run).

No routing logic lives anywhere except in the strategy. Graph builder and nodes are routing-agnostic.

### Nodes

Nodes are pure functions wrapped in a `BaseNode` class (`nodes/base.py`). Each node:

- Receives `SystemState`
- Performs its work (call an LLM, call an HTTP endpoint, run an evaluator)
- Returns a state delta (only the keys it changed)

Nodes are registered in `engine/registry.py` and instantiated by the graph builder. They have no knowledge of middlewares, strategies, or each other.

### Middlewares

Middlewares observe the execution without coupling to it. The `WorkflowEngine` calls middleware hooks (`before_run`, `before_step`, `after_step`, `after_run`) around each node execution. Middlewares:

- Write run data to MongoDB (`automatic_database_middleware.py`, `batch_database_middleware.py`, `manual_database_middleware.py`)
- Broadcast progress over Socket.IO (`automatic_ws_middleware.py`, `batch_ws_middleware.py`, `manual_ws_middleware.py`)
- Log structured output to the console (`logging_middleware.py`)

Middlewares do not call each other and do not modify state.

### Graph Topology

```
[init]
  │
  ▼
[attack] ─────────────────────┐
  │                           │
  ▼                           │
[defence]                     │
  │                           │
  ▼                           │
[eval]                        │
  │                           │
  ▼                           │
[router] ── ATTACK ───────────┘
  │
  └── END ──► (graph terminates)
```

The `RouterNode` calls `strategy.route(state)` and returns the result directly as the LangGraph edge label. The graph builder maps edge labels to destination nodes.

---

## Directory Layout (Phase 1 end state)

```
core/
  __init__.py
  logging.py       ← structured console logger
  models.py        ← AttackPayload, DefencePayload, EvalResult
  config.py        ← GraphConfig, StrategyConfig, node config models
  constants.py     ← NodeName, RunStatus string constants
  env.py           ← Pydantic Settings loaded from .env

engine/
  state.py         ← SystemState, TurnData, RoutingSignals, reducers
  graph_builder.py ← builds the LangGraph StateGraph
  workflow_engine.py ← drives execution, calls middleware hooks
  registry.py      ← node and strategy registries
  provider_registry.py ← LLM provider registry

nodes/             ← one file per node implementation
middlewares/       ← one file per middleware implementation
strategies/        ← one file per strategy implementation
providers/         ← one file per LLM provider

server/
  main.py          ← FastAPI app, lifespan, router mounting
  run_manager.py   ← run lifecycle, executor management
  api/
    runs.py        ← create, start, stop, delete, list, get runs
    discovery.py   ← list strategies, providers, nodes + schemas
    data.py        ← get attacks, defences, evaluations, stats
    manual_routes.py ← manual session and turn management
    schemas.py     ← Pydantic request/response models
  database/
    connection.py
    models.py      ← MongoDB document models
    operations.py  ← async CRUD helpers
  websocket/
    socketio_manager.py
    operations.py

scripts/
  build_defence_models.py  ← standalone training script (not importable)

docs/
tests/
.env.example
```

---

## Data Flow (automatic run)

1. `POST /api/v1/runs` → creates a `RunModel` in MongoDB with status `idle`
2. `POST /api/v1/runs/{run_id}/start` → `RunManager.start_run()` creates a `RunExecutor` and calls `WorkflowEngine.execute()`
3. `WorkflowEngine` builds the graph, attaches middlewares, calls `graph.astream(initial_state)`
4. For each node execution:
   - `before_step` hooks fire (logging, DB prep)
   - Node executes, returns state delta
   - LangGraph merges delta into `SystemState` via reducers
   - `after_step` hooks fire (DB write, WS broadcast)
5. `RouterNode` calls `strategy.route()` → returns `ATTACK` or `END`
6. On `END`: `after_run` hooks fire, run status updated to `completed`

---

## Configuration

All environment-sourced configuration lives in `core/env.py`. Copy `.env.example` to `.env` and set values there. The `get_settings()` singleton is called by:

- `server/database/connection.py` — MongoDB URI and DB name
- `server/main.py` — CORS origins, host, port
- `providers/ollama_provider.py` — Ollama base URL
- `core/logging.py` — debug enabled flag and minimum log level
