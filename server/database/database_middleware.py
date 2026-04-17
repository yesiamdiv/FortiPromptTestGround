"""
Database Middleware

Persists execution data to MongoDB.
"""

from typing import Dict, Any
from middlewares.base import BaseMiddleware
from server.database.connection import get_db
from datetime import datetime


class DatabaseMiddleware(BaseMiddleware):
    """
    Middleware that persists run data to MongoDB.
    
    Saves:
    - Run metadata (before/after)
    - Execution steps (attack, defence, eval)
    - Final results
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
    
    async def before_run(self, initial_state, config, run_id):
        """Create run document in database"""
        db = get_db()
        if not db:
            print("Warning: Database not connected, skipping persistence")
            return
        
        try:
            strategy = config["configurable"]["strategy"]
            initial_payload = initial_state.get("initial_payload", {})
            
            run_doc = {
                "run_id": run_id,
                "status": "running",
                "strategy": strategy.name,
                "started_at": initial_state.get("start_time"),
                "intent": initial_payload.get("intent", "unknown"),
                "target": initial_payload.get("target"),
                "user_id": initial_payload.get("user_id"),
                "session_id": initial_payload.get("session_id"),
                "tags": initial_payload.get("tags", []),
                "description": initial_payload.get("description"),
                "total_attempts": 0,
                "successful_attempts": 0
            }
            
            await db.runs.insert_one(run_doc)
            
        except Exception as e:
            print(f"[DB Middleware] Error in before_run: {e}")
    
    async def after_step(self, step_data, run_id):
        """Save step data to database"""
        db = get_db()
        if not db:
            return
        
        # Self-filtering: only save relevant nodes
        if not step_data:
            return
        
        node_name = list(step_data.keys())[0]
        node_output = step_data[node_name]
        
        try:
            # Save attack steps
            if node_name == "attack" and self.config.get("save_attacks"):
                await self._save_attack_step(db, run_id, node_output)
            
            # Save defence steps
            elif node_name == "defence" and self.config.get("save_defences"):
                await self._save_defence_step(db, run_id, node_output)
            
            # Save evaluation steps
            elif node_name == "eval" and self.config.get("save_evaluations"):
                await self._save_eval_step(db, run_id, node_output)
            
        except Exception as e:
            print(f"[DB Middleware] Error in after_step: {e}")
    
    async def after_run(self, final_state, run_id):
        """Update run document with final results"""
        db = get_db()
        if not db:
            return
        
        try:
            context = final_state.get("strategy_context", {})
            current_turn = final_state.get("current_turn", {})
            
            update = {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.utcnow().isoformat(),
                    "total_attempts": context.get("attempt_count", 0),
                    "routing_signal": final_state.get("routing_signal")
                }
            }
            
            # Add final evaluation if present
            if current_turn.get("evaluation"):
                eval_result = current_turn["evaluation"]
                update["$set"]["final_score"] = eval_result.get_score()
                update["$set"]["final_category"] = eval_result.get_category()
                
                if eval_result.is_success():
                    update["$inc"] = {"successful_attempts": 1}
            
            await db.runs.update_one(
                {"run_id": run_id},
                update
            )
            
        except Exception as e:
            print(f"[DB Middleware] Error in after_run: {e}")
    
    async def on_error(self, error, run_id, step_data=None):
        """Mark run as failed in database"""
        db = get_db()
        if not db:
            return
        
        try:
            await db.runs.update_one(
                {"run_id": run_id},
                {
                    "$set": {
                        "status": "failed",
                        "completed_at": datetime.utcnow().isoformat(),
                        "error": str(error),
                        "error_details": {
                            "type": type(error).__name__,
                            "message": str(error)
                        }
                    }
                }
            )
        except Exception as e:
            print(f"[DB Middleware] Error in on_error: {e}")
    
    async def _save_attack_step(self, db, run_id, node_output):
        """Save attack step to database"""
        turn = node_output.get("current_turn", {})
        attack = turn.get("attack")
        
        if not attack:
            return
        
        step_doc = {
            "run_id": run_id,
            "turn_id": turn.get("turn_id"),
            "node": "attack",
            "timestamp": turn.get("timestamp"),
            "attack": attack.to_dict()
        }
        
        await db.steps.insert_one(step_doc)
    
    async def _save_defence_step(self, db, run_id, node_output):
        """Save defence step to database"""
        turn = node_output.get("current_turn", {})
        defence = turn.get("defence")
        
        if not defence:
            return
        
        step_doc = {
            "run_id": run_id,
            "turn_id": turn.get("turn_id"),
            "node": "defence",
            "timestamp": turn.get("timestamp"),
            "defence": defence.to_dict()
        }
        
        await db.steps.insert_one(step_doc)
    
    async def _save_eval_step(self, db, run_id, node_output):
        """Save evaluation step to database"""
        turn = node_output.get("current_turn", {})
        evaluation = turn.get("evaluation")
        attack = turn.get("attack")
        defence = turn.get("defence")
        
        if not evaluation:
            return
        
        # Save to steps collection
        step_doc = {
            "run_id": run_id,
            "turn_id": turn.get("turn_id"),
            "node": "eval",
            "timestamp": turn.get("timestamp"),
            "evaluation": evaluation.to_dict()
        }
        
        await db.steps.insert_one(step_doc)
        
        # Also save to evaluations collection for easier querying
        eval_doc = {
            "run_id": run_id,
            "turn_id": turn.get("turn_id"),
            "timestamp": turn.get("timestamp"),
            "score": evaluation.get_score(),
            "success": evaluation.is_success(),
            "category": evaluation.get_category(),
            "reasoning": evaluation.get_reasoning(),
            **evaluation.metadata
        }
        
        # Add attack and defence context
        if attack:
            eval_doc["attack_text"] = attack.to_string()
        if defence:
            eval_doc["defence_text"] = defence.get_text()
            eval_doc["was_blocked"] = defence.was_blocked()
        
        await db.evaluations.insert_one(eval_doc)
