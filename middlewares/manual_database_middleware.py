"""
Refactored Manual Database Middleware

CHANGES FROM ORIGINAL:
- ✓ Uses strict SystemState typing
- ✓ Direct property access (NOT legacy getters)
- ✓ Consistent runtime_config naming
- ✓ Aligned with base.py (BaseMiddleware) signature
"""

from typing import Dict, Any, Optional
from middlewares.base import BaseMiddleware
from server.database.connection import get_db
from server.database.operations import DatabaseOperations, get_db_ops
from core.logging import debug, tracer, step, warn, err
from core.constants import NodeName
from engine.state import SystemState
import uuid
from datetime import datetime


class ManualDatabaseMiddleware(BaseMiddleware):
    """
    Database middleware for manual runs.
    
    Manages state hydration, session/turn creation, and state persistence.
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
        """Initialize manual run — hydrate iteration count from last turn, create new Turn."""
        tracer("ManualDatabaseMiddleware.before_run", run_id=run_id)
        
        db = get_db()
        if db is None:
            warn("Database not connected, skipping persistence")
            return
        
        try:
            db_ops = get_db_ops(db)
            payload = state.get("payload", {})
            
            session_id = payload.get("session_id")
            if not session_id:
                err("Missing session_id for manual run")
                raise ValueError("Manual run requires a 'session_id' in the payload")
            
            # Try to resume from an existing unified session; create it if this is the first turn
            existing_session = await db_ops.get_session(session_id)
            if not existing_session:
                run_doc = await db_ops.get_run(run_id)
                run_name = run_doc.name if run_doc else run_id
                await db_ops.create_session(
                    session_id=session_id,
                    run_id=run_id,
                    name=run_name,
                    run_type="manual",
                )

            # Hydrate iteration count from last unified turn
            last_turn = await db_ops.get_last_turn_for_session(session_id)
            strategy_context = state.get("strategy_context", {})
            if last_turn:
                debug("Hydrating state from last turn", turn=last_turn.turn_id)
                strategy_context["iteration_count"] = last_turn.index + 1
                if "history" not in strategy_context:
                    strategy_context["history"] = []
            else:
                debug("Starting new turn, no prior turns")
                strategy_context["history"] = []
                strategy_context["iteration_count"] = 0
            
            strategy_context["session_id"] = session_id
            strategy_context["max_turns"] = self.middleware_config.get("max_turns", 100)
            state["strategy_context"] = strategy_context

            # Create new turn document
            current_turn_id = f"turn_{uuid.uuid4().hex[:8]}"
            turn_index = strategy_context["iteration_count"]
            state["current_turn"] = {"turn_id": current_turn_id}
            state["session_id"] = session_id
            state["turn_index"] = turn_index
            
            # Persist started_at on the very first turn
            if turn_index == 0:
                _now = datetime.utcnow().isoformat()
                await db_ops.update_run(run_id, {"started_at": _now, "updated_at": _now})
            
            await db_ops.create_turn(
                session_id=session_id,
                turn_id=current_turn_id,
                run_id=run_id,
                index=turn_index,
            )
            step("Turn created", turn=current_turn_id, session=session_id, index=turn_index)
            
        except ValueError as e:
            err("Configuration error in before_run", error=str(e))
            await db_ops.update_run(run_id, {"status": "failed", "error": str(e)})
        except Exception as e:
            err("Unexpected error in before_run", error=str(e))

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
            
            context = state.get("strategy_context", {})
            iteration = context.get("iteration_count", 0)
            session_id = context.get("session_id")
            current_turn_id = state.get("current_turn", {}).get("turn_id")
            
            if not session_id or not current_turn_id:
                warn("Missing session_id or turn_id in after_step", node=node_name)
                return
            
            if node_name == NodeName.ATTACK and self.middleware_config.get("save_attacks"):
                attack_id = await self._save_attack(db_ops, run_id, session_id, iteration, state, current_turn_id)
                if attack_id:
                    await db_ops.update_turn_references(current_turn_id, attack_data_id=attack_id)
            
            elif node_name == NodeName.DEFENCE and self.middleware_config.get("save_defences"):
                defence_id = await self._save_defence(db_ops, run_id, session_id, iteration, state, current_turn_id)
                if defence_id:
                    await db_ops.update_turn_references(current_turn_id, defence_data_id=defence_id)
            
            elif node_name == NodeName.EVAL and self.middleware_config.get("save_evaluations"):
                eval_id = await self._save_evaluation(db_ops, run_id, session_id, iteration, state, current_turn_id)
                if eval_id:
                    await db_ops.update_turn_references(current_turn_id, evaluation_data_id=eval_id)
            
        except Exception as e:
            err("Error in after_step", error=str(e), node=node_name)

    async def after_run(
        self, 
        state: SystemState, 
        run_id: str
    ) -> None:
        """
        Mark manual run as IDLE and save final state.
        
        ARCHITECTURAL BOUNDARY:
        For manual runs, when LangGraph reaches __end__, it only means the current turn is over.
        This middleware is responsible for the "Happy Path" status update to IDLE,
        so the run is ready to accept the next user prompt.
        """
        db = get_db()
        if db is None:
            return
        
        try:
            db_ops = get_db_ops(db)
            current_turn = state.get("current_turn", {})
            
            final_score = None
            if current_turn.get("evaluation"):
                # ✓ REFACTORED: Direct property access
                # Convert numpy types to Python native types for JSON serialization
                final_score = float(current_turn["evaluation"].score)
            
            context = state.get("strategy_context", {})
            best_score = context.get("best_score")
            session_id = state.get("session_id")
            
            # 5-B1: Read session_id from state - get_session_id_for_run() does not exist
            if not session_id:
                session_id = context.get("session_id")
            if not session_id:
                err("Cannot find session_id in final_state or strategy_context", run_id=run_id)
                await db_ops.update_run(run_id, {"status": "idle"})
                return
            
            # Update run status to IDLE (Happy Path — turn complete, awaiting next user input)
            from datetime import datetime
            await db_ops.update_run(run_id, {
                "status": "idle",
                "updated_at": datetime.utcnow().isoformat()
            })
            
            await db_ops.update_session(
                session_id,
                final_score=final_score,
                best_score=best_score,
                status="active",
            )
            
            step("Manual run turn completed, state saved, set to IDLE", run_id=run_id)
        
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
            err("Manual run failed in database", run_id=run_id)
        except Exception as e:
            err("Error in on_error handler", error=str(e))
    
    async def _save_attack(
        self,
        db_ops,
        run_id: str,
        session_id: str,
        iteration: int,
        state: SystemState,
        turn_id: str,
    ) -> str:
        """Save attack data and return the inserted document ID."""
        current_turn = state.get("current_turn", {})
        attack = current_turn.get("attack")
        if not attack:
            return None
        attack_id = await db_ops.save_attack(
            run_id=run_id,
            index=iteration,
            turn_id=turn_id,
            prompt=attack.to_string(),
            metadata=attack.metadata,
        )
        debug("Attack saved", turn=turn_id)
        return attack_id

    async def _save_defence(
        self,
        db_ops,
        run_id: str,
        session_id: str,
        iteration: int,
        state: SystemState,
        turn_id: str,
    ) -> str:
        """Save defence data and return the inserted document ID."""
        current_turn = state.get("current_turn", {})
        defence = current_turn.get("defence")
        if not defence:
            return None
        defence_id = await db_ops.save_defence(
            run_id=run_id,
            index=iteration,
            turn_id=turn_id,
            response=defence.response_text,
            status_code=defence.status_code,
            was_blocked=defence.was_blocked(),
            metadata=defence.metadata,
        )
        debug("Defence saved", turn=turn_id)
        return defence_id

    async def _save_evaluation(
        self,
        db_ops,
        run_id: str,
        session_id: str,
        iteration: int,
        state: SystemState,
        turn_id: str,
    ) -> str:
        """Save evaluation data and return the inserted document ID."""
        current_turn = state.get("current_turn", {})
        evaluation = current_turn.get("evaluation")
        if not evaluation:
            return None
        eval_id = await db_ops.save_evaluation(
            run_id=run_id,
            index=iteration,
            turn_id=turn_id,
            score=float(evaluation.score),
            success=evaluation.success,
            category=evaluation.category,
            feedback=evaluation.reasoning,
            metadata=evaluation.metadata,
        )
        debug("Evaluation saved", turn=turn_id, score=evaluation.score)
        return eval_id
