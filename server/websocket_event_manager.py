
"""
Refined WebSocket Event Emissions

Ensures WebSocket events are emitted correctly for manual wait states and turn updates.
"""

import asyncio
from typing import Dict, Any, List, Optional

from server.websocket.socketio_manager import SocketIOManager
from server.database.manual_operations import get_manual_ops
from server.database.connection import get_db
from server.run_manager import RunExecutor, RunStatus
from engine.state_schema import RoutingSignals


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
            'timeout_seconds': executor.graph_config.attack_node_config.max_attempts_per_turn if executor.graph_config.attack_node_config else 60,
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

    # Add specific data based on node type
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


# --- Integration Points ---

# These functions should be called from the relevant components:
# 1. In RunExecutor._handle_manual_wait: Call emit_manual_wait_events
# 2. In RunExecutor._run_loop: After state update from manual input, call emit_resumption_event
# 3. In ManualAttackNode.execute: If adding a waiting turn, call emit_turn_update_events(..., node_name='attack')
# 4. In ManualAttackNode.execute (after defence/eval): Call emit_turn_update_events(..., node_name='defence'/'eval')

# We need to ensure that the executor instance and session_id are available where these functions are called.

# NOTE: The actual modifications to RunExecutor and nodes are needed to trigger these emissions.

