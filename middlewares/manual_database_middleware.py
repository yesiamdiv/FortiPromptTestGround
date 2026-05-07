"""
Manual Database Middleware

Handles saving data and state during manual runs.
"""

from typing import Dict, Any
from middlewares.base import BaseMiddleware
from server.database.connection import get_db
from server.database.operations import get_db_ops
from engine.debug_utils import debug, tracer, step, warn, err, checkpoint
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
        tracer("ManualDatabaseMiddleware.before_run", run_id=run_id)
        db = get_db()
        if db is None:
            warn("Database not connected, skipping persistence")
            return
        
        try:
            db_ops = get_db_ops(db)
            strategy_config = initial_state.get("config", {}).get("strategy_config", {})
            strategy_name = strategy_config.get("strategy_name", "unknown_strategy")
            payload = initial_state.get("payload", {})
            
            session_id = payload.get("session_id")
            if not session_id:
                err("Missing session_id for manual run")
                raise ValueError("Manual run requires a 'session_id' in the payload for manual turn processing.")
            
            last_manual_turn = await db_ops.get_last_manual_turn_for_session(session_id)
            
            strategy_context = initial_state.get("strategy_context", {})
            if last_manual_turn:
                debug("Hydrating state from last turn", turn=last_manual_turn.turn_id, session=session_id)
                history = [last_manual_turn.attack_prompt] if last_manual_turn.attack_prompt else []
                if last_manual_turn.index > 0:
                    pass

                strategy_context["history"] = history
                strategy_context["iteration_count"] = last_manual_turn.index + 1
            else:
                debug("Starting new turn, no prior turns", session=session_id)
                strategy_context["history"] = []
                strategy_context["iteration_count"] = 0
            
            strategy_context["session_id"] = session_id
            strategy_context["max_turns"] = self.config.get("max_turns", 100)

            initial_state["strategy_context"] = strategy_context

            current_turn_id = f"turn_{uuid.uuid4().hex[:8]}"
            initial_state["current_turn"] = {"turn_id": current_turn_id}
            initial_state["session_id"] = session_id

            await db_ops.create_manual_turn(
                session_id=session_id,
                turn_id=current_turn_id,
                run_id=run_id,
                index=initial_state['strategy_context']['iteration_count']
            )
            step("Manual turn created", turn=current_turn_id, session=session_id)

            debug("Manual run processing", run_id=run_id, session=session_id, strategy=strategy_name)
            
        except ValueError as e:
            err("Configuration error in before_run", error=str(e))
            await db_ops.update_run(run_id, {"status": "failed", "error": str(e)})
        except Exception as e:
            err("Unexpected error in before_run", error=str(e))
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
            
            session_id = context.get("session_id")
            current_turn_id = node_output.get("current_turn", {}).get("turn_id")
            
            if not session_id or not current_turn_id:
                warn("Missing session_id or turn_id in after_step", node=node_name)
                return

            if node_name == "attack" and self.config.get("save_attacks"):
                await self._save_attack(db_ops, run_id, session_id, iteration, node_output, current_turn_id)
            
            elif node_name == "defence" and self.config.get("save_defences"):
                await self._save_defence(db_ops, run_id, session_id, iteration, node_output, current_turn_id)
            
            elif node_name == "eval" and self.config.get("save_evaluations"):
                await self._save_evaluation(db_ops, run_id, session_id, iteration, node_output, current_turn_id)
            
        except Exception as e:
            err("Error in after_step", error=str(e))

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
            
            session_id = final_state.get("session_id")
            if not session_id:
                err("Missing session_id in final_state", run_id=run_id)
                session_id = await db_ops.get_session_id_for_run(run_id)
                if not session_id:
                    err("Could not retrieve session_id for run", run_id=run_id)
                    return

            await db_ops.update_manual_session_state(
                session_id=session_id,
                run_id=run_id,
                state_checkpoint=final_state,
                final_score=final_score,
                best_score=best_score
            )
            
            await db_ops.update_run(run_id, {"status": "idle"})
            step("Manual run turn completed, state saved, set to IDLE", run_id=run_id, session=session_id)
            
        except Exception as e:
            err("Error in after_run", error=str(e))
    
    async def on_error(self, error, run_id, step_data=None):
        db = get_db()
        if db is None:
            return
        
        try:
            db_ops = get_db_ops(db)
            await db_ops.mark_run_failed(run_id, str(error))
            err("Manual run failed in database", run_id=run_id)
            
        except Exception as e:
            err("Error in on_error", error=str(e))
    
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
            turn_index=iteration
        )
        debug("Attack saved", turn=turn_id, session=session_id)
    
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
        debug("Defence saved", turn=turn_id, session=session_id)
    
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
        debug("Evaluation saved", turn=turn_id, session=session_id)
