---
## Goal

The user wants to refactor the codebase for cleaning and improving the architecture. The main objective is to decouple components, clarify responsibilities, and establish a cleaner flow, especially concerning manual run execution.

## Instructions

- The user wants to divide the application into a "frame" (core structure) and "pieces" (functional components).
- Key problems identified include:
    1. Run Executor and Run Manager are overloaded with manual flow logic.
    2. Graph Builder has mode-specific (manual/automatic) edges and routing logic.
    3. Ambiguity exists around where graph streaming (`astream`) and middleware management should reside.
    4. Data models need to correctly represent sessions and their relationship with runs, especially for manual interactions.
    5. Middleware should be exclusively responsible for persistence and event handling.
- **Revised Core Principles:**
    *   Manual runs should be stateless request-response cycles.
    *   The `Strategy` object should dictate graph flow (looping vs. single iteration) and routing.
    *   `RunExecutor`/`RunManager` should be unaware of manual vs. automatic modes.
    *   `WorkflowEngine` orchestrates `astream` and middleware invocation.
    *   `GraphBuilder` constructs the graph and injects middleware via a factory or itself.
    *   Middleware handles persistence and broadcasting exclusively.
- **Clarification:** The user explicitly stated that all code related to *manual input*, *manual attacks*, and *live manual sessions* within the execution flow must be removed. The `ManualTurn` and `ManualSession` data models should be retained in `models_v2.py` for data storage purposes, but not for live execution control.

## Discoveries

*   **`astream` Usage:** LangGraph's `astream` feature is used in `engine/workflow_engine.py` and `server/run_manager.py` to iterate through the graph's execution steps and allow middleware interception.
*   **Current Middleware Injection:** Middleware is passed to `WorkflowEngine` during its initialization. The selection mechanism needs refinement.
*   **`RunExecutor`'s Manual Logic:** `RunExecutor` in `server/run_manager.py` previously handled manual wait states and signaling (`_manual_input_event`), which has now been removed.
*   **Graph Builder Divergence:** `engine/graph_builder.py` previously defined different graph structures and routing logic for manual vs. automatic modes. The manual-specific logic has been removed, unifying the graph construction for automatic execution.
*   **Data Model Structure:** `models_v2.py` defines core models (`AttackData`, `DefenceData`, `EvaluationData`, `RunModel`), and consolidated manual interaction models (`ManualTurn`, `ManualSession`). These models are now normalized and reference each other via IDs, with manual-specific execution logic removed.

## Accomplished

*   **Analysis:** Codebase analyzed for state management, database models, workflow engine, graph builder, and run manager logic.
*   **Documentation:** `CLEANING_CODEBASE_TASK.md` updated to reflect refactoring, including the removal of manual input handling and model normalization.
*   **Model Refactoring:** `models_v2.py` refactored to consolidate manual models, normalize references, and remove manual input handling fields. `RunModel` and `ManualTurn` were cleaned.
*   **Codebase Refactoring:** Manual-specific logic and routing removed from `engine/workflow_engine.py` (minor cleanup), `engine/graph_builder.py`, and `server/run_manager.py`.
*   **File Cleanup:** `manual_models.py` was deleted.
*   **Commit:** Changes related to model and code refactoring were committed.

**Work In Progress:** None.

**Work Left:**
*   Final review of all removed and modified code to ensure no manual input/execution logic remains.
*   Confirm that `ManualTurn` and `ManualSession` models are correctly used for data storage and not for execution flow control.

## Relevant files / directories

*   **Modified:**
    *   `engine/workflow_engine.py` (minor cleanup)
    *   `engine/graph_builder.py`
    *   `server/run_manager.py`
    *   `server/database/models_v2.py`
    *   `CLEANING_CODEBASE_TASK.md`
*   **Deleted:**
    *   `server/database/manual_models.py`
*   **Relevant Directories:**
    *   `.worktrees/v2/engine/`
    *   `.worktrees/v2/server/database/`
    *   `.worktrees/v2/server/`
---
