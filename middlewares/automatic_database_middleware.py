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
from middlewares.base import BaseMiddleware
from server.database.connection import get_db
from server.database.operations import get_db_ops
from core.logging import debug, tracer, step, warn, err
from core.constants import NodeName
from engine.state import SystemState


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
        """Create a Session for this run and record started_at."""
        tracer("AutomaticDatabaseMiddleware.before_run", run_id=run_id)
        
        db = get_db()
        if db is None:
            warn("Database not connected, skipping persistence")
            return
        
        try:
            from datetime import datetime
            db_ops = get_db_ops(db)
            _now = datetime.utcnow().isoformat()

            # Persist started_at on the run document
            await db_ops.update_run(run_id, {"started_at": _now, "updated_at": _now})

            # Create one Session per automatic run
            session_id = f"sess_{run_id}"
            run_doc = await db_ops.get_run(run_id)
            run_name = run_doc.name if run_doc else run_id
            await db_ops.create_session(
                session_id=session_id,
                run_id=run_id,
                name=run_name,
                run_type="automatic",
            )
            state["session_id"] = session_id
            state["turn_index"] = 0
            step("Session created for automatic run", session_id=session_id)
            
        except Exception as e:
            err("Error in before_run", error=str(e))
    
    async def after_step(
        self, 
        state: SystemState, 
        run_id: str, 
        node_name: Optional[str] = None
    ) -> None:
        """Save step data to database and maintain Session/Turn references."""
        db = get_db()
        if db is None:
            return
        
        if not state or not node_name:
            return
        
        try:
            db_ops = get_db_ops(db)
            context = state.get("strategy_context", {})
            iteration = context.get("iteration_count", 0)
            turn_id = state.get("current_turn", {}).get("turn_id") or f"turn_{run_id}_{iteration}"
            session_id = state.get("session_id", f"sess_{run_id}")
            turn_index = state.get("turn_index", iteration)

            if node_name == NodeName.ATTACK and self.middleware_config.get("save_attacks"):
                # Create the Turn document on attack (first step of each cycle)
                await db_ops.create_turn(session_id, turn_id, run_id, index=turn_index)
                attack_id = await self._save_attack(db_ops, run_id, iteration, state, turn_id)
                if attack_id:
                    await db_ops.update_turn_references(turn_id, attack_data_id=attack_id)
            
            elif node_name == NodeName.DEFENCE and self.middleware_config.get("save_defences"):
                defence_id = await self._save_defence(db_ops, run_id, iteration, state, turn_id)
                if defence_id:
                    await db_ops.update_turn_references(turn_id, defence_data_id=defence_id)
            
            elif node_name == NodeName.EVAL and self.middleware_config.get("save_evaluations"):
                eval_id = await self._save_evaluation(db_ops, run_id, iteration, state, turn_id)
                if eval_id:
                    await db_ops.update_turn_references(turn_id, evaluation_data_id=eval_id)
                # Advance turn_index for next cycle
                state["turn_index"] = turn_index + 1
            
        except Exception as e:
            err("Error in after_step", error=str(e), node=node_name)
    
    async def after_run(
        self, 
        state: SystemState, 
        run_id: str
    ) -> None:
        """
        Mark automatic run as COMPLETED in database.
        
        ARCHITECTURAL BOUNDARY:
        For automatic runs, when LangGraph reaches __end__, the entire test is over.
        This middleware is responsible for the "Happy Path" status update to COMPLETED.
        """
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
            
            # Update database with COMPLETED status (Happy Path)
            from datetime import datetime
            await db_ops.update_run(run_id, {
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "final_score": final_score,
                "best_score": best_score,
                "manual_wait_active": False,
                "manual_input_required": None
            })
            
            step("Automatic run marked COMPLETED in database", run_id=run_id)
            
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
        attack_id = await db_ops.save_attack(
            run_id=run_id,
            index=iteration,
            turn_id=turn_id,
            prompt=attack.to_string(),
            metadata=attack.metadata
        )
        debug("Attack saved", run_id=run_id, iteration=iteration)
        return attack_id
    
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
        defence_id = await db_ops.save_defence(
            run_id=run_id,
            index=iteration,
            turn_id=turn_id,
            response=defence.response_text,
            status_code=defence.status_code,
            was_blocked=defence.was_blocked(),
            metadata=defence.metadata
        )
        debug("Defence saved", run_id=run_id, iteration=iteration)
        return defence_id
    
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
        eval_id = await db_ops.save_evaluation(
            run_id=run_id,
            index=iteration,
            turn_id=turn_id,
            score=evaluation.score,
            success=evaluation.success,
            category=evaluation.category,
            feedback=evaluation.reasoning,
            metadata=evaluation.metadata
        )
        debug("Evaluation saved", run_id=run_id, iteration=iteration)
        return eval_id

