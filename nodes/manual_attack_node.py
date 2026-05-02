
"""
Manual Attack Node - Refined for Session Integration

Integrates with manual_ops for session and turn management.
"""

from typing import Dict, Any
from nodes.base import BaseAdversarialNode
from engine.state_schema import update_turn_data, RoutingSignals
from engine.domain_models import create_simple_attack
from datetime import datetime
import asyncio 

from server.database.manual_operations import get_manual_ops
from server.database.connection import get_db


class ManualAttackNode(BaseAdversarialNode):
    """
    Node for manual attack execution.
    
    Interacts with manual session management to record turns and signals a wait state.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {"wait_timeout": 60.0} # Default wait timeout in seconds
        if config:
            default_config.update(config)
        super().__init__(default_config)
        self.manual_ops = None # Will be initialized when needed

    async def execute(self, state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        current_turn_data_from_state = state.get("current_turn", {{}})
        session_id = current_turn_data_from_state.get("session_id")
        run_id = state.get("run_id")
        
        if not session_id or not run_id:
            print(f"ManualAttackNode Warning: Missing session_id or run_id in state for {self.run_id}. Cannot proceed.")
            return {"routing_signal": RoutingSignals.END}

        # Initialize manual operations if not already done
        if self.manual_ops is None:
            db = get_db()
            if not db:
                raise RuntimeError("Database not connected. Cannot initialize manual_ops.")
            self.manual_ops = get_manual_ops(db)

        # Get current session details to determine turn index and check status
        session = await self.manual_ops.get_session(session_id)
        if not session:
            raise ValueError(f"Manual session {session_id} not found for run {run_id}.")
        
        turn_index = session.get("turn_count", 0)
        turn_id = f"{session_id}_turn_{turn_index}"

        # Check if we are already in a manual wait state for this session/run.
        if state.get("manual_wait_active") == True and state.get("routing_signal") == "WAITING_FOR_MANUAL_INPUT":
            print(f"ManualAttackNode: Already waiting for input for session {session_id}. Maintaining signal.")
            return {
                "routing_signal": "WAITING_FOR_MANUAL_INPUT"
            }

        # --- Signal manual wait state and add a placeholder turn ---
        wait_signal_value = "WAITING_FOR_MANUAL_INPUT"
        
        # Update state to indicate manual wait is active
        state["manual_wait_active"] = True
        state["manual_input_required"] = "attack_prompt"
        state["routing_signal"] = wait_signal_value
        
        # Add a placeholder turn to the session indicating we are waiting for user input.
        try:
            turn_metadata = {"run_id": run_id, "session_id": session_id}
            await self.manual_ops.add_turn(
                session_id=session_id,
                turn_id=turn_id,
                turn_index=turn_index,
                role="attacker", 
                attack_prompt="[Waiting for user input...]", 
                metadata=turn_metadata
            )
            print(f"ManualAttackNode: Added waiting turn {turn_id} for session {session_id}.")
        except Exception as e:
            print(f"ManualAttackNode Error: Failed to add waiting turn for session {session_id}: {e}")

        # Update the current_turn data in the state to reflect the waiting status
        updated_turn = update_turn_data(
            current_turn_data,
            node_name="manual_attack",
            attack=create_simple_attack(
                data="Waiting for manual prompt...", 
                metadata= {
                    "wait_signal": wait_signal_value,
                    "timeout_seconds": self.config.get("wait_timeout"),
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "strategy_name": config["configurable"].get("strategy", "unknown").name
                }
            )
        )

        return {
            "current_turn": updated_turn,
            "routing_signal": wait_signal_value
        }

