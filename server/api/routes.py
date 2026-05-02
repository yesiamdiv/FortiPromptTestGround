
"""
Refined WebSocket Events and API Workflow Considerations

This file outlines the intended WebSocket events and API interactions for enhanced real-time feedback and manual session management.
"""

import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from server.websocket.socketio_manager import SocketIOManager
from server.database.manual_operations import get_manual_ops
from server.database.connection import get_db
from server.run_manager import RunExecutor, RunStatus


async def emit_manual_wait_events(executor: RunExecutor, session_id: str, run_id: str):
    """Emits WebSocket events when a run enters a manual wait state."""
    socketio_manager = get_socketio_manager()
    
    if not socketio_manager:
        print("Warning: Socket.IO manager not initialized. Cannot emit wait events.")
        return

    # Event indicating a manual input is required
    await socketio_manager.broadcast_to_room(
        run_id,
        'manual_input_required',
        {
            'run_id': run_id,
            'session_id': session_id,
            'input_type': executor.current_state.get("manual_input_required", "unknown"),
            'timeout_seconds': executor.graph_config.attack_node_config.max_attempts_per_turn, # Example: using a config value
            'status': 'waiting'
        }
    )

    # Event indicating the run is paused specifically for input
    await socketio_manager.broadcast_to_room(
        run_id,
        'run_paused_for_input',
        {
            'run_id': run_id,
            'session_id': session_id,
            'status': RunStatus.WAITING_INPUT.value
        }
    )


async def emit_resumption_event(run_id: str, session_id: str, turn_id: str):
    """Emits WebSocket event when manual input is received and run resumes."""
    socketio_manager = get_socketio_manager()
    if not socketio_manager:
        print("Warning: Socket.IO manager not initialized. Cannot emit resumption event.")
        return

    await socketio_manager.broadcast_to_room(
        run_id,
        'manual_input_received',
        {
            'run_id': run_id,
            'session_id': session_id,
            'turn_id': turn_id, # The turn that received manual input
            'status': 'processing' # Indicate that it's now processing
        }
    )


async def emit_turn_update_events(run_id: str, session_id: str, turn: Dict[str, Any], node_name: str):
    """Emits WebSocket events for turn updates (attack, defense, eval)."""
    socketio_manager = get_socketio_manager()
    if not socketio_manager:
        return

    event_name = f"manual_{node_name}_update"
    payload = {
        'session_id': session_id,
        'turn_id': turn.get("turn_id"),
        'turn_index': turn.get("turn_index"),
        'timestamp': turn.get("timestamp")
    }

    if node_name == "attack":
        payload.update({
            'attack_prompt': turn.get("attack_prompt"),
            'attack_metadata': turn.get("metadata", {{}})
        })
    elif node_name == "defence":
        payload.update({
            'defense_response': turn.get("defense_response"),
            'was_blocked': turn.get("defense_was_blocked"),
            'status_code': turn.get("defense_status_code"),
            'defense_metadata': turn.get("defense_metadata", {{}})
        })
    elif node_name == "eval":
        payload.update({
            'score': turn.get("eval_score"),
            'success': turn.get("eval_success"),
            'category': turn.get("eval_category"),
            'feedback': turn.get("eval_feedback", ""),
            'eval_metadata': turn.get("metadata", {{}})
        })
    
    await socketio_manager.broadcast_to_room(run_id, event_name, payload)


# --- Refinements to RunExecutor and API Handlers ---

# Modify RunExecutor to integrate WebSocket broadcasts for wait states
# This requires accessing the executor from the API handler.

async def refine_run_executor_for_websockets(executor: "RunExecutor", session_id: str):
    """Inject WebSocket signaling logic into RunExecutor if needed, or ensure it picks up state changes.
    
    The current approach is that ManualAttackNode sets state flags, and RunExecutor monitors them.
    The API then sets the event. WebSocket events should be broadcast when these state changes occur.
    
    We will adjust the `_handle_manual_wait` in RunExecutor to emit WebSocket events.
    """
    pass # Placeholder for potential direct injection or modification if needed.

# We will modify RunExecutor directly to emit WebSocket events when entering/exiting wait states.



# --- API Route Integration --- 
# (These would typically be in server/api/routes.py or a dedicated manual_routes file)

# Assume `router` is an APIRouter instance

def integrate_manual_routes(router):
    """Integrates manual session API routes into the main router.
    This function would be called in server/main.py.
    """
    # Example: Importing and including routes from manual_routes.py
    # from server.api.manual_routes import router as manual_router
    # router.include_router(manual_router, prefix="/api/v1/runs")
    
    # For demonstration, adding the critical manual prompt endpoint here if it wasn't there.
    # NOTE: This is illustrative. Actual integration should be in the main API setup.
    
    @router.post("/runs/{run_id}/manual-prompt", response_model=Dict[str, Any])
    async def provide_manual_prompt(run_id: str, prompt_data: Dict[str, str]):
        """
        Endpoint to provide manual input (e.g., attack prompt) for a paused run.
        This endpoint interacts with manual session management and signals the RunExecutor to resume.
        """
        try:
            run_manager = get_run_manager()
            executor = run_manager.executors.get(run_id)
            
            if not executor:
                raise ValueError(f"Run executor not found for run_id: {run_id}")
            
            # Check if the run is indeed in a manual wait state
            if not executor._manual_wait_active:
                raise RuntimeError(f"Run {run_id} is not in a manual wait state.")
            
            manual_prompt = prompt_data.get("prompt")
            if not manual_prompt:
                raise ValueError("Manual prompt is required in the request body.")

            session_id = executor.current_state.get("session_id")
            if not session_id:
                # Attempt to find an active session if not directly in state
                db = get_db()
                if db:
                    manual_ops = get_manual_ops(db)
                    sessions = await manual_ops.list_sessions(run_id, status='active', limit=1)
                    if sessions:
                        session_id = sessions[0]["session_id"]
                    else:
                        raise ValueError("No active manual session found to associate prompt with.")
                else:
                    raise RuntimeError("Database not connected. Cannot find active session.")
            
            # --- Use manual_ops to add the turn ---
            turn_index = executor.current_state.get("turn_index", 0) # Get index from current state if available
            turn_id = f"{session_id}_turn_{turn_index}"
            
            # Add the user's prompt as a new turn
            await executor.manual_ops.add_turn(
                session_id=session_id,
                turn_id=turn_id,
                turn_index=turn_index,
                role="attacker",
                attack_prompt=manual_prompt,
                metadata={"status": "received_manual_input"}
            )
            
            # --- Update Executor's internal state ---
            updated_attack_payload = create_simple_attack(data=manual_prompt, metadata= {
                "source": "manual_input",
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": session_id,
                "turn_id": turn_id
            })
            
            if executor.current_state:
                executor.current_state["current_turn"]["attack"] = updated_attack_payload
                executor.current_state["manual_wait_active"] = False
                executor.current_state["manual_input_required"] = None
                executor.current_state["routing_signal"] = RoutingSignals.ATTACK
            
            # --- Update Database Record ---
            db = get_db()
            if db:
                db_ops = get_db_ops(db)
                await db_ops.update_run(run_id, {
                    "status": RunStatus.RUNNING.value,
                    "manual_prompt_received_at": datetime.utcnow().isoformat()
                })
                await executor.manual_ops.update_session(session_id, {
                    "status": "active",
                    "turn_count": turn_index + 1
                })

            # --- Signal Executor to Resume ---
            executor._manual_input_event.set()
            executor._manual_wait_active = False
            executor._manual_input_event.clear()

            return {
                "message": "Manual prompt received and execution resumed.",
                "run_id": run_id,
                "session_id": session_id,
                "turn_id": turn_id
            }
            
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))


# --- Integration of other manual routes into main router would happen here ---
# Example:
# from server.api.manual_routes import router as manual_router
# router.include_router(manual_router, prefix="/api/v1/runs")

# --- Placeholder for additional refined WebSocket event logic ---
# The actual WebSocket event emission logic will be integrated into the RunExecutor
# and potentially middleware when specific states are entered/exited.

async def emit_manual_wait_events(executor: RunExecutor, session_id: str):
    """Emits WebSocket events when a run enters a manual wait state."""
    socketio_manager = get_socketio_manager()
    if not socketio_manager:
        print("Warning: Socket.IO manager not initialized. Cannot emit wait events.")
        return

    run_id = executor.run_id
    # Event indicating a manual input is required
    await socketio_manager.broadcast_to_room(
        run_id,
        'manual_input_required',
        {
            'run_id': run_id,
            'session_id': session_id,
            'input_type': executor.current_state.get("manual_input_required", "unknown"),
            'timeout_seconds': executor.graph_config.attack_node_config.max_attempts_per_turn, 
            'status': 'waiting'
        }
    )

    # Event indicating the run is paused specifically for input
    await socketio_manager.broadcast_to_room(
        run_id,
        'run_paused_for_input',
        {
            'run_id': run_id,
            'session_id': session_id,
            'status': RunStatus.WAITING_INPUT.value
        }
    )

async def emit_resumption_event(run_id: str, session_id: str, turn_id: str):
    """Emits WebSocket event when manual input is received and run resumes."""
    socketio_manager = get_socketio_manager()
    if not socketio_manager:
        return

    await socketio_manager.broadcast_to_room(
        run_id,
        'manual_input_received',
        {
            'run_id': run_id,
            'session_id': session_id,
            'turn_id': turn_id,
            'status': 'processing'
        }
    )

# Placeholder for other WebSocket event emissions (e.g., turn updates)
# These would be integrated into the nodes' execute methods or middleware.

