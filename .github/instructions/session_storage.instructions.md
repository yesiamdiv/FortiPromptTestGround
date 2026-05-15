# Session Storage Instructions

## Purpose

This module is responsible for persisting the results of the attack generation and defense testing processes. It acts as the primary data store, managing data for individual "runs" which can encompass both attack and defense testing.

## Key Responsibilities

*   **Data Persistence**: Store all generated data, including attack prompts, responses, evaluation results, and any associated metadata. This data is organized within "runs."
*   **"Runs" Management**: Implement a system to manage multiple runs, ensuring data for each run is isolated and accessible. Each run can contain both attack and defense testing data.
*   **Direct Integration with Orchestration**: Data generated during a run (by attackers, defenders, evaluators) should be directly fed into this storage module for immediate and safe persistence.
*   **Configuration**: Allow configuration for storing data in different backends (e.g., local files, database).
*   **Data Retrieval**: Provide methods to retrieve all data associated with a specific run, which will be used for display on the frontend and by other modules (e.g., evaluation systems).
*   **Primary Storage**: This module serves as the main storage device, replacing reliance on in-memory storage for critical data.

## Context and References

*   **Core Session Storage Files**: `alat-sessions/src/session_manager.py` and `alat-sessions/src/persistence/storage.py`.
*   **Data Flow**: Data will be passed directly from `engine/src/core/orchestrator.py` and other components involved in a run.
*   **Shared State**: The `ArenaState` (defined in `engine/src/core/state.py`) will contain the data to be stored, and this module will be responsible for its persistent representation.
*   **Project Architecture**: Refer to `engine/.github/copilot-instructions.md` for overall data flow and architectural guidelines.

## Working Directory

*   `AgenticLLMAdversarialTestbed/alat-sessions/`
*   `AgenticLLMAdversarialTestbed/engine/` (for integration points with Orchestrator and other modules)