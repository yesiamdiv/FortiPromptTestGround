"""
Manual Database Middleware

Handles saving data and state during manual runs.
"""

from typing import Dict, Any
from middlewares.base import BaseMiddleware
from server.database.connection import get_db
from server.database.operations import get_db_ops
from engine.state_schema import SystemState, RoutingSignals
import uuid # For generating turn_id if not present


class ManualDatabaseMiddleware(BaseMiddleware):
    """
    Database middleware for manual runs.
    
    Manages state hydration, session/turn creation, and state persistence.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {
            "save_attacks": True,
            "save_defences": True,
            "save_evaluations": True
        }
        if config:
            default_config.update(config)
        super().__init__(default_config)

    async def before_run(self, initial_state: SystemState, config: Dict[str, Any], run_id: str):
        db = get_db()
        if not db:
            print("⚠️  Database not connected, skipping persistence")
            return
        
        try:
            db_ops = get_db_ops(db)
            strategy_config = initial_state.get("config", {}).get("strategy_config", {})
            strategy_name = strategy_config.get("strategy_name", "unknown_strategy")
            payload = initial_state.get("payload", {})
            
            # --- Session and Turn Management ---
            session_id = payload.get("session_id")
            if not session_id:
                # If no session_id in payload, this is the first turn of a new session.
                # The API layer should ideally create the session and pass ID, but middleware can handle initial creation if needed.
                # For now, we'll expect API to pass it. If not, raise error.
                raise ValueError("Manual run requires a 'session_id' in the payload.")
            
            # Attempt to fetch the last turn for state hydration
            last_manual_turn = await db_ops.get_last_manual_turn_for_session(session_id)
            
            if last_manual_turn:
                print(f"  🔄 Hydrating state from last turn {last_manual_turn.turn_id} for session {session_id}")
                # Hydrate strategy_context history from the last manual turn
                if 'strategy_context' not in initial_state or not initial_state['strategy_context']:
                    initial_state['strategy_context'] = {}
                
                # Assuming manual_turn data stores accumulated history or can reconstruct it
                # For now, let's assume the last turn's attack prompt is the full history up to that point for simplicity
                # In a real scenario, you'd fetch all turns for the session and build the history list
                history = [last_manual_turn.attack_prompt] if last_manual_turn.attack_prompt else []
                initial_state['strategy_context']['history'] = history
                initial_state['strategy_context']['iteration_count'] = last_manual_turn.index + 1
                # Other context hydration as needed
                
            else:
                print(f"  ✨ Starting new turn for session {session_id} (no prior turns found)")
                # If no prior turns, ensure history and iteration count are initialized
                if 'strategy_context' not in initial_state or not initial_state['strategy_context']:
                    initial_state['strategy_context'] = {}
                initial_state['strategy_context']['history'] = []
                initial_state['strategy_context']['iteration_count'] = 0
            
            # Create a new manual_turn entry for the current execution cycle
            current_turn_id = f"turn_{uuid.uuid4().hex[:8]}"
            initial_state["current_turn"] = {"turn_id": current_turn_id} # Inject new turn_id into state
            initial_state["session_id"] = session_id # Ensure session_id is in state for after_run

            await db_ops.create_manual_turn(
                session_id=session_id,
                turn_id=current_turn_id,
                run_id=run_id, # Link to the overall run
                index=initial_state['strategy_context']['iteration_count']
            )
            print(f"  ➡️ Created new manual turn {current_turn_id} for session {session_id}")

            # Run creation is handled by the API, so no need to create run document here.
            # The run status is also managed by RunManager based on signals.
            print(f"📝 Manual run starting. Run ID: {run_id}, Session ID: {session_id}, Strategy: {strategy_name}")
            
        except Exception as e:
            print(f"[ManualDatabaseMiddleware] Error in before_run: {e}")
            # On error, ensure run status is updated to failed
            await db_ops.update_run(run_id, {"status": "failed"})

    async def after_step(self, step_data, run_id):
        db = get_db()
        if not db:
            return
        
        if not step_data:
            return
        
        node_name = list(step_data.keys())[0]
        node_output = step_data[node_name]
        
        try:
            db_ops = get_db_ops(db)
            
            context = node_output.get("strategy_context", {})
            iteration = context.get("iteration_count", 0) 
            
            # Retrieve session_id and turn_id from node_output or context
            session_id = node_output.get("session_id", initial_state.get("session_id")) # Try from node_output first
            current_turn_id = node_output.get("current_turn", {}).get("turn_id")
            
            if not session_id or not current_turn_id:
                print(f"[ManualDatabaseMiddleware] Warning: session_id or turn_id missing in after_step for {node_name}")
                return # Cannot save without these IDs

            if node_name == "attack" and self.config.get("save_attacks"):
                await self._save_attack(db_ops, run_id, session_id, iteration, node_output, current_turn_id)
            
            elif node_name == "defence" and self.config.get("save_defences"):
                await self._save_defence(db_ops, run_id, session_id, iteration, node_output, current_turn_id)
            
            elif node_name == "eval" and self.config.get("save_evaluations"):
                await self._save_evaluation(db_ops, run_id, session_id, iteration, node_output, current_turn_id)
            
        except Exception as e:
            print(f"[ManualDatabaseMiddleware] Error in after_step: {e}")

    async def after_run(self, final_state: SystemState, run_id: str):
        db = get_db()
        if not db:
            return
        
        try:
            db_ops = get_db_ops(db)
            current_turn_data = final_state.get("current_turn", {})
            
            final_score = None
            if current_turn_data.get("evaluation"):
                final_score = current_turn_data["evaluation"].get_score()
            
            context = final_state.get("strategy_context", {})
            best_score = context.get("best_score")
            
            # Get session_id from final_state (injected in before_run)
            session_id = final_state.get("session_id")
            if not session_id:
                print(f"[ManualDatabaseMiddleware] Error: session_id missing in final_state for run {run_id}")
                return # Cannot save without session_id

            # Update the ManualSession with the final state checkpoint
            await db_ops.update_manual_session_state(
                session_id=session_id,
                run_id=run_id,
                state_checkpoint=final_state,  # Save the entire state
                final_score=final_score,
                best_score=best_score
            )
            
            # Set run status to IDLE, indicating it's waiting for user input
            await db_ops.update_run(run_id, {"status": "idle"})
            print(f"✅ Manual run turn completed, state saved, and set to IDLE: {run_id} (Session: {session_id})")
            
        except Exception as e:
            print(f"[ManualDatabaseMiddleware] Error in after_run: {e}")
    
    async def on_error(self, error, run_id, step_data=None):
        db = get_db()
        if not db:
            return
        
        try:
            db_ops = get_db_ops(db)
            await db_ops.mark_run_failed(run_id, str(error))
            print(f"❌ Manual run failed in database: {run_id}")
            
        except Exception as e:
            print(f"[ManualDatabaseMiddleware] Error in on_error: {e}")
    
    async def _save_attack(self, db_ops, run_id, session_id, iteration, node_output, turn_id):
        turn = node_output.get("current_turn", {})
        attack = turn.get("attack")
        
        if not attack:
            return
        
        await db_ops.update_manual_turn_data(
            session_id=session_id,
            turn_id=turn_id,
            attack_prompt=attack.to_string(),
            attack_metadata=attack.metadata,
            turn_index=iteration # Ensure turn_index is updated
        )
        print(f"  💾 Attack saved to turn {turn_id} (session {session_id})")
    
    async def _save_defence(self, db_ops, run_id, session_id, iteration, node_output, turn_id):
        turn = node_output.get("current_turn", {})
        defence = turn.get("defence")
        
        if not defence:
            return
        
        await db_ops.update_manual_turn_data(
            session_id=session_id,
            turn_id=turn_id,
            defence_response=defence.get_text(),
            defence_status_code=defence.status_code,
            defence_was_blocked=defence.was_blocked(),
            defence_metadata=defence.metadata,
            turn_index=iteration
        )
        print(f"  💾 Defence saved to turn {turn_id} (session {session_id})")
    
    async def _save_evaluation(self, db_ops, run_id, session_id, iteration, node_output, turn_id):
        turn = node_output.get("current_turn", {})
        evaluation = turn.get("evaluation")
        
        if not evaluation:
            return
        
        await db_ops.update_manual_turn_data(
            session_id=session_id,
            turn_id=turn_id,
            evaluation_score=evaluation.get_score(),
            evaluation_success=evaluation.is_success(),
            evaluation_category=evaluation.get_category(),
            evaluation_feedback=evaluation.get_reasoning(),
            evaluation_metadata=evaluation.metadata,
            turn_index=iteration
        )
        print(f"  💾 Evaluation saved to turn {turn_id} (session {session_id})")
