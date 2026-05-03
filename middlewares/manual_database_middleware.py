"""
Manual Database Middleware

Handles saving data and state during manual runs.
"""

from typing import Dict, Any
from middlewares.base import BaseMiddleware
from server.database.connection import get_db
from server.database.operations import get_db_ops
from engine.state_schema import SystemState, RoutingSignals


class ManualDatabaseMiddleware(BaseMiddleware):
    """
    Database middleware for manual runs.
    
    Manages pausing, state saving, and resuming.
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
            # CORRECT WAY to access strategy name from initial_state
            strategy_config = initial_state.get("config", {}).get("strategy_config", {})
            strategy_name = strategy_config.get("strategy_name", "unknown_strategy")
            payload = initial_state.get("payload", {})
            
            run_data = {
                "run_id": run_id,
                "name": payload.get("name", f"Run {run_id[:8]}"),
                "status": "running",
                "description": payload.get("description", ""),
                "strategy": strategy_name,
                "components": [],  # TODO: Track components used
                "config": {
                    "global_config": payload.get("config", {}),
                    "attack_config": {},
                    "defence_config": {},
                    "evaluation_config": {}
                },
                "started_at": initial_state.get("start_time"),
                "intent": payload.get("intent", "unknown"),
                "target": payload.get("target"),
                "user_id": payload.get("user_id"),
                "session_id": payload.get("session_id"),
                "tags": payload.get("tags", [])
            }
            
            await db_ops.create_run(run_data)
            print(f"📝 Run created in database: {run_id}")
            
        except Exception as e:
            print(f"[ManualDatabaseMiddleware] Error in before_run: {e}")

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
            turn_id = context.get("turn_id", f"turn_{iteration}")

            if node_name == "attack" and self.config.get("save_attacks"):
                await self._save_attack(db_ops, run_id, iteration, node_output, turn_id)
            
            elif node_name == "defence" and self.config.get("save_defences"):
                await self._save_defence(db_ops, run_id, iteration, node_output, turn_id)
            
            elif node_name == "eval" and self.config.get("save_evaluations"):
                await self._save_evaluation(db_ops, run_id, iteration, node_output, turn_id)
            
        except Exception as e:
            print(f"[ManualDatabaseMiddleware] Error in after_step: {e}")

    async def after_run(self, final_state, run_id):
        db = get_db()
        if not db:
            return
        
        try:
            db_ops = get_db_ops(db)
            current_turn = final_state.get("current_turn", {})
            
            final_score = None
            if current_turn.get("evaluation"):
                final_score = current_turn["evaluation"].get_score()
            
            context = final_state.get("strategy_context", {})
            best_score = context.get("best_score")
            
            # For manual runs, mark as paused and save the state checkpoint
            await db_ops.mark_run_paused(
                run_id,
                state_checkpoint=final_state,  # Save the entire state
                final_score=final_score,
                best_score=best_score
            )
            
            print(f"⏸️ Run paused and state saved: {run_id}")
            
        except Exception as e:
            print(f"[ManualDatabaseMiddleware] Error in after_run: {e}")
    
    async def on_error(self, error, run_id, step_data=None):
        db = get_db()
        if not db:
            return
        
        try:
            db_ops = get_db_ops(db)
            await db_ops.mark_run_failed(run_id, str(error))
            print(f"❌ Run failed in database: {run_id}")
            
        except Exception as e:
            print(f"[ManualDatabaseMiddleware] Error in on_error: {e}")
    
    async def _save_attack(self, db_ops, run_id, iteration, node_output, turn_id):
        turn = node_output.get("current_turn", {})
        attack = turn.get("attack")
        
        if not attack:
            return
        
        await db_ops.save_attack(
            run_id=run_id,
            index=iteration,
            turn_id=turn_id,
            prompt=attack.to_string(),
            metadata=attack.metadata
        )
        print(f"  💾 Attack saved (iteration {iteration})")
    
    async def _save_defence(self, db_ops, run_id, iteration, node_output, turn_id):
        turn = node_output.get("current_turn", {})
        defence = turn.get("defence")
        
        if not defence:
            return
        
        await db_ops.save_defence(
            run_id=run_id,
            index=iteration,
            turn_id=turn_id,
            response=defence.get_text(),
            status_code=defence.status_code,
            was_blocked=defence.was_blocked(),
            metadata=defence.metadata
        )
        print(f"  💾 Defence saved (iteration {iteration})")
    
    async def _save_evaluation(self, db_ops, run_id, iteration, node_output, turn_id):
        turn = node_output.get("current_turn", {})
        evaluation = turn.get("evaluation")
        
        if not evaluation:
            return
        
        await db_ops.save_evaluation(
            run_id=run_id,
            index=iteration,
            turn_id=turn_id,
            score=evaluation.get_score(),
            success=evaluation.is_success(),
            category=evaluation.get_category(),
            feedback=evaluation.get_reasoning(),
            metadata=evaluation.metadata
        )
        print(f"  💾 Evaluation saved (iteration {iteration})")
