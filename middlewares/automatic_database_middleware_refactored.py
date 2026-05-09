"""
Refactored Automatic Database Middleware

CHANGES FROM ORIGINAL:
- ✓ Uses strict SystemState typing (not Dict[str, Any])
- ✓ Direct property access (NOT legacy getters)
- ✓ Consistent runtime_config naming
- ✓ Aligned with base.py signature
- ✓ Eliminated dictionary-style state access where possible
"""

from typing import Dict, Any, Optional
from middlewares.base_refactored import BaseMiddleware
from server.database.connection import get_db
from server.database.operations import get_db_ops
from engine.debug_utils import debug, tracer, step, warn, err
from engine.state_schema import SystemState


class AutomaticDatabaseMiddleware(BaseMiddleware):
    """
    Database middleware for automatic runs.
    
    Persists attacks, defences, and evaluations as the graph executes.
    """
    
    def __init__(self, middleware_config: Dict[str, Any] = None):
        default_config = {
            "save_attacks": True,
            "save_defences": True,
            "save_evaluations": True
        }
        if middleware_config:
            default_config.update(middleware_config)
        super().__init__(default_config)

    async def before_run(
        self, 
        state: SystemState, 
        runtime_config: Dict[str, Any], 
        run_id: str
    ) -> None:
        """Log run start - database run record created elsewhere"""
        tracer("AutomaticDatabaseMiddleware.before_run", run_id=run_id)
        
        db = get_db()
        if db is None:
            warn("Database not connected, skipping persistence")
            return
        
        try:
            # Access typed state properties
            config_dict = state.get("config", {})
            strategy_config = config_dict.get("strategy_config", {})
            strategy_name = strategy_config.get("strategy_name", "unknown_strategy")
            
            payload = state.get("payload", {})
            intent = payload.get('intent', 'unknown')
            
            debug("Automatic run starting", strategy=strategy_name, intent=intent)
            
        except Exception as e:
            err("Error in before_run", error=str(e))
    
    async def after_step(
        self, 
        state: SystemState, 
        run_id: str, 
        node_name: Optional[str] = None
    ) -> None:
        """Save step data to database"""
        db = get_db()
        if db is None:
            return
        
        if not state or not node_name:
            return
        
        try:
            db_ops = get_db_ops(db)
            
            # Extract iteration context
            context = state.get("strategy_context", {})
            iteration = context.get("iteration_count", 0) 
            turn_id = context.get("turn_id", f"turn_{iteration}")
            
            # Route based on node name
            if node_name == "attack" and self.middleware_config.get("save_attacks"):
                await self._save_attack(db_ops, run_id, iteration, state, turn_id)
            
            elif node_name == "defence" and self.middleware_config.get("save_defences"):
                await self._save_defence(db_ops, run_id, iteration, state, turn_id)
            
            elif node_name == "eval" and self.middleware_config.get("save_evaluations"):
                await self._save_evaluation(db_ops, run_id, iteration, state, turn_id)
            
        except Exception as e:
            err("Error in after_step", error=str(e), node=node_name)
    
    async def after_run(
        self, 
        state: SystemState, 
        run_id: str
    ) -> None:
        """Mark run as completed in database"""
        db = get_db()
        if db is None:
            return
        
        try:
            db_ops = get_db_ops(db)
            
            # Extract final evaluation score
            current_turn = state.get("current_turn", {})
            final_score = None
            
            if current_turn.get("evaluation"):
                # ✓ REFACTORED: Direct property access
                final_score = current_turn["evaluation"].score
            
            # Extract best score from strategy context
            context = state.get("strategy_context", {})
            best_score = context.get("best_score")
            
            await db_ops.mark_run_completed(
                run_id,
                final_score=final_score,
                best_score=best_score
            )
            
            step("Automatic run completed in database", run_id=run_id)
            
        except Exception as e:
            err("Error in after_run", error=str(e))
    
    async def on_error(
        self, 
        error: Exception, 
        run_id: str, 
        state: Optional[SystemState] = None
    ) -> None:
        """Mark run as failed in database"""
        db = get_db()
        if db is None:
            return
        
        try:
            db_ops = get_db_ops(db)
            await db_ops.mark_run_failed(run_id, str(error))
            err("Automatic run failed in database", run_id=run_id)
            
        except Exception as e:
            err("Error in on_error handler", error=str(e))
    
    # =========================================================================
    # PRIVATE HELPER METHODS - Refactored with Direct Property Access
    # =========================================================================
    
    async def _save_attack(
        self, 
        db_ops, 
        run_id: str, 
        iteration: int, 
        state: SystemState, 
        turn_id: str
    ) -> None:
        """Save attack data to database"""
        current_turn = state.get("current_turn", {})
        attack = current_turn.get("attack")
        
        if not attack:
            return
        
        # ✓ REFACTORED: Use .to_string() method and direct .metadata access
        await db_ops.save_attack(
            run_id=run_id,
            index=iteration,
            turn_id=turn_id,
            prompt=attack.to_string(),  # Method that returns string
            metadata=attack.metadata     # Direct property access
        )
        debug("Attack saved", run_id=run_id, iteration=iteration)
    
    async def _save_defence(
        self, 
        db_ops, 
        run_id: str, 
        iteration: int, 
        state: SystemState, 
        turn_id: str
    ) -> None:
        """Save defence data to database"""
        current_turn = state.get("current_turn", {})
        defence = current_turn.get("defence")
        
        if not defence:
            return
        
        # ✓ REFACTORED: Direct property access instead of getters
        await db_ops.save_defence(
            run_id=run_id,
            index=iteration,
            turn_id=turn_id,
            response=defence.response_text,  # Direct property (was: defence.get_text())
            status_code=defence.status_code,  # Direct property
            was_blocked=defence.was_blocked(), # Method with logic (kept as-is)
            metadata=defence.metadata         # Direct property
        )
        debug("Defence saved", run_id=run_id, iteration=iteration)
    
    async def _save_evaluation(
        self, 
        db_ops, 
        run_id: str, 
        iteration: int, 
        state: SystemState, 
        turn_id: str
    ) -> None:
        """Save evaluation data to database"""
        current_turn = state.get("current_turn", {})
        evaluation = current_turn.get("evaluation")
        
        if not evaluation:
            return
        
        # ✓ REFACTORED: All direct property access
        await db_ops.save_evaluation(
            run_id=run_id,
            index=iteration,
            turn_id=turn_id,
            score=evaluation.score,        # Direct property (was: evaluation.get_score())
            success=evaluation.success,    # Direct property (was: evaluation.is_success())
            category=evaluation.category,  # Direct property (was: evaluation.get_category())
            feedback=evaluation.reasoning, # Direct property (was: evaluation.get_reasoning())
            metadata=evaluation.metadata   # Direct property
        )
        debug("Evaluation saved", run_id=run_id, iteration=iteration)
