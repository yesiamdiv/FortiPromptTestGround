# Orchestration and Attack Generation Instructions

## Purpose

The Orchestrator acts as the central control flow manager for the attack generation process. It receives requests from the Communication Layer, directs them to the appropriate Attacker module, and manages the overall execution.

## Key Responsibilities

*   **Request Handling**: Receive attack generation requests (e.g., goal, parameters) from the Communication Layer.
*   **State Management**: Initialize and manage the `ArenaState` for each attack generation run.
*   **Attacker Invocation**: Instantiate and call the appropriate attacker module based on the request.
*   **Flow Control**: Manage the sequence of operations, including passing state to the attacker and receiving results.
*   **Integration with Session Storage**: Pass generated attack data and results to the Session Storage module for persistence.

## Context and References

*   **Core Orchestrator File**: `engine/src/core/orchestrator.py`
*   **Attacker Interface**: `engine/src/core/interfaces.py` (specifically `BaseAttacker`)
*   **Attacker Implementations**: `engine/src/attackers/` directory. Ensure any new attacker modules adhere to the defined interfaces.
*   **Shared State**: `ArenaState` defined in `engine/src/core/state.py` is crucial for passing data.
*   **Project Architecture**: Refer to `engine/.github/copilot-instructions.md` for overall architecture and design decisions.

## Working Directory

*   `AgenticLLMAdversarialTestbed/engine/src/core/`
*   `AgenticLLMAdversarialTestbed/engine/src/attackers/`