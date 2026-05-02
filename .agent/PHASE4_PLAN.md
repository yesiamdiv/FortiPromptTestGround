
# Phase 4: API/WebSocket Updates and Frontend Integration Considerations

## Objective:
Enhance the user experience and real-time feedback mechanisms by refining API interactions and WebSocket events, particularly for manual attack flows and overall run progress.

## Tasks:

1.  **Refine WebSocket Events:**
    *   **Manual Wait Signaling:**
        *   **`manual_input_required` Event:** Ensure this event is broadcast when a run enters a manual wait state. It should include details like `run_id`, `session_id`, `input_type` (e.g., 'attack_prompt'), and `timeout_seconds`.
        *   **`run_paused_for_input` Event:** Potentially broadcast when the executor is actively paused waiting for input.
        *   **`manual_input_received` Event:** Broadcast when user input is successfully processed by the API, signaling the run's resumption.
    *   **Session/Turn Updates:**
        *   **`manual_session_created`:** Ensure this event is broadcast when a new manual session is initiated.
        *   **`manual_turn_added`:** Broadcast when a new turn (attack or defense) is added to a session.
        *   **`manual_evaluation_complete`:** Broadcast after evaluation of a manual turn.
        *   **`manual_session_saved`:** Broadcast when a session is saved.
        *   **`manual_session_deleted`:** Broadcast when a session is deleted.
    *   **General Run Events:** Review and update existing WebSocket events (`run_started`, `run_completed`, `run_error`, etc.) to include session or turn context where relevant.

2.  **Frontend Integration Considerations (for user interaction):
    *   **Listen to Manual Wait Events:** The frontend should listen for `manual_input_required` and `run_paused_for_input` events.
    *   **Display Input Interface:** Upon receiving these events, the UI should present a chat-like interface for the user to enter prompts.
    *   **Send Manual Input:** The frontend will send the user's prompt via a POST request to `/runs/{runId}/manual-prompt`.
    *   **Update UI:** Listen for `manual_input_received`, `manual_turn_added`, `manual_defense_response`, `manual_evaluation_complete`, and `manual_session_saved`/`deleted` events to update the chat history and session status in real-time.
    *   **Display Run Progress:** Use existing events like `run_progress`, `run_completed`, `run_error` to show the overall status of the run.

3.  **API Refinements (if needed):
    *   Consider endpoints for fetching historical session data if not already covered by `GET /runs/{run_id}/manual/sessions/{session_id}`.
    *   Ensure API responses include relevant information for frontend updates.

## Current Status:

Phase 3 is now complete with the integration of manual session management and core API/backend logic.

## Next Steps:

Proceed with implementing the refined WebSocket events and outlining the necessary frontend interactions for Phase 4. This will provide the complete interactive experience for manual attack scenarios. 
