---
## Goal

The user wants to refactor the codebase for cleaning and improving the architecture. The main objective is to decouple components, clarify responsibilities, and establish a cleaner flow, especially concerning manual run execution.

## Instructions

- The application is divided into a "frame" (core structure) and "pieces" (functional components).
- **Frame:** `WorkflowEngine`, `RunManager`, `RunExecutor`, `GraphBuilder` (core orchestration, state management, graph construction).
- **Pieces:** Nodes, Middleware, Strategies (functional components).
- **Refactoring Focus:**
    1. **Remove Manual Execution Logic:** Eliminate code related to live manual input, pauses, and sessions from the execution flow.
    2. **Simplify Configuration:** Centralize strategy retrieval and configuration passing, removing redundancies.
    3. **Type Safety:** Utilize `SystemState` for state management throughout the graph.
    4. **Clean Node Implementations:** Ensure nodes correctly interact with `SystemState`, strategy, and use simplified config access.

## Discoveries & Accomplishments

*   **Frame Refactoring Complete:**
    *   **Database Models:** `models_v2.py` consolidated and normalized. `manual_models.py` removed. Core models preserved, manual interaction models normalized with reference IDs.
    *   **Workflow Engine:** Fixed state merging bugs, properly handles `astream`, middleware, and uses `SystemState` typing.
    *   **Graph Builder:** Unified routing, removed manual flow logic, renamed router node to `router`, correctly injects strategy instance into router config, and uses `SystemState` typing.
    *   **Run Manager/Executor:** Removed all manual input/control logic. Correctly handles configuration fetching and payload passing. Correctly delegates execution to `WorkflowEngine`. Simplified status management. Added dynamic middleware setup based on execution mode (though now simplified to base middlewares).
    *   **Type Safety:** `SystemState` is now consistently used across `WorkflowEngine`, `GraphBuilder`, and Nodes.

*   **Pieces Refactoring (Nodes):**
    *   **`manual_attack_node.py`:** Removed, as manual input handling is eliminated from the execution flow.
    *   **`strategy_router_node.py`:** Refactored into `router_node.py`. Now delegates solely to `strategy.route(state)` and accesses strategy from `self.config`.
    *   **`nodes/default_nodes.py`:** Updated `DefaultInitNode` to call `strategy.initialize()`. Updated `DefaultRouterNode` (now `RouterNode`) to use `strategy.route()` and delegate correctly. Registered `RouterNode` under "router".
    *   **`LLMAttackNode`:** Updated to use `runtime_config` and access strategy via `self.config`.
    *   **`HTTPDefenceNode`, `EnsembleDefenceNode`, `ServerEvalNode`, `LLMEvalNode`:** Updated to use `runtime_config` in their `execute` methods.

**Work In Progress:** None.

**Work Left:**
*   **Middleware Refinement:** Review and potentially refactor middleware implementations (`LoggingMiddleware`, `DatabaseMiddlewareV2`) to ensure they correctly interact with `SystemState` and the refined configuration.
*   **Strategy Implementation:** Fully implement `initialize()` and `route()` methods for specific strategies (e.g., `DefaultStrategy`, `IterativeImprovementStrategy`) to utilize `SystemState` and simplified config.
*   **Node Implementations:** Ensure all nodes correctly read from and write to `SystemState['current_turn']` and `SystemState['strategy_context']` based on their specific functions.
*   **Server/API Layer:** Address the server and API endpoint structure and access. This includes how manual runs (if any remain for data logging purposes) are handled at the API level.

## Relevant files / directories

*   **Modified:**
    *   `engine/workflow_engine.py`
    *   `engine/graph_builder.py`
    *   `server/run_manager.py`
    *   `server/database/models_v2.py`
    *   `nodes/base.py`
    *   `nodes/default_nodes.py`
    *   `nodes/router_node.py`
    *   `nodes/llm_attack_node.py`
    *   `nodes/http_defence_node.py`
    *   `nodes/ensemble_defence_node.py`
    *   `nodes/server_eval_node.py`
    *   `nodes/llm_eval_node.py`
*   **Deleted:**
    *   `nodes/manual_attack_node.py`
    *   `nodes/strategy_router_node.py`
    *   `server/database/manual_models.py`
*   **Relevant Directories:**
    *   `.worktrees/v2/engine/`
    *   `.worktrees/v2/server/database/`
    *   `.worktrees/v2/server/`
    *   `.worktrees/v2/nodes/`
    *   `.worktrees/v2/strategies/`
---
