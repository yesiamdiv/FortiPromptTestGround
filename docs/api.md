# FortiPrompt — API Reference

Base path: `/api/v1`

---

## Runs (`server/api/runs.py`)

### `POST /runs`
Create a new adversarial run. Returns the run record. Does not start execution.

**Request body**
```json
{
  "name": "My red-team run",
  "description": "Optional description",
  "config": {
    "graph_type": "automatic",
    "attack_node_config": { "node_type": "strategy_attack" },
    "defense_node_config": { "node_type": "http_defence", "node_params": { "target_url": "http://..." } },
    "evaluation_node_config": { "node_type": "llm_eval" },
    "strategy_config": {
      "strategy_name": "iterative_improvement",
      "strategy_params": {}
    }
  }
}
```

**Response** `201 RunDetailsResponse`

---

### `PATCH /runs/{run_id}`
Update configuration for an existing idle run (name, description, node params, strategy params).

**Request body** (all fields optional)
```json
{
  "name": "Updated name",
  "strategy_params": { "temperature": 0.9 },
  "attack_node_params": {},
  "defense_node_params": {},
  "evaluation_node_params": {}
}
```

**Response** `200 RunDetailsResponse`

---

### `DELETE /runs/{run_id}`
Delete a run record. Associated attack/defence/evaluation data is not deleted.

**Response** `200 { "message": "<run_id> is deleted" }`

---

### `POST /runs/{run_id}/start`
Start an existing run. For automatic and batch runs, begins the attack/defence/eval loop. For manual runs, initiates the first turn.

**Request body** (optional payload passed to strategy on first turn)
```json
{}
```

**Response** `200 RunResponse`

**Errors**
- `404` — run not found
- `400` — run is not in a startable state

---

### `POST /runs/{run_id}/stop`
Stop a running run gracefully.

**Response** `200 RunResponse`

---

### `GET /runs`
List all runs.

**Response** `200 ListRunsResponse`

---

### `GET /runs/{run_id}`
Get detailed information about a specific run.

**Response** `200 RunDetailsResponse`

**Errors**
- `404` — run not found

---

## Discovery (`server/api/discovery.py`)

### `GET /strategies`
List all registered attack strategies and their configuration schemas.

**Response** `200 ListStrategiesResponse`

---

### `GET /strategies/{strategy_name}/schema`
Get the configuration schema for a specific strategy.

**Response** `200 StrategySchemaResponse`

**Errors**
- `404` — strategy not found

---

### `GET /providers`
List all registered LLM providers.

**Response** `200 ListProvidersResponse`

---

### `GET /nodes/attack`
List registered attack node types and their schemas.

**Response** `200 ListNodeSchemasResponse`

---

### `GET /nodes/defense`
List registered defense node types and their schemas.

**Response** `200 ListNodeSchemasResponse`

---

### `GET /nodes/evaluation`
List registered evaluation node types and their schemas.

**Response** `200 ListNodeSchemasResponse`

---

### `GET /discovery/nodes`
List all node types with full descriptions (richer than the category-filtered endpoints above).

**Response** `200 List[NodeInfo]`

---

### `GET /discovery/nodes/{node_type}`
Get description and schema for a specific node type.

**Response** `200 NodeInfo`

---

### `GET /discovery/strategies`
List all strategies with full descriptions.

**Response** `200 List[StrategyInfo]`

---

### `GET /discovery/strategies/{strategy_name}`
Get description and schema for a specific strategy.

**Response** `200 StrategyInfo`

---

## Run Data (`server/api/data.py`)

### `GET /runs/{run_id}/attacks`
Get all attack records for a run.

**Response** `200 { "attacks": [AttackData, ...] }`

---

### `GET /runs/{run_id}/defences`
Get all defence records for a run.

**Response** `200 { "defences": [DefenceData, ...] }`

---

### `GET /runs/{run_id}/evaluations`
Get all evaluation records for a run.

**Response** `200 { "evaluations": [EvaluationData, ...] }`

---

### `GET /runs/{run_id}/stats`
Get computed statistics for a run.

**Response**
```json
{
  "run_id": "run_abc123",
  "total_attacks": 10,
  "total_defences": 10,
  "total_evaluations": 10,
  "success_rate": 0.4,
  "blocked_rate": 0.6,
  "average_score": 0.52,
  "best_score": 0.95,
  "categories": { "harmful": 5, "misinformation": 3, "copyright": 2 }
}
```

---

## Manual Sessions (`server/api/manual_routes.py`)

Manual runs allow a human (or external system) to submit attack prompts turn-by-turn.

### `POST /runs/{run_id}/sessions`
Create a new manual session within a run. The run must have `graph_type: "manual"`.

**Request body**
```json
{
  "name": "Session 1",
  "description": "Optional",
  "initial_payload": { "prompt": "Optional first message" }
}
```

**Response** `201 ManualSessionResponse`

---

### `POST /runs/{run_id}/sessions/{session_id}/manual_turn`
Submit the next attack turn for a manual session. Blocks until the defence and evaluation nodes complete.

**Request body**
```json
{
  "prompt": "Ignore all previous instructions...",
  "metadata": {}
}
```

**Response** `200 SubmitManualTurnResponse` — includes attack, defence, and evaluation data for the turn.

---

### `GET /runs/{run_id}/sessions/{session_id}`
Get session details including current status.

**Response** `200 ManualSessionResponse`

---

### `GET /runs/{run_id}/sessions/{session_id}/history`
Get the full turn history for a session, ordered by turn index.

**Response** `200 ManualTurnHistoryResponse`

---

### `GET /runs/{run_id}/sessions`
List all sessions for a run.

**Response** `200 List[ManualSessionResponse]`

---

### `DELETE /runs/{run_id}/sessions/{session_id}`
Delete a session and its turns.

**Response** `200 { "message": "..." }`

---

## WebSocket Events (Socket.IO)

Real-time progress is broadcast over Socket.IO at `/socket.io`. Connect and listen on the `run_{run_id}` room.

| Event | Payload | When |
|---|---|---|
| `attack_generated` | `{ run_id, turn_id, prompt, metadata }` | After attack node |
| `defence_received` | `{ run_id, turn_id, response, was_blocked }` | After defence node |
| `evaluation_complete` | `{ run_id, turn_id, score, success, category }` | After eval node |
| `run_complete` | `{ run_id, status }` | Run finishes |
| `run_error` | `{ run_id, error }` | Run fails |

See `docs/SOCKETIO_CLIENT_GUIDE.md` for client connection examples.

---

## Phase 2 — Session / Turn Endpoints

These endpoints expose the unified Session/Turn data model introduced in Phase 2.
All run types (automatic, batch, manual, multiturn) write to these collections.

### `GET /runs/{run_id}/sessions`

List all sessions for a run, ordered by creation time.

**Response**
```json
{
  "sessions": [
    {
      "session_id": "sess_run_abc123",
      "run_id": "run_abc123",
      "name": "My Run",
      "run_type": "automatic",
      "status": "completed",
      "total_turns": 5,
      "successful_turns": 3,
      "created_at": "2024-01-01T12:00:00",
      "updated_at": "2024-01-01T12:05:00"
    }
  ]
}
```

---

### `GET /runs/{run_id}/sessions/{session_id}`

Get session detail plus computed stats.

**Response**
```json
{
  "session": { ... },
  "stats": {
    "total_turns": 5,
    "turns_with_evaluation": 5
  }
}
```

---

### `GET /runs/{run_id}/sessions/{session_id}/turns`

List all turns for a session with linked attack / defence / evaluation data resolved inline.

**Response**
```json
{
  "turns": [
    {
      "turn_id": "turn_abc",
      "session_id": "sess_run_abc123",
      "index": 0,
      "attack_data_id": "66a1b2c3d4e5f6...",
      "defence_data_id": "66a1b2c3d4e5f7...",
      "evaluation_data_id": "66a1b2c3d4e5f8...",
      "attack": { "prompt": "...", ... },
      "defence": { "response": "...", ... },
      "evaluation": { "score": 0.85, ... }
    }
  ]
}
```

---

### `GET /runs/{run_id}/sessions/{session_id}/turns/{turn_id}`

Get a single turn with all linked data resolved.

---

## Deprecated Endpoints

The following flat endpoints are kept for backward compatibility but are **deprecated**.
They query the `attacks`, `defences`, and `evaluations` collections directly and do not
expose Session/Turn relationships. Prefer the Session/Turn endpoints above.

- `GET /runs/{run_id}/attacks`
- `GET /runs/{run_id}/defences`
- `GET /runs/{run_id}/evaluations`
