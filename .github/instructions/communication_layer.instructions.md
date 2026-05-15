# Communication Layer Instructions

## Purpose

This module is responsible for handling all communication between the frontend and the backend. It will manage incoming API requests for attack generation and maintain WebSocket connections for real-time updates.

## Key Responsibilities

*   **API Endpoints**: Define and implement API endpoints for initiating attack generation requests from the frontend.
*   **WebSocket Server**: Establish and manage WebSocket connections to send real-time progress, results, and feedback from the backend to the frontend. This includes managing rooms/channels for broadcasting updates.
*   **Message Formatting**: Define clear message formats for API requests, WebSocket events (e.g., `attack_progress`, `attack_complete`, `error`), and responses.


## Context and References

*   **Frontend Integration**: Refer to `TestingAndTrainingInterface/src/services/api.ts` and `TestingAndTrainingInterface/src/services/webSocketService.ts` for frontend implementation details and expected communication patterns.
*   **Backend Orchestration**: The data flow will be passed to `engine/src/core/orchestrator.py`.
*   **Shared State**: Data passed between modules should adhere to the `ArenaState` structure defined in `engine/src/core/state.py` also to the models in `db/models.py`.
*   **WebSocket Implementation**: Consider using libraries like Socket.IO for managing WebSocket connections, including concepts like rooms for targeted communication.

## Working Directory

*   Primary focus: `AgenticLLMAdversarialTestbed/api_gateway/` for implementing the communication layer.
*   Frontend integration: `TestingAndTrainingInterface/`.