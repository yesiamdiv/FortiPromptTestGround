# API Endpoints and WebSocket Events Documentation

This document outlines the REST API endpoints and WebSocket events for the Adversarial Testing Engine, designed to support both automated and manual human-in-the-loop testing workflows.

## 1. API Endpoints

All API endpoints are prefixed with `/api/v1`.

### 1.1 Run Management

#### `POST /runs`
*   **Description:** Creates a new adversarial run. This initializes a run record in the database but does not start execution immediately. The `graph_config` determines if the run is `manual` or `automatic`.
*   **Method:** `POST`
*   **Request Body (`CreateRunRequest`):**
    ```json
    {
        "name": "string",
        "description": "Optional detailed description for the run.",
        "graph_config": { /* GraphConfig object, defines topology and strategy */ },
        "payload": { /* Initial payload for the run, e.g., global runtime_config */ }
    }
    ```
*   **Responses (`RunResponse`):**
    *   `201 Created`: `{"run_id": "string", "status": "idle", "message": "Run created successfully."}`
    *   `500 Internal Server Error`: `{"detail": "Failed to create run: ..."}`

#### `PATCH /runs/{run_id}`
*   **Description:** Updates configuration for an existing run (e.g., name, description, or strategy parameters within `graph_config`). This allows dynamic adjustment of run settings before or during idle states.
*   **Method:** `PATCH`
*   **Path Parameters:**
    *   `run_id` (string): The ID of the run to update.
*   **Request Body (`UpdateRunRequest`):**
    ```json
    {
        "name": "Optional new name",
        "description": "Optional new description",
        "graph_config": { /* Optional new GraphConfig object, e.g., with updated strategy_params */ }
    }
    ```
*   **Responses (`RunDetailsResponse`):**
    *   `200 OK`: `RunDetailsResponse` object (reflecting updated run details)
    *   `404 Not Found`: `{"detail": "Run with ID ... not found."}`
    *   `500 Internal Server Error`: `{"detail": "Failed to update run ...: ..."}`

#### `POST /runs/{run_id}/start`
*   **Description:** Starts or resumes an existing adversarial run. For `automatic` runs, this initiates the continuous loop. For `manual` runs, this initiates the first turn or resumes from an `idle` state after user input.
*   **Method:** `POST`
*   **Path Parameters:**
    *   `run_id` (string): The ID of the run to start.
*   **Request Body (Optional `payload`):**
    ```json
    { 
        "prompt": "User's initial prompt for manual run", 
        "session_id": "optional_session_id_for_manual_resume",
        "runtime_config": { /* Dynamic runtime overrides */ }
    }
    ```
*   **Responses (`RunResponse`):**
    *   `200 OK`: `{"run_id": "string", "status": "running"|"idle", "message": "Run started successfully"}` (Status will reflect the new IDLE state after turn completion for manual runs)
    *   `400 Bad Request`: `{"detail": "Run is already running" | "Cannot start run ... in status: ..."}`
    *   `404 Not Found`: `{"detail": "Run with ID ... not found"}`
    *   `500 Internal Server Error`: `{"detail": "Failed to start run: ..."}`

#### `POST /runs/{run_id}/stop`
*   **Description:** Stops a currently running adversarial run.
*   **Method:** `POST`
*   **Path Parameters:**
    *   `run_id` (string): The ID of the run to stop.
*   **Responses (`RunResponse`):**
    *   `200 OK`: `{"run_id": "string", "status": "stopped"}`
    *   `404 Not Found`: `{"detail": "Run ... not active or executor not found"}`
    *   `500 Internal Server Error`: `{"detail": "Failed to stop run: ..."}`

#### `GET /runs`
*   **Description:** Retrieves a list of all adversarial runs.
*   **Method:** `GET`
*   **Responses (`ListRunsResponse`):**
    *   `200 OK`: `{"runs": [...]}` (List of `RunModel` objects)
    *   `500 Internal Server Error`: `{"detail": "Failed to list runs: ..."}`

#### `GET /runs/{run_id}`
*   **Description:** Retrieves detailed information about a specific adversarial run.
*   **Method:** `GET`
*   **Path Parameters:**
    *   `run_id` (string): The ID of the run to retrieve.
*   **Responses (`RunDetailsResponse`):**
    *   `200 OK`: `RunDetailsResponse` object
    *   `404 Not Found`: `{"detail": "Run with ID ... not found."}`
    *   `500 Internal Server Error`: `{"detail": "Failed to get run details: ..."}`

#### `GET /strategies`
*   **Description:** Lists all available attack strategies and their JSON configuration schemas. This allows the frontend to dynamically build forms for strategy configuration.
*   **Method:** `GET`
*   **Responses (`ListStrategiesResponse`):**
    *   `200 OK`: `{"strategies": [{"strategy_name": "string", "schema_definition": {}}]}`
    *   `500 Internal Server Error`: `{"detail": "Failed to list strategies: ..."}`

### 1.2 Manual Run Sessions & Turns

These endpoints are prefixed with `/api/v1` and are nested under `/runs/{run_id}`.

#### `POST /runs/{run_id}/sessions`
*   **Description:** Creates a new manual interaction session within a given run. This is the entry point for a human-in-the-loop chat. If `initial_payload` is provided, it can be used to kick off the first turn.
*   **Method:** `POST`
*   **Path Parameters:**
    *   `run_id` (string): The ID of the parent run.
*   **Request Body (`CreateManualSessionRequest`):**
    ```json
    {
        "name": "string",
        "description": "Optional description for the session.",
        "initial_payload": { /* Initial payload for the first turn (e.g., user's first prompt). Can contain runtime_config. */ }
    }
    ```
*   **Responses (`ManualSessionResponse`):**
    *   `201 Created`: `ManualSessionResponse` object
    *   `400 Bad Request`: `{"detail": "Run is not configured for manual sessions."}`
    *   `404 Not Found`: `{"detail": "Run with ID ... not found."}`
    *   `500 Internal Server Error`: `{"detail": "Failed to create manual session: ..."}`

#### `POST /runs/{run_id}/sessions/{session_id}/manual_turn`
*   **Description:** Submits user input (e.g., an attack prompt) for a manual turn within a session. This resumes the manual run's execution for one cycle (Attack -> Defence -> Eval).
*   **Method:** `POST`
*   **Path Parameters:**
    *   `run_id` (string): The ID of the parent run.
    *   `session_id` (string): The ID of the manual session.
*   **Request Body (`SubmitManualTurnRequest`):**
    ```json
    {
        "prompt": "The user's input/prompt for this manual turn.",
        "runtime_config": { /* Dynamic runtime overrides for this specific turn. */ }
    }
    ```
*   **Responses (`RunResponse`):**
    *   `200 OK`: `{"run_id": "string", "status": "idle", "message": "Run started successfully"}` (Status will reflect the new IDLE state after turn completion)
    *   `404 Not Found`: `{"detail": "Manual session ... not found for run ..."}`
    *   `500 Internal Server Error`: `{"detail": "Failed to submit manual turn: ..."}`

#### `GET /runs/{run_id}/sessions/{session_id}`
*   **Description:** Retrieves detailed information about a specific manual session.
*   **Method:** `GET`
*   **Path Parameters:**
    *   `run_id` (string): The ID of the parent run.
    *   `session_id` (string): The ID of the manual session.
*   **Responses (`ManualSessionResponse`):**
    *   `200 OK`: `ManualSessionResponse` object
    *   `404 Not Found`: `{"detail": "Manual session ... not found for run ..."}`
    *   `500 Internal Server Error`: `{"detail": "Failed to get manual session details: ..."}`

#### `GET /runs/{run_id}/sessions/{session_id}/history`
*   **Description:** Retrieves the complete history of turns for a manual session, including detailed attack, defense, and evaluation data for each turn.
*   **Method:** `GET`
*   **Path Parameters:**
    *   `run_id` (string): The ID of the parent run.
    *   `session_id` (string): The ID of the manual session.
*   **Responses (`ManualTurnHistoryResponse`):**
    *   `200 OK`: `{"session": ManualSession, "turns": [ManualTurnResponse, ...]}`
    *   `404 Not Found`: `{"detail": "Manual session ... not found for run ..."}`
    *   `500 Internal Server Error`: `{"detail": "Failed to get manual turn history: ..."}`

### 1.3 Provider Discovery

#### `GET /providers`
*   **Description:** Returns a list of all registered LLM providers (e.g., "ollama", "openai", "gemini"). This allows the frontend to dynamically populate dropdowns for provider selection.
*   **Method:** `GET`
*   **Responses (`ListProvidersResponse`):**
    *   `200 OK`: `{"providers": [{"name": "string"}]}`
    *   `500 Internal Server Error`: `{"detail": "Failed to list providers: ..."}`

### 1.4 Node Discovery

#### `GET /nodes/attack`
*   **Description:** Lists available attack node types and their configuration schemas. This enables the frontend to dynamically build forms for configuring attack nodes.
*   **Method:** `GET`
*   **Responses (`ListNodeSchemasResponse`):**
    *   `200 OK`: `{"nodes": [{"node_type": "attack", "node_name": "string", "schema_definition": {}}]}`
    *   `500 Internal Server Error`: `{"detail": "Failed to list attack nodes: ..."}`

#### `GET /nodes/defense`
*   **Description:** Lists available defense node types and their configuration schemas. This enables the frontend to dynamically build forms for configuring defense nodes.
*   **Method:** `GET`
*   **Responses (`ListNodeSchemasResponse`):**
    *   `200 OK`: `{"nodes": [{"node_type": "defense", "node_name": "string", "schema_definition": {}}]}`
    *   `500 Internal Server Error`: `{"detail": "Failed to list defense nodes: ..."}`

#### `GET /nodes/evaluation`
*   **Description:** Lists available evaluation node types and their configuration schemas. This enables the frontend to dynamically build forms for configuring evaluation nodes.
*   **Method:** `GET`
*   **Responses (`ListNodeSchemasResponse`):**
    *   `200 OK`: `{"nodes": [{"node_type": "evaluation", "node_name": "string", "schema_definition": {}}]}`
    *   `500 Internal Server Error`: `{"detail": "Failed to list evaluation nodes: ..."}`

## 2. WebSocket Events

All WebSocket events are broadcast to specific rooms. General run events are broadcast to a `run_id` room. Manual run events are broadcast to a `session_id` room. The `SocketIOManager` manages client connections and rooms.

### 2.1 General Run Events

#### `run_started`
*   **Description:** Signals the beginning of a run's execution.
*   **Broadcast Room:** `run_id`
*   **Payload:**
    ```json
    {
        "type": "run_started",
        "run_id": "string",
        "strategy": "string",
        "intent": "string",
        "target": "string",
        "timestamp": "ISO datetime string",
        "session_id": "optional_string" // Included for manual runs
    }
    ```

#### `run_progress`
*   **Description:** Provides general progress updates for a run, often used for iteration tracking.
*   **Broadcast Room:** `run_id`
*   **Payload:**
    ```json
    {
        "type": "run_progress",
        "run_id": "string",
        "current": "integer",
        "total": "integer",
        "message": "string (e.g., 'Routing: attack')",
        "progress_percent": "float"
    }
    ```

#### `run_completed`
*   **Description:** Signals the successful completion of an *automatic* run.
*   **Broadcast Room:** `run_id`
*   **Payload:**
    ```json
    {
        "type": "run_completed",
        "run_id": "string",
        "total_attempts": "integer",
        "routing_signal": "string (e.g., '__end__')",
        "timestamp": "ISO datetime string",
        "final_evaluation": { /* ... evaluation summary ... */ }
    }
    ```

#### `run_error`
*   **Description:** Signals that an error occurred during a run's execution.
*   **Broadcast Room:** `run_id`
*   **Payload:**
    ```json
    {
        "type": "run_error",
        "run_id": "string",
        "error": "string (error message)",
        "error_type": "string (e.g., 'ValueError')"
    }
    ```

#### `new_run_available`
*   **Description:** Broadcast to *all* connected clients when a new run record is created in the database, allowing UIs to update run lists.
*   **Broadcast Room:** All clients (global emit)
*   **Payload:**
    ```json
    {
        "type": "new_run_available",
        "run_id": "string",
        "run_summary": { // New: Summary of the created run
            "name": "string",
            "strategy": "string",
            "status": "string"
        }
    }
    ```

### 2.2 Manual Run Specific Events

#### `manual_attack_generated`
*   **Description:** Broadcast when an attack prompt has been generated by the strategy within a manual session.
*   **Broadcast Room:** `session_id`
*   **Payload:**
    ```json
    {
        "type": "manual_attack_generated",
        "run_id": "string",
        "session_id": "string",
        "turn_id": "string",
        "index": "integer (iteration/turn number)",
        "attack": { /* AttackData preview/full_text */ }
    }
    ```

#### `manual_defence_response`
*   **Description:** Broadcast when the defense system has processed the attack and returned a response within a manual session.
*   **Broadcast Room:** `session_id`
*   **Payload:**
    ```json
    {
        "type": "manual_defence_response",
        "run_id": "string",
        "session_id": "string",
        "turn_id": "string",
        "index": "integer",
        "defence": { /* DefenceData preview/full_text, status_code, was_blocked */ }
    }
    ```

#### `manual_evaluation_complete`
*   **Description:** Broadcast when the evaluation of the attack and defense response is complete within a manual session.
*   **Broadcast Room:** `session_id`
*   **Payload:**
    ```json
    {
        "type": "manual_evaluation_complete",
        "run_id": "string",
        "session_id": "string",
        "turn_id": "string",
        "index": "integer",
        "evaluation": { /* EvaluationData score, success, reasoning */ }
    }
    ```

#### `manual_turn_completed`
*   **Description:** Signals that a full manual turn cycle (Attack -> Defence -> Eval) has completed.
*   **Broadcast Room:** `session_id`
*   **Payload:**
    ```json
    {
        "type": "manual_turn_completed",
        "run_id": "string",
        "session_id": "string",
        "turn_id": "string",
        "index": "integer"
    }
    ```

#### `run_idle`
*   **Description:** Broadcast after a *manual* run completes one turn, indicating that the system has finished processing and is now `idle`, awaiting the next user input for the session.
*   **Broadcast Room:** `run_id` (or `session_id` depending on `ws_operations.py` implementation, currently in `run_id` for consistency with main run status)
*   **Payload:**
    ```json
    {
        "type": "run_idle",
        "run_id": "string",
        "message": "Awaiting user input for next turn",
        "last_turn_id": "string (ID of the last completed turn)",
        "iteration_count": "integer",
        "session_id": "string" // Included for manual runs
    }
    ```
