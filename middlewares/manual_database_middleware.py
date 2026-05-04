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
        if db is None:
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
                # Expecting session_id from payload for manual turns.
                # If missing, it indicates an issue in the API call or payload structure.
                raise ValueError("Manual run requires a 'session_id' in the payload for manual turn processing.")
            
            # Attempt to fetch the last turn for state hydration
            last_manual_turn = await db_ops.get_last_manual_turn_for_session(session_id)
            
            strategy_context = initial_state.get("strategy_context", {})
            if last_manual_turn:
                print(f"  🔄 Hydrating state from last turn {last_manual_turn.turn_id} for session {session_id}")
                # Hydrate strategy_context history from the last manual turn
                history = [last_manual_turn.attack_prompt] if last_manual_turn.attack_prompt else []
                # Ensure history is accumulated if previous turns exist
                if last_manual_turn.index > 0: # This assumes history is not directly stored but reconstructed
                    # Fetching all turns to build history would be better for complex states
                    # For now, using last turn's prompt as a basic history item.
                    # A more robust solution would involve fetching all previous turns for the session.
                    pass

                strategy_context["history"] = history
                strategy_context["iteration_count"] = last_manual_turn.index + 1
            else:
                print(f"  ✨ Starting new turn for session {session_id} (no prior turns found)")
                # If no prior turns, ensure history and iteration count are initialized
                strategy_context["history"] = []
                strategy_context["iteration_count"] = 0
            
            # Ensure session_id is in strategy_context for subsequent access
            strategy_context["session_id"] = session_id
            strategy_context["max_turns"] = self.config.get("max_turns", 100)

            initial_state["strategy_context"] = strategy_context

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

            # Run creation is handled by the API; here we just ensure the run status is idle if it's the start of a manual sequence.
            # RunManager will handle the state transitions based on signals.
            print(f"📝 Manual run processing turn. Run ID: {run_id}, Session ID: {session_id}, Strategy: {strategy_name}")
            
        except ValueError as e: # Catch specific error for missing session_id
            print(f"[ManualDatabaseMiddleware] Configuration Error in before_run: {e}")
            # Update run status to failed if critical config is missing
            await db_ops.update_run(run_id, {"status": "failed", "error": str(e)})
        except Exception as e:
            print(f"[ManualDatabaseMiddleware] Unexpected Error in before_run: {e}")
            await db_ops.update_run(run_id, {"status": "failed", "error": str(e)})

    async def after_step(self, step_data, run_id):
        db = get_db()
        if db is None:
            return
        
        if not step_data:
            return
        
        node_name = list(step_data.keys())[0]
        node_output = step_data[node_name]
        
        try:
            db_ops = get_db_ops(db)
            
            context = node_output.get("strategy_context", {})
            iteration = context.get("iteration_count", 0) 
            
            # Retrieve session_id and turn_id from context or node_output
            session_id = context.get("session_id")
            current_turn_id = node_output.get("current_turn", {}).get("turn_id")
            
            if not session_id or not current_turn_id:
                print(f"[ManualDatabaseMiddleware] Warning: session_id or turn_id missing in after_step for {node_name}. Cannot save turn data.")
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
        if db is None:
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
                print(f"[ManualDatabaseMiddleware] Error: session_id missing in final_state for run {run_id}. Cannot update session.")
                # Attempt fallback to get from run_id if needed, but ideally it should be in state.
                session_id = await db_ops.get_session_id_for_run(run_id) # This might need a dedicated db_ops method
                if not session_id:
                    print(f"[ManualDatabaseMiddleware] Critical Error: Could not retrieve session_id for run {run_id}. State checkpoint may not be saved correctly.")
                    return

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
        if db is None:
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
