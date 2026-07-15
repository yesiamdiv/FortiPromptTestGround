# API Endpoints and WebSocket Events Documentation

This document outlines the REST API endpoints and WebSocket events for the Adversarial Testing Engine, designed to support both automated and manual human-in-the-loop testing workflows.

## 1. API Endpoints

All API endpoints are prefixed with `/api/v1`.

### 1.1 Run Management

#### `POST /runs`
- **Description:** Creates a new adversarial run. This initializes a run record in the database but does not start execution immediately. The `graph_config.graph_type` determines if the run is `automatic`, `manual`, or `batch`.
- **Method:** `POST`
- **Request Body (`CreateRunRequest`):**
  ```json
  {
      "name": "string",
      "description": "Optional detailed description for the run.",
      "config": {
          "graph_type": "automatic",
          "attack_node_config": { "node_type": "llm_attack" },
          "defense_node_config": { "node_type": "heuristic_defense" },
          "evaluation_node_config": { "node_type": "llm_eval" },
          "strategy_config": {
              "strategy_name": "iterative_improvement",
              "strategy_params": {}
          }
      },
      "payload": {}
  }
  ```
- **Responses (`RunResponse`):**
  - `201 Created`: `{"run_id": "string", "status": "idle", "message": "Run created successfully."}`
  - `500 Internal Server Error`: `{"detail": "Failed to create run: ..."}`

#### `PATCH /runs/{run_id}`
- **Description:** Updates configuration for an existing run (e.g., name, description, or strategy/ node parameters).
- **Method:** `PATCH`
- **Path Parameters:**
  - `run_id` (string): The ID of the run to update.
- **Request Body (`UpdateRunRequest`):**
  ```json
  {
      "name": "Optional new name",
      "description": "Optional new description",
      "strategy_params": {}
  }
  ```
- **Responses (`RunDetailsResponse`):**
  - `200 OK`: `RunDetailsResponse` object
  - `404 Not Found`: `{"detail": "Run with ID ... not found."}`

#### `POST /runs/{run_id}/start`
- **Description:** Starts or resumes an existing adversarial run. For `automatic` runs this begins the loop. For `manual` runs this executes one turn.
- **Method:** `POST`
- **Path Parameters:**
  - `run_id` (string): The ID of the run to start.
- **Request Body (optional):**
  ```json
  {
      "prompt": "User's input for manual run",
      "session_id": "optional session for manual resume",
      "runtime_config": {}
  }
  ```
- **Responses (`RunResponse`):**
  - `200 OK`: `{"run_id": "string", "status": "running"|"idle", "message": "Run started successfully"}`
  - `400 Bad Request`: `{"detail": "Run is already running" | "Cannot start run ... in status: ..."}`
  - `404 Not Found`: `{"detail": "Run with ID ... not found"}`

#### `POST /runs/{run_id}/stop`
- **Description:** Stops a currently running adversarial run.
- **Method:** `POST`
- **Path Parameters:**
  - `run_id` (string): The ID of the run to stop.
- **Responses (`RunResponse`):**
  - `200 OK`: `{"run_id": "string", "status": "stopped"}`
  - `404 Not Found`: `{"detail": "Run ... not active or executor not found"}`

#### `GET /runs`
- **Description:** Retrieves a list of all adversarial runs.
- **Method:** `GET`
- **Responses (`ListRunsResponse`):**
  - `200 OK`: `{"runs": [...]}`
  - `500 Internal Server Error`: `{"detail": "Failed to list runs: ..."}`

#### `GET /runs/{run_id}`
- **Description:** Retrieves detailed information about a specific run.
- **Method:** `GET`
- **Path Parameters:**
  - `run_id` (string): The ID of the run.
- **Responses (`RunDetailsResponse`):**
  - `200 OK`: `RunDetailsResponse` object
  - `404 Not Found`: `{"detail": "Run with ID ... not found."}`

#### `DELETE /runs/{run_id}`
- **Description:** Deletes a run and all its associated data.
- **Method:** `DELETE`
- **Path Parameters:**
  - `run_id` (string): The ID of the run to delete.
- **Responses:**
  - `200 OK`: `{"message": "Run deleted successfully"}`
  - `404 Not Found`: `{"detail": "Run with ID ... not found."}`

### 1.2 Statistics

#### `GET /runs/{run_id}/stats`
- **Description:** Returns aggregate statistics for a run, computed live from the attacks/defences/evaluations collections.
- **Method:** `GET`
- **Path Parameters:**
  - `run_id` (string): The ID of the run.
- **Responses:**
  - `200 OK`:
    ```json
    {
        "total_attacks": 42,
        "total_defences": 42,
        "blocked_defences": 30,
        "passed_defences": 12,
        "total_evaluations": 42,
        "breaches": 5,
        "defended": 37,
        "breach_rate": 0.119
    }
    ```
  - `404 Not Found`: `{"detail": "Run ... not found."}`

#### `GET /runs/{run_id}/stats/charts`
- **Description:** Returns declarative chart data for the frontend. Currently provides two pie charts: defence-layer breakdown and evaluation-category breakdown.
- **Method:** `GET`
- **Path Parameters:**
  - `run_id` (string): The ID of the run.
- **Responses:**
  - `200 OK`:
    ```json
    {
        "charts": [
            {
                "id": "defence-layer-breakdown",
                "title": "Blocks by Defence Layer",
                "type": "pie",
                "data": [
                    {"label": "heuristic", "value": 15, "color": "#EF4444"},
                    {"label": "llm", "value": 8, "color": "#F59E0B"}
                ]
            },
            {
                "id": "eval-category-breakdown",
                "title": "Evaluations by Category",
                "type": "pie",
                "data": [
                    {"label": "safe", "value": 37, "color": "#DC2626"},
                    {"label": "jailbreak", "value": 3, "color": "#F59E0B"}
                ]
            }
        ]
    }
    ```
  - `404 Not Found`: `{"detail": "Run ... not found."}`

### 1.3 Run Data (Attacks / Defences / Evaluations)

#### `GET /runs/{run_id}/attacks`
- **Description:** Lists all attack payloads generated during a run.
- **Method:** `GET`
- **Path Parameters:**
  - `run_id` (string): The ID of the run.
- **Responses:**
  - `200 OK`: `{"attacks": [...]}`

#### `GET /runs/{run_id}/defences`
- **Description:** Lists all defence responses recorded during a run.
- **Method:** `GET`
- **Path Parameters:**
  - `run_id` (string): The ID of the run.
- **Responses:**
  - `200 OK`: `{"defences": [...]}`

#### `GET /runs/{run_id}/evaluations`
- **Description:** Lists all evaluations recorded during a run.
- **Method:** `GET`
- **Path Parameters:**
  - `run_id` (string): The ID of the run.
- **Responses:**
  - `200 OK`: `{"evaluations": [...]}`

### 1.4 Sessions & Turns

Endpoints under `/runs/{run_id}/sessions` handle both manual and batch session management.

#### `POST /runs/{run_id}/sessions`
- **Description:** Creates a new interaction session within a run. For manual runs, this is the entry point for a chat session.
- **Method:** `POST`
- **Path Parameters:**
  - `run_id` (string): The ID of the parent run.
- **Request Body (`CreateSessionRequest`):**
  ```json
  {
      "name": "My Session",
      "description": "Optional description",
      "initial_payload": { "prompt": "Hello" }
  }
  ```
- **Responses:**
  - `201 Created`: `Session` object (unified session model)
  - `400 Bad Request`: `{"detail": "Run is not configured for manual sessions."}`
  - `404 Not Found`: `{"detail": "Run with ID ... not found."}`

#### `POST /runs/{run_id}/sessions/{session_id}/manual_turn`
- **Description:** Submits user input for a manual turn within a session. Triggers one Attack → Defence → Eval cycle.
- **Method:** `POST`
- **Path Parameters:**
  - `run_id` (string): The ID of the parent run.
  - `session_id` (string): The ID of the session.
- **Request Body (`SubmitTurnRequest`):**
  ```json
  {
      "prompt": "User's attack prompt",
      "runtime_config": {}
  }
  ```
- **Responses (`SubmitTurnResponse`):**
  - `200 OK`: `{"run_id": "string", "session_id": "string", "turn_id": "pending", "status": "running"}`
  - `404 Not Found`: `{"detail": "Manual session ... not found for run ..."}`

#### `GET /runs/{run_id}/sessions/{session_id}`
- **Description:** Retrieves details of a specific session.
- **Method:** `GET`
- **Path Parameters:**
  - `run_id` (string): The ID of the parent run.
  - `session_id` (string): The ID of the session.
- **Responses:**
  - `200 OK`: `Session` object
  - `404 Not Found`: `{"detail": "Session ... not found for run ..."}`

#### `GET /runs/{run_id}/sessions/{session_id}/history`
- **Description:** Retrieves the complete turn history for a session, including detailed attack/defence/evaluation data for each turn.
- **Method:** `GET`
- **Path Parameters:**
  - `run_id` (string): The ID of the parent run.
  - `session_id` (string): The ID of the session.
- **Responses (`SessionHistoryResponse`):**
  - `200 OK`:
    ```json
    {
        "session": { "...": "..." },
        "turns": [
            {
                "turn_id": "...",
                "attack_data": { "...": "..." },
                "defence_data": { "...": "..." },
                "evaluation_data": { "...": "..." }
            }
        ]
    }
    ```
  - `404 Not Found`: `{"detail": "Session ... not found for run ..."}`

#### `GET /runs/{run_id}/sessions`
- **Description:** Lists all sessions for a run, ordered by creation time.
- **Method:** `GET`
- **Path Parameters:
  - `run_id` (string): The ID of the run.
- **Responses:**
  - `200 OK`: `{"sessions": [...]}`

#### `DELETE /runs/{run_id}/sessions/{session_id}`
- **Description:** Deletes a session and all its turns.
- **Method:** `DELETE`
- **Path Parameters:**
  - `run_id` (string): The ID of the parent run.
  - `session_id` (string): The ID of the session to delete.
- **Responses:**
  - `200 OK`: `{"message": "Session ... deleted successfully"}`
  - `404 Not Found`: `{"detail": "Session ... not found."}`

### 1.5 Discovery

#### `GET /strategies`
- **Description:** Lists all available attack strategies and their JSON configuration schemas.
- **Method:** `GET`
- **Responses (`ListStrategiesResponse`):**
  - `200 OK`: `{"strategies": [{"strategy_name": "string", "schema_definition": {}}]}`

#### `GET /providers`
- **Description:** Lists all registered LLM providers (e.g., "ollama", "openai", "gemini").
- **Method:** `GET`
- **Responses (`ListProvidersResponse`):**
  - `200 OK`: `{"providers": [{"name": "string"}]}`

#### `GET /nodes/attack`
- **Description:** Lists available attack node types and their configuration schemas.
- **Method:** `GET`
- **Responses (`ListNodeSchemasResponse`):**
  - `200 OK`: `{"nodes": [{"node_type": "attack", "node_name": "string", "schema_definition": {}}]}`

#### `GET /nodes/defense`
- **Description:** Lists available defense node types and their configuration schemas.
- **Method:** `GET`
- **Responses (`ListNodeSchemasResponse`):**
  - `200 OK`: `{"nodes": [{"node_type": "defense", "node_name": "string", "schema_definition": {}}]}`

#### `GET /nodes/evaluation`
- **Description:** Lists available evaluation node types and their configuration schemas.
- **Method:** `GET`
- **Responses (`ListNodeSchemasResponse`):**
  - `200 OK`: `{"nodes": [{"node_type": "evaluation", "node_name": "string", "schema_definition": {}}]}`

## 2. WebSocket Events

All WebSocket events use Socket.IO with `transports: ['websocket']` (no HTTP polling). General run events broadcast to a `run_id` room. Manual run events broadcast to a `session_id` room.

### 2.1 Connection Events

#### `connected`
- **Description:** Sent to the client immediately after a successful Socket.IO handshake.
- **Broadcast Room:** Client's own SID
- **Payload:**
  ```json
  {
      "status": "connected",
      "session_id": "socket_sid"
  }
  ```

#### `room_joined`
- **Description:** Confirms the client joined a `run_id` room.
- **Broadcast Room:** Client's own SID
- **Payload:**
  ```json
  {
      "status": "joined",
      "room": "run_id",
      "run_id": "string"
  }
  ```

#### `session_room_joined`
- **Description:** Confirms the client joined a `session_id` room.
- **Broadcast Room:** Client's own SID
- **Payload:**
  ```json
  {
      "status": "joined",
      "room": "session_id",
      "session_id": "string"
  }
  ```

#### `error`
- **Description:** Sent when a client request (join/leave/ping) fails.
- **Broadcast Room:** Client's own SID
- **Payload:**
  ```json
  {
      "message": "error description"
  }
  ```

### 2.2 Automatic Run Events

#### `run_started`
- **Description:** Signals the beginning of a run's execution.
- **Broadcast Room:** `run_id`
- **Payload:**
  ```json
  {
      "type": "run_started",
      "run_id": "string",
      "strategy": "string",
      "intent": "string",
      "target": "string",
      "session_id": "string",
      "timestamp": "ISO datetime"
  }
  ```

#### `attack_generated`
- **Description:** Broadcast when an attack payload has been produced by the strategy.
- **Broadcast Room:** `run_id`
- **Payload:**
  ```json
  {
      "type": "attack_generated",
      "run_id": "string",
      "turn_id": "string",
      "index": 0,
      "attack": {
          "preview": "first 200 chars",
          "full_text": "complete attack text",
          "type": "text|chat|json",
          "metadata": {},
          "timestamp": "ISO datetime"
      }
  }
  ```

#### `defence_response`
- **Description:** Broadcast when the defence node has processed the attack.
- **Broadcast Room:** `run_id`
- **Payload:**
  ```json
  {
      "type": "defence_response",
      "run_id": "string",
      "turn_id": "string",
      "index": 0,
      "defence": {
          "preview": "first 200 chars",
          "full_text": "complete response",
          "status_code": 200,
          "was_blocked": false,
          "metadata": {},
          "timestamp": "ISO datetime"
      }
  }
  ```

#### `evaluation_complete`
- **Description:** Broadcast when the evaluation node has scored the turn.
- **Broadcast Room:** `run_id`
- **Payload:**
  ```json
  {
      "type": "evaluation_complete",
      "run_id": "string",
      "turn_id": "string",
      "index": 0,
      "evaluation": {
          "score": 0.0,
          "success": false,
          "category": "safe",
          "reasoning": "...",
          "summary": "...",
          "metadata": {}
      }
  }
  ```

#### `turn_completed`
- **Description:** Signals that a full automatic turn cycle has finished.
- **Broadcast Room:** `run_id`
- **Payload:**
  ```json
  {
      "type": "turn_completed",
      "run_id": "string",
      "turn_id": "string",
      "index": 0,
      "evaluation": { "score": 0.0, "success": false, "category": "safe" }
  }
  ```

#### `run_progress`
- **Description:** Provides iteration progress updates.
- **Broadcast Room:** `run_id`
- **Payload:**
  ```json
  {
      "type": "run_progress",
      "run_id": "string",
      "current": 1,
      "total": 10,
      "message": "Routing: attack",
      "progress_percent": 10.0
  }
  ```

#### `run_completed`
- **Description:** Signals successful completion of an automatic run.
- **Broadcast Room:** `run_id`
- **Payload:**
  ```json
  {
      "type": "run_completed",
      "run_id": "string",
      "total_attempts": 10,
      "routing_signal": "__end__",
      "timestamp": "ISO datetime",
      "final_evaluation": { "...": "..." }
  }
  ```

#### `run_error`
- **Description:** Signals an error during run execution.
- **Broadcast Room:** `run_id`
- **Payload:**
  ```json
  {
      "type": "run_error",
      "run_id": "string",
      "error": "error message",
      "error_type": "ValueError"
  }
  ```

#### `new_run_available`
- **Description:** Broadcast to all connected clients when a new run is created.
- **Broadcast Room:** All clients (global)
- **Payload:**
  ```json
  {
      "type": "new_run_available",
      "run_id": "string",
      "run_summary": { "name": "string", "strategy": "string", "status": "idle" }
  }
  ```

### 2.3 Manual Run Events

Manual events broadcast to the `session_id` room.

#### `run_idle`
- **Description:** Broadcast after a manual run completes one turn, indicating the system is idle and awaiting the next user input.
- **Broadcast Room:** `run_id`
- **Payload:**
  ```json
  {
      "type": "run_idle",
      "run_id": "string",
      "message": "Awaiting user input for next turn",
      "last_turn_id": "string",
      "iteration_count": 1,
      "session_id": "string"
  }
  ```

#### `manual_attack_generated`
- **Description:** Broadcast when the strategy has produced an attack prompt in a manual session.
- **Broadcast Room:** `session_id`
- **Payload:**
  ```json
  {
      "type": "manual_attack_generated",
      "run_id": "string",
      "session_id": "string",
      "turn_id": "string",
      "index": 0,
      "attack": { "preview": "...", "full_text": "...", "type": "text", "metadata": {} }
  }
  ```

#### `manual_defence_response`
- **Description:** Broadcast when the defence node has responded in a manual session.
- **Broadcast Room:** `session_id`
- **Payload:**
  ```json
  {
      "type": "manual_defence_response",
      "run_id": "string",
      "session_id": "string",
      "turn_id": "string",
      "index": 0,
      "defence": { "preview": "...", "full_text": "...", "status_code": 200, "was_blocked": false }
  }
  ```

#### `manual_evaluation_complete`
- **Description:** Broadcast when evaluation finishes in a manual session.
- **Broadcast Room:** `session_id`
- **Payload:**
  ```json
  {
      "type": "manual_evaluation_complete",
      "run_id": "string",
      "session_id": "string",
      "turn_id": "string",
      "index": 0,
      "evaluation": { "score": 0.0, "success": false, "category": "safe", "reasoning": "...", "summary": "...", "metadata": {} }
  }
  ```

#### `manual_turn_completed`
- **Description:** Signals that a full manual turn cycle has finished.
- **Broadcast Room:** `session_id`
- **Payload:**
  ```json
  {
      "type": "manual_turn_completed",
      "run_id": "string",
      "session_id": "string",
      "turn_id": "string",
      "index": 0
  }
  ```

### 2.4 Client Actions (Emit to Server)

Clients send these events to the server:

#### `join_run`
- **Description:** Subscribe to all events for a given run.
- **Payload:** `{"run_id": "string"}`
- **Response (server emits):** `room_joined` event

#### `leave_run`
- **Description:** Unsubscribe from a run's events.
- **Payload:** `{"run_id": "string"}`
- **Response (server emits):** `room_left` event

#### `join_session`
- **Description:** Subscribe to all events for a specific session.
- **Payload:** `{"session_id": "string"}`
- **Response (server emits):** `session_room_joined` event

#### `ping`
- **Description:** Health-check / keep-alive.
- **Payload:** `{"timestamp": number}`
- **Response (server emits):** `pong` event with the same timestamp
