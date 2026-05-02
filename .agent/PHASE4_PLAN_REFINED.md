
# Phase 4: API/WebSocket Updates and Frontend Integration Considerations

## Objective:
Enhance the user experience and real-time feedback mechanisms by refining API interactions and WebSocket events, particularly for manual attack flows and overall run progress.

## Tasks:

1.  **Refine WebSocket Events:**
    *   **Manual Wait Signaling:**
        *   **`manual_input_required` Event:** Ensure this event is broadcast when a run enters a manual wait state. It should include details like `run_id`, `session_id`, `input_type` (e.g., 'attack_prompt'), and `timeout_seconds`.
        *   **`run_paused_for_input` Event:** Ensure this event is broadcast when the executor is actively paused waiting for input.
        *   **`manual_input_received` Event:** Ensure this event is broadcast when user input is successfully processed by the API, signaling the run's resumption.
    *   **Session/Turn Updates:**
        *   **`manual_session_created`:** Ensure this event is broadcast when a new manual session is initiated via the API.
        *   **`manual_turn_added`:** Ensure this event is broadcast when a new turn (attack, defense, eval) is added to a session via the API or nodes.
        *   **`manual_defense_response`:** Ensure this event is broadcast when a defense response is recorded.
        *   **`manual_evaluation_complete`:** Ensure this event is broadcast when an evaluation is completed for a turn.
        *   **`manual_session_saved`:** Ensure this event is broadcast when a session is saved.
        *   **`manual_session_deleted`:** Ensure this event is broadcast when a session is deleted.
    *   **General Run Events:** Review and update existing WebSocket events (`run_started`, `run_completed`, `run_error`, `run_progress`) to include session or turn context where relevant for a cohesive feed.

2.  **API Workflow for Frontend:**
    *   **`POST /runs/{runId}/manual-prompt` Endpoint:**
        *   Ensure its response clearly indicates success, the received prompt, and any data needed for immediate UI updates (e.g., confirming resumption).
    *   **Session Management APIs:**
        *   Ensure endpoints like `create_session`, `add_turn`, `save_session`, `delete_session`, and `list_sessions` provide clear and useful responses for frontend consumption.
    *   **General API Best Practices:** Adhere to RESTful principles, provide consistent response formats, and implement informative error handling.

3.  **Frontend Interaction (Conceptual):
    *   **Event Listeners:** Frontend must listen for `manual_input_required`, `run_paused_for_input` to display input UI, and for turn/session update events to refresh chat history.
    *   **API Calls:** Trigger API calls for session management and manual prompt submission.
    *   **State Management:** Frontend will manage UI state based on received events and API responses.

## Current Status:

Phase 3 is complete. The backend architecture for dynamic graphs, manual interaction, and session management is established, with core components integrated and tested.

## Next Steps:

Implement the refined WebSocket event emissions and ensure the API responses provide adequate information for frontend integration. This will finalize the backend setup for interactive manual flows.
