"""
Database Middleware - Refactored

Uses server/database/operations.py for actual database logic.
Middleware only orchestrates - doesn't implement database operations.

Saves to separate collections: attacks, defences, evaluations.
"""

from typing import Dict, Any
from middlewares.base import BaseMiddleware
from server.database.connection import get_db
from server.database.operations import get_db_ops


class DatabaseMiddlewareV2(BaseMiddleware):
    """
    Refactored middleware using separate collections.
    
    Collections:
    - runs: Run metadata
    - attacks: Individual attack prompts
    - defences: Individual defence responses
    - evaluations: Individual evaluation results
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize database middleware.
        
        Args:
            config: Configuration including:
                - save_attacks: Whether to save attack data (default: True)
                - save_defences: Whether to save defence data (default: True)
                - save_evaluations: Whether to save evaluation data (default: True)
        """
        default_config = {
            "save_attacks": True,
            "save_defences": True,
            "save_evaluations": True
        }
        
        if config:
            default_config.update(config)
        
        super().__init__(default_config)
        self._iteration_counters = {}  # Track iteration numbers per run
    
    async def before_run(self, initial_state, config, run_id):
        """Create run document in database"""
        db = get_db()
        if not db:
            print("⚠️  Database not connected, skipping persistence")
            return
        
        try:
            db_ops = get_db_ops(db)
            strategy = config["configurable"]["strategy"]
            payload = initial_state.get("payload", {})
            
            # Initialize iteration counter for this run
            self._iteration_counters[run_id] = 0
            
            run_data = {
                "run_id": run_id,
                "name": payload.get("name", f"Run {run_id[:8]}"),
                "status": "running",
                "description": payload.get("description", ""),
                "strategy": strategy.name,
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
            print(f"[DB Middleware] Error in before_run: {e}")
    
    async def after_step(self, step_data, run_id):
        """Save step data to appropriate collection"""
        db = get_db()
        if not db:
            return
        
        if not step_data:
            return
        
        node_name = list(step_data.keys())[0]
        node_output = step_data[node_name]
        
        try:
            db_ops = get_db_ops(db)
            
            # Get current iteration number
            iteration = self._iteration_counters.get(run_id, 0)
            
            # Save based on node type
            if node_name == "attack" and self.config.get("save_attacks"):
                await self._save_attack(db_ops, run_id, iteration, node_output)
                # Increment iteration counter after attack
                self._iteration_counters[run_id] = iteration + 1
            
            elif node_name == "defence" and self.config.get("save_defences"):
                await self._save_defence(db_ops, run_id, iteration, node_output)
            
            elif node_name == "eval" and self.config.get("save_evaluations"):
                await self._save_evaluation(db_ops, run_id, iteration, node_output)
            
        except Exception as e:
            print(f"[DB Middleware] Error in after_step: {e}")
    
    async def after_run(self, final_state, run_id):
        """Update run with final results"""
        db = get_db()
        if not db:
            return
        
        try:
            db_ops = get_db_ops(db)
            current_turn = final_state.get("current_turn", {})
            
            # Get final scores
            final_score = None
            if current_turn.get("evaluation"):
                final_score = current_turn["evaluation"].get_score()
            
            # Get best score from strategy context
            context = final_state.get("strategy_context", {})
            best_score = context.get("best_score")
            
            # Mark as completed
            await db_ops.mark_run_completed(
                run_id,
                final_score=final_score,
                best_score=best_score
            )
            
            # Clean up iteration counter
            self._iteration_counters.pop(run_id, None)
            
            print(f"✅ Run completed in database: {run_id}")
            
        except Exception as e:
            print(f"[DB Middleware] Error in after_run: {e}")
    
    async def on_error(self, error, run_id, step_data=None):
        """Mark run as failed"""
        db = get_db()
        if not db:
            return
        
        try:
            db_ops = get_db_ops(db)
            await db_ops.mark_run_failed(run_id, str(error))
            
            # Clean up iteration counter
            self._iteration_counters.pop(run_id, None)
            
            print(f"❌ Run failed in database: {run_id}")
            
        except Exception as e:
            print(f"[DB Middleware] Error in on_error: {e}")
    
    async def _save_attack(self, db_ops, run_id, iteration, node_output):
        """Save attack to attacks collection"""
        turn = node_output.get("current_turn", {})
        attack = turn.get("attack")
        
        if not attack:
            return
        
        await db_ops.save_attack(
            run_id=run_id,
            index=iteration,
            turn_id=turn.get("turn_id", f"turn_{iteration}"),
            prompt=attack.to_string(),
            metadata=attack.metadata
        )
        
        print(f"  💾 Attack saved (iteration {iteration})")
    
    async def _save_defence(self, db_ops, run_id, iteration, node_output):
        """Save defence to defences collection"""
        turn = node_output.get("current_turn", {})
        defence = turn.get("defence")
        
        if not defence:
            return
        
        await db_ops.save_defence(
            run_id=run_id,
            index=iteration,
            turn_id=turn.get("turn_id", f"turn_{iteration}"),
            response=defence.get_text(),
            status_code=defence.status_code,
            was_blocked=defence.was_blocked(),
            metadata=defence.metadata
        )
        
        print(f"  💾 Defence saved (iteration {iteration})")
    
    async def _save_evaluation(self, db_ops, run_id, iteration, node_output):
        """Save evaluation to evaluations collection"""
        turn = node_output.get("current_turn", {})
        evaluation = turn.get("evaluation")
        
        if not evaluation:
            return
        
        await db_ops.save_evaluation(
            run_id=run_id,
            index=iteration,
            turn_id=turn.get("turn_id", f"turn_{iteration}"),
            score=evaluation.get_score(),
            success=evaluation.is_success(),
            category=evaluation.get_category(),
            feedback=evaluation.get_reasoning(),
            metadata=evaluation.metadata
        )
        
        print(f"  💾 Evaluation saved (iteration {iteration})")