# 🚀 Server Module (The Gateway)

The `server` directory is the external interface of the Agentic LLM Adversarial Testbed. If the `engine` is the brain, the `server` is the nervous system. 

It provides the REST APIs, manages real-time WebSocket streaming, handles database persistence, and safely wraps the LangGraph execution loop in an asynchronous HTTP environment.

---

## 🏛️ Core Architectural Philosophy

The server is built strictly on the principle of **Decoupling**. 

The core `engine` knows **absolutely nothing** about HTTP requests, MongoDB, or WebSockets. It simply takes a state, processes it, and emits updates. The `server` module is responsible for bridging that pure logic to the outside world.

1. **The Middleware Pattern (The Reporters):** Instead of the engine writing to the database directly, the server attaches "Middlewares" (`automatic_database_middleware.py`, `automatic_ws_middleware.py`) to the engine. These act as reporters—watching the engine execute and safely broadcasting or saving the resulting Domain Models.
2. **Asynchronous First:** Every layer of the server (FastAPI, httpx, Motor/MongoDB, Socket.IO) must be strictly asynchronous to ensure long-running LLM calls never block the main thread.
3. **Graceful Degradation:** If a WebSocket disconnects or a database write fails, it must **never** crash the active LangGraph execution.

---

## 📂 Directory Breakdown

### `api/` (The REST Interface)
Contains the FastAPI routes. This is the traditional request/response layer used by the frontend to fetch history, configure new runs, and view available components (fetching from the Engine's Registries).

### `websocket/` (The Live Stream)
Manages the Socket.IO connections. Because adversarial testing takes time (multiple LLM calls), WebSockets are required to stream live execution steps (`run_progress`, `attack_generated`, `evaluation_complete`) back to the UI in real-time.

### `database/` (The Persistence Layer)
Handles all MongoDB connections and CRUD operations. It translates the Engine's strict Pydantic/Dataclass Domain Models into JSON-safe BSON for storage.

### `middlewares/` (The Bridge)
Contains the hooks that attach to the `WorkflowEngine`'s `before_run`, `after_step`, and `after_run` lifecycle events. 
* *Note: Middlewares must strictly read Domain Model properties (e.g., `evaluation.score`, `defence.response_text`) and never rely on outdated getter methods.*

### `run_manager.py` (The Execution Wrapper)
The crucial file that connects a frontend API request to the backend Engine. It reads the database config, creates the `ConfigurableGraphBuilder`, attaches the server middlewares, and kicks off the background task.

---

## 🚦 The "Gold Standard" Rules for Server Interaction

If you are modifying the server routes, database schemas, or webSockets, adhere to these rules:

* **Protect the Engine:** Never pass raw FastAPI Request objects or raw WebSocket contexts down into the `engine`, `nodes`, or `strategies`. 
* **Strict Type Translation:** When receiving a REST payload, use Pydantic models to validate the data *before* passing it to the engine's `runtime_config`.
* **Handle Domain Models:** When extracting data in middlewares to send over WebSockets or to the Database, remember that `current_turn["attack"]` is an `AttackPayload` object, not a dictionary. Use `.to_dict()` or explicit property access.
* **Fire and Forget Execution:** Because Graph Executions can take minutes, the REST API (`/start_run`) must trigger the `RunManager` as a background task and immediately return a `200 OK` to the frontend. All subsequent updates must happen via WebSockets.

---

## 🔧 Future Roadmap / Pending Refactors
* Audit `api/` endpoints to ensure strict Pydantic validation matches the new Engine capabilities.
* Scrub `websocket/` and `middlewares/` to ensure 100% compliance with Domain Model property access (removing legacy `.get_score()` calls).
* Standardize database schemas to perfectly mirror the updated LangGraph `SystemState`.