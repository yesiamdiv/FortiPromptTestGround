# Project Architecture Overview

This document provides a high-level overview of the Adversarial Testing Engine's architecture, detailing its core components, their dependencies, and the primary workflows.

## I. Core Components & Dependencies

1.  **FastAPI Server (`server/main.py`):**
    *   **Description:** The main entry point for the application. Sets up the FastAPI web server, handles application lifespan events (startup/shutdown), configures middleware, and mounts Socket.IO.
    *   **Dependencies:**
        *   `server/api/routes.py` (and other API route files): For defining REST endpoints.
        *   `server/database/connection.py`: For initializing and managing the MongoDB connection.
        *   `server/websocket/socketio_manager.py`: For initializing the Socket.IO server.
        *   `server/run_manager.py`: For initializing the global `RunManager` instance.
        *   `engine/registry.py`: For populating node and strategy registries on startup.
        *   `uvicorn`: ASGI server for running the application.

2.  **Run Manager (`server/run_manager.py`):**
    *   **Description:** Manages the lifecycle of all runs. Acts as a singleton (`get_run_manager`). It holds active `RunExecutor` instances and coordinates their start, pause, resume, and stop operations.
    *   **Dependencies:**
        *   `RunExecutor` (defined in the same file): For managing individual run lifecycles.
        *   `server/database/operations.py` (`get_db_ops`): For database access to retrieve run data.
        *   `server/config.models.py` (`GraphConfig`): For parsing run configurations.
        *   `asyncio`: For managing background tasks (`RunExecutor.task`).

3.  **Run Executor (`server/run_manager.py`):**
    *   **Description:** Manages a single adversarial run. It builds a dynamic graph, instantiates a strategy, and orchestrates the execution loop (`_run_loop`). Handles pausing, resuming, and manual input waits using `asyncio.Event`s.
    *   **Dependencies:**
        *   `engine/graph_builder.py` (`build_dynamic_graph`): To create the run-specific graph.
        *   `engine/registry.py` (`get_strategy_registry`): To get strategy instances.
        *   `engine.workflow_engine.WorkflowEngine`: To execute the graph.
        *   `middlewares`: Instances of `LoggingMiddleware`, `DatabaseMiddlewareV2`, `WebSocketMiddlewareV2` are created per executor.
        *   `server/database.operations.py` (`get_db_ops`): For updating run status in the DB.
        *   `server/websocket.socketio_manager`: For broadcasting events.
        *   `engine.state_schema` (`create_initial_state`): For initializing the graph state.
        *   `server/database/manual_operations.py` (`get_manual_ops`): For manual session interactions.

4.  **Workflow Engine (`engine/workflow_engine.py`):**
    *   **Description:** Orchestrates the execution of the LangGraph (`compiled_graph`). It iterates through steps, triggers middleware, and manages run state.
    *   **Dependencies:**
        *   `langgraph.graph.StateGraph` (external library).
        *   `middlewares`: List of middleware instances to be invoked.
        *   `engine.state_schema`: For state management.

5.  **Graph Builder (`engine/graph_builder.py`):**
    *   **Description:** Dynamically constructs the LangGraph based on `GraphConfig`. It uses registries to instantiate nodes and strategies, defining graph edges and routing logic (including manual wait handling).
    *   **Dependencies:**
        *   `langgraph.graph.StateGraph` (external library).
        *   `engine.registry` (`get_node_registry`, `get_strategy_registry`): To get node factories and strategy classes.
        *   `server.config.models.py` (`GraphConfig`): The blueprint for graph construction.
        *   Specific Node classes (e.g., `ManualAttackNode`, `StrategyRouterNode`): To be instantiated.

6.  **Node Registry (`engine/registry.py`):**
    *   **Description:** Manages factories for nodes, allowing dynamic instantiation based on configuration.
    *   **Dependencies:**
        *   Specific Node classes (e.g., `ManualAttackNode`, `StrategyRouterNode`).

7.  **Strategy Registry (`engine/registry.py`):**
    *   **Description:** Manages strategy classes, allowing dynamic instantiation based on configuration.
    *   **Dependencies:**
        *   Specific Strategy classes (e.g., `DefaultStrategy`, `IterativeImprovementStrategy`).

8.  **Manual Session Management:**
    *   **`server/database/manual_models.py`:** Pydantic models for `ManualSession` and `ManualTurn`.
    *   **`server/database/manual_operations.py`:** CRUD operations for manual sessions/turns.
    *   **`server/api/routes.py` (Manual Routes):** Endpoints for managing sessions, turns, and config.
    *   **Dependencies:**
        *   `server/database/connection.py` (`get_db`): For DB access.
        *   `server/run_manager.py` (`get_run_manager`): To link sessions to runs.
        *   `server/websocket.socketio_manager` (`get_socketio_manager`): For broadcasting session events.
        *   `server/api.schemas`: For request/response models.

9.  **Middlewares (`middlewares/` directory):
    *   **`LoggingMiddleware`:** Logs execution details.
    *   **`DatabaseMiddlewareV2`:** Handles persistence of attacks, defenses, and evaluations.
    *   **`WebSocketMiddlewareV2`:** Handles broadcasting of run progress and step updates.
    *   **Dependencies:** Each middleware depends on specific operational modules (e.g., DB ops, WebSocket ops) and the `WorkflowEngine` for execution context.

10. **Database (`server/database/` directory):
    *   **`connection.py`:** Manages MongoDB connection.
    *   **`operations.py`:** Core CRUD for runs, attacks, defenses, evaluations.
    *   **`manual_operations.py`:** CRUD for manual sessions and turns.
    *   **`models_v2.py`:** Pydantic models for main run data and associated collections.
    *   **`manual_models.py`:** Pydantic models for manual session data.
    *   **Dependencies:** `motor` (async MongoDB driver).

11. **WebSocket (`server/websocket/` directory):
    *   **`socketio_manager.py`:** Manages Socket.IO server instance and room broadcasting.
    *   **Dependencies:** `python-socketio`, `aiohttp`.

## II. Primary Workflows

### A. Server Startup Workflow:

1.  **`server/main.py` (Lifespan Event - Startup)**
    *   Initialize Database connection (`server/database/connection.py`).
    *   Initialize Socket.IO Manager (`server/websocket/socketio_manager.py`).
    *   Initialize Run Manager (`server/run_manager.py`).
    *   **Populate Registries:** Call `register_all_components()` (from `engine/registry.py`) to load node factories and strategy classes.
    *   **Restore Existing Runs:** Load runs from DB, track active ones, and update status (e.g., mark interrupted runs as stopped). Socket.IO rooms are managed.
    *   **Mount API Routers:** Include main, manual, and other API route handlers.
    *   **Mount Socket.IO App:** Mount the Socket.IO application.

### B. Run Creation Workflow:

1.  **API Call:** `POST /api/v1/runs/create` (from `server/api/routes.py`).
2.  **`RunManager.create_run`:**
    *   Validates `GraphConfig` from request.
    *   Calls `db_ops.create_run` to save run metadata and `graph_config` to the database.
    *   Returns run details.
3.  **Database:** `runs` collection updated with new run document.

### C. Run Execution Workflow (Standard Automatic):

1.  **API Call:** `POST /api/v1/runs/{runId}/start`.
2.  **`RunManager.start_run`:**
    *   Retrieves run data (including `GraphConfig`) from DB.
    *   Creates a `RunExecutor` instance, passing `GraphConfig`.
    *   Builds the graph dynamically using `build_dynamic_graph(graph_config)`.
    *   Instantiates strategy and middlewares.
    *   Creates `executor.task` to run `_run_loop`.
3.  **`RunExecutor._run_loop`:**
    *   Initializes state and triggers `before_run` middleware.
    *   Iterates through `graph.astream(initial_state, runtime_config)`:
        *   Checks for `_pause_event` and waits if paused.
        *   Updates `self.current_state` with `step_data`.
        *   Triggers `after_step` middleware.
    *   If `stop_requested`, breaks loop.
    *   If `routing_signal` is `END`, marks run as `COMPLETED`.
    *   Triggers `after_run` middleware.
4.  **Node Execution:** Each node (`attack`, `defence`, `eval`, `strategy_router`) executes its `execute` method.
5.  **Middleware:** `before_run`, `after_step`, `after_run`, `on_error` are invoked at appropriate points.

### D. Manual Attack Workflow:

1.  **Initiation:** Similar to standard run start, but `GraphConfig.graph_type` is set to "manual".
2.  **Graph Construction:** `build_dynamic_graph` creates a graph with `manual_attack` and `strategy_router` nodes and specific edges.
3.  **`ManualAttackNode.execute`:**
    *   Sets `state["manual_wait_active"] = True`, `state["manual_input_required"]`, and `routing_signal = "WAITING_FOR_MANUAL_INPUT"`.
    *   Uses `manual_ops.add_turn` to record the waiting state.
    *   Returns the updated state with the wait signal.
4.  **`StrategyRouterNode.execute`:**
    *   Detects `manual_wait_active` and `WAITING_FOR_MANUAL_INPUT`.
    *   Maintains the `WAITING_FOR_MANUAL_INPUT` signal, keeping the graph at this point.
5.  **`RunExecutor._run_loop`:**
    *   Detects `self._manual_wait_active` (from state).
    *   Sets status to `WAITING_INPUT`.
    *   Calls `emit_manual_wait_events()`.
    *   **Pauses execution by `await self._manual_input_event.wait()`**. 
6.  **External Input:**
    *   **API Call:** `POST /runs/{runId}/manual-prompt`.
    *   **`RunManager.provide_manual_input`:**
        *   Retrieves `RunExecutor`.
        *   Updates `executor.current_state` with the manual prompt and resets wait flags.
        *   Uses `manual_ops` to add the turn to the session.
        *   Updates DB status and session turn count.
        *   **Crucially, calls `executor._manual_input_event.set()` to resume execution.**
        *   Calls `emit_resumption_event()`.
7.  **Resumption:**
    *   `RunExecutor._run_loop` wakes up.
    *   Resets internal flags (`_manual_wait_active`).
    *   Updates status to `RUNNING`.
    *   The graph continues execution from the updated state (e.g., to `defence` node).

### III. Key Dependencies Between Components:

*   **FastAPI Server (`main.py`) -> Run Manager (`run_manager.py`):** Server starts and retrieves the Run Manager singleton.
*   **Run Manager (`run_manager.py`) -> Run Executor (`run_manager.py`):** Manager creates and holds executors.
*   **Run Executor -> Graph Builder (`graph_builder.py`):** Executor uses builder to create the graph based on `GraphConfig`.
*   **Run Executor -> Registries (`engine/registry.py`):** Executor gets strategy instances and node factories from registries.
*   **Run Executor -> Workflow Engine (`workflow_engine.py`):** Executor uses the engine to run the compiled graph.
*   **Workflow Engine -> Middlewares:** Engine invokes middleware methods (`before_run`, `after_step`, etc.).
*   **Middlewares -> Database/WebSocket Ops:** Middlewares use operational modules for persistence and communication.
*   **Nodes (`nodes/`) -> Registries (`engine/registry.py`):** Nodes are registered with the registry.
*   **Nodes -> Strategies (`strategies/`) & Manual Ops (`server/database/manual_operations.py`):** Nodes can depend on strategies for logic and manual nodes interact with manual ops.
*   **API Routes (`server/api/`) -> Run Manager & Manual Ops:** API endpoints call manager/ops for actions.
*   **API (`POST /runs/{runId}/manual-prompt`) -> Run Executor:** API directly signals the executor to resume.
*   **ManualAttackNode -> ManualOps:** Records turns.
*   **RunExecutor (`_handle_manual_wait`, `provide_manual_input`) -> WebSocket Manager:** Emits events.

## IV. Future Considerations (Phase 4 & Beyond):

*   **Frontend Integration:** Developing the UI to consume WebSocket events and interact with API endpoints for a seamless user experience.
*   **Advanced Strategies:** Implementing more complex strategies and ensuring their memory management is robust.
*   **Testing:** Comprehensive unit, integration, and end-to-end tests for all workflows, especially manual interaction and state transitions.
*   **Error Handling & Resilience:** Enhancing robustness for production environments.
*   **Configuration Management:** User-friendly ways to manage run configurations and strategy parameters.
