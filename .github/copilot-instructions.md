# FortiPrompt — Copilot Instructions

## What This Project Is

FortiPrompt is a **modular, automated red-teaming framework** for testing the robustness of LLM systems against adversarial attacks — prompt injections, jailbreaks, roleplay exploits, and data extraction attempts.

The core idea: pit an **Attacker Agent** against a **Defender Endpoint** in an automated loop, with a **Judge** deciding whether the attack succeeded. Results are logged to a local MongoDB database for analysis.

---

## The Golden Rule of This Codebase

> The Orchestrator manages **data flow**. It has zero knowledge of what happens inside any node.

Every component communicates through a single shared dictionary (`ArenaState`). Nodes read from it, do their work, write back to it. That's the entire contract. This means you can swap out any attacker, defender, or judge without touching anything else.

---

## Architecture at a Glance

```
START
  │
  ▼
[Attacker Node]   → generates current_prompt
  │
  ▼
[Defender Node]   → generates current_response
  │
  ▼
[Judge Node]      → writes evaluation_result: "breached" | "blocked"
  │
  ▼
[Router]          → breached? → END
                    blocked + max turns hit? → END
                    blocked + turns left? → loop back to Attacker
  │
  ▼
[Telemetry Node]  → logs everything to SQLite (directly called by Orchestrator within graph) → END
```

The graph is built with **LangGraph**. The routing edges are fixed. The data is dynamic.

---

## Directory Structure & What Lives Where

```
engine/
├── .github/
│   ├── copilot-instructions.md     ← you are here
│   └── memory/                     ← persistent context notes (see below)
│
├── src/
│   ├── core/
│   │   ├── .instructions.md                ← Instructions for agents
│   │   ├── state.py                ← ArenaState TypedDict (the shared clipboard)
│   │   ├── interfaces.py           ← BaseAttacker, BaseDefender, BaseEvaluator, BaseAttackStrategy
│   │   └── orchestrator.py         ← LangGraph graph assembly + run() entry point
│   │
│   ├── attackers/
│   │   ├── llm_attacker.py         ← LangChain-powered attacker (takes any model + strategy)
│   │   ├── mock_attacker.py        ← reads payloads from a JSON dataset file
│   │   └── strategies/
│   │       ├── single_turn.py      ← fresh payload each turn, no history
│   │       └── multi_turn.py       ← builds on conversation history, escalates
│   │
│   ├── defenders/
│   │   ├── api_defender.py         ← raw HTTP POST to any external endpoint
│   │   ├── llm_defender.py         ← LangChain model as defender (with optional filters)
│   │   ├── mock_defender.py        ← scripted responses for testing
│   │   └── filters/
│   │       ├── base_filter.py      ← BaseFilter interface + FilterResult dataclass
│   │       ├── regex_pre_filter.py ← blocks prompts matching known attack patterns
│   │       └── (add more filters here)
│   │
│   ├── evaluators/
│   │   ├── llm_judge.py            ← LLM-as-judge, renders BREACHED/BLOCKED verdict
│   │   └── string_judge.py         ← deterministic regex/substring matching, no LLM needed
│   │
│   └── telemetry/
│       └── tracker.py              ← SQLiteTracker, logs every turn to run_history.sqlite3
│
├── data/
│   └── attacks_input.json          ← dataset of pre-written attack payloads
├── logs/
│   └── run_history.sqlite3         ← auto-created on first run
├── main.py                         ← wire components together and call orchestrator.run()
├── requirements.txt
└── .env.example                    ← API keys and config template

app_orchestrator/
    ├── __init__.py
    ├── app_orchestrator.py         ← Manages Engine runs, database interaction, event handling
    └── events.py                   ← Defines event types and event queue

```

---

## The Shared State (ArenaState)

Every node reads and writes this dict. Never pass data any other way.

**Note:** The `ArenaState` design is a preliminary idea and subject to change. This serves as a general concept for shared data flow.

```python
{
  "run_id": str,               # unique per run
  "goal": str,                 # what the attacker is trying to achieve
  "strategy": str,             # name of the attack strategy
  "max_turns": int,            # loop limit
  "turn_count": int,           # current iteration
  "chat_history": [...],       # list of {"role": "attacker"|"defender", "content": str}
  "current_prompt": str,       # latest attack payload
  "current_response": str,     # latest defender response
  "evaluation_result": str,    # "breached" | "blocked" | "pending"
  "evaluation_reasoning": str, # judge's explanation
  "strategy_metadata": dict,   # attacker's internal scratchpad (carry notes between turns)
  "final_outcome": str,        # "attacker_wins" | "defender_wins"
}
```

---

## How to Add a New Component

### New Attacker
Subclass `BaseAttacker` from `src/core/interfaces.py`. Implement `generate_attack(state) -> dict`. The dict must include `current_prompt`.

**Note:** These are general instructions to illustrate the use of interfaces and hierarchical organization, promoting an object-oriented approach to structuring the project.

### New Defender
Subclass `BaseDefender`. Implement `get_response(state) -> dict`. Must include `current_response`.

### New Evaluator
Subclass `BaseEvaluator`. Implement `evaluate(state) -> dict`. Must include `evaluation_result` as `"breached"` or `"blocked"`.

### New Attack Strategy
Subclass `BaseAttackStrategy`. Implement `build_prompt(state) -> str` and `should_reset_history(state) -> bool`. Inject into `LLMAttacker`.

### New Defender Filter
Subclass `BaseFilter` from `src/defenders/filters/base_filter.py`. Implement `check(text) -> FilterResult`. Pass as `pre_filters` or `post_filters` to `LLMDefender`.

---

## Key Design Decisions to Respect

- **The Orchestrator is not a memory manager.** It only passes state. Attackers manage their own `strategy_metadata`.
- **Filters are not evaluators.** Filters are internal to the defender. The Judge evaluates the full exchange externally.
- **LLM providers are injected, not hardcoded.** Always accept a `BaseChatModel` parameter. Never instantiate a specific model inside a module.
- **Nodes return partial dicts.** LangGraph merges them. Only return keys you actually updated.
- **The Defender is always a black box to the Orchestrator.** It could be a local model, a remote API, a guarded pipeline — the Orchestrator doesn't care.

---

## Tech Stack

- **LangGraph** — state machine / graph orchestration
- **LangChain** — LLM provider abstraction (supports OpenAI, Anthropic, Ollama, any OpenAI-compatible endpoint)
- **MongoDB** — telemetry storage (via standard library `pymongo`)
- **requests** — HTTP client for `APIDefender`
- **Python 3.10**

---

## Configuration and Execution

FortiPrompt is designed for flexibility, allowing you to configure and run test pipelines with interchangeable components.

### Centralized Configuration

A primary configuration file (e.g., `config.yaml`) will serve as the central hub for defining and managing test runs. This file will allow you to:

*   **Select Components**: Specify which attacker, defender, evaluator, and attack strategy to use for a given run.
*   **Parameterize Components**: Define specific parameters for each selected component (e.g., LLM model to use, filter thresholds, prompt templates).
*   **Manage Data Sources**: Indicate the datasets or input files to be used for attacks, mock responses, or other data-driven aspects of the test.
*   **Control Execution**: Set parameters like `max_turns` and other run-specific settings.

### State and Memory Management for Concurrent Runs

Each test run initiated through the configuration will have its own isolated `ArenaState`. This ensures that:

*   **Independent Runs**: Multiple test instances can run concurrently without interfering with each other.
*   **State Persistence**: The `ArenaState` for each run will maintain its unique `run_id`, `chat_history`, and `strategy_metadata`, allowing for detailed tracking and analysis of individual test outcomes.

### Data Integration

The configuration file will also specify how data is integrated into the pipeline:

*   **Input Data**: Define paths to datasets for attack payloads (e.g., `data/attacks_input.json`) or other input requirements.
*   **Mock Data**: Specify mock responses or data for testing defender behavior in isolation.
*   **Custom Data**: Allow users to point to custom data sources for specialized testing scenarios.

This approach ensures that you can easily set up, run, and manage diverse red-teaming experiments with full control over the pipeline's components and data.

### Overall System Architecture (External View)

This section describes how external components (API Gateway, UI) interact with the core FortiPrompt engine.

```
[UI/External Client]
  │
  ▼
[API Gateway]
  │ (HTTP requests - e.g., /runs to start, /runs/{id} for status)
  ▼
[AppOrchestrator]
  │ (1. Starts Engine run in background)
  │ (2. Queries DB for run status)
  │ (3. Receives Engine events)
  ▼
[Engine]
  │ (LangGraph pipeline - Attacker → Defender → Judge → Telemetry)
  │
  │ (Internal event emission for real-time updates)
  ▼
[Event Queue] ─► [AppOrchestrator (Event Handler)]
  │
  │ (Notifies WebSocketManager)
  ▼
[API Gateway (WebSocketManager)]
  │ (Pushes real-time updates)
  ▼
[UI/External Client]
```

**Interaction Flow:**

*   **HTTP Requests (e.g., Start Run)**: The `API Gateway` receives an HTTP request (e.g., `POST /runs`). It delegates to the `AppOrchestrator` to initiate a new red-teaming run. The `AppOrchestrator` then kicks off the `Engine`'s LangGraph pipeline as an asynchronous background task, persists initial run details to the database, and immediately returns a `202 Accepted` response to the `API Gateway`.
*   **HTTP Requests (e.g., Get Run Status)**: The `API Gateway` receives an HTTP request (e.g., `GET /runs/{run_id}`). It delegates to the `AppOrchestrator`, which queries the database (populated by the `Telemetry Node`) for the latest status and details of the specified run, returning this data to the `API Gateway`.
*   **Real-time Updates (WebSockets)**:
    1.  **Engine Event Emission**: During its execution, after significant steps (and after `Telemetry` persistence), the `Engine` emits internal "state updated" events.
    2.  **Event Queue**: These events are pushed into an `Event Queue` (e.g., an `asyncio.Queue` or a dedicated message broker for larger scale). This queue acts as a buffer, potentially running on a separate thread/process to decouple the event emission from consumption. Synchronization mechanisms (like `asyncio.Lock` or `threading.Lock` if using separate threads) will be used to ensure safe access to shared data within the event handling process.
    3.  **AppOrchestrator Event Handling**: The `AppOrchestrator` actively listens to this `Event Queue`. When it consumes an event, it translates the internal `Engine` event into a message suitable for external clients.
    4.  **WebSocket Notification**: The `AppOrchestrator` then calls the `API Gateway`'s `WebSocketManager` to broadcast this update to all connected frontend clients subscribed to the specific `run_id`.

**Key Architectural Components:**

*   **`AppOrchestrator`**: A new, dedicated service layer (`app_orchestrator.py`) responsible for:
    *   Translating API requests into `Engine` commands.
    *   Initiating `Engine` runs asynchronously.
    *   Querying run status from the database.
    *   Acting as the primary handler for `Engine`-emitted events, bridging them to the `API Gateway`'s `WebSocketManager`.
*   **`Event Queue`**: An in-memory (e.g., `asyncio.Queue`) or external (e.g., Redis Pub/Sub) queue used by the `Engine` to emit events and by the `AppOrchestrator` to consume them, providing asynchronous buffering and decoupling. Synchronization mechanisms (like `asyncio.Lock` or `threading.Lock` if using separate threads) will be used to ensure safe access to shared data within the event handling process.
*   **`Telemetry Node`**: Remains within the `Engine`'s LangGraph flow, directly called by the `Orchestrator` after critical steps to ensure persistent storage of `ArenaState` in the database. Its role is purely persistence, without knowledge of external APIs or events.