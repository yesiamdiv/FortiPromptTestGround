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
from engine.debug_utils import debug, tracer, step, warn, err
from engine.state_schema import SystemState
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
        """Initialize manual run - hydrate from last turn or start fresh"""
        tracer("ManualDatabaseMiddleware.before_run", run_id=run_id)
        
        db = get_db()
        if db is None:
            warn("Database not connected, skipping persistence")
            return
        
        try:
            db_ops = get_db_ops(db)
            config_dict = state.get("config", {})
            strategy_config = config_dict.get("strategy_config", {})
            strategy_name = strategy_config.get("strategy_name", "unknown_strategy")
            payload = state.get("payload", {})
            
            session_id = payload.get("session_id")
            if not session_id:
                err("Missing session_id for manual run")
                raise ValueError("Manual run requires a 'session_id' in the payload")
            
            # Hydrate from last turn
            last_manual_turn = await db_ops.get_last_manual_turn_for_session(session_id)
            
            strategy_context = state.get("strategy_context", {})
            if last_manual_turn:
                debug("Hydrating state from last turn", turn=last_manual_turn.turn_id)
                # ManualTurn has no attack_prompt field — only attack_data_id.
                # History is rebuilt by ManualStrategy from the conversation payload;
                # we only need to restore the iteration count.
                strategy_context["iteration_count"] = last_manual_turn.index + 1
                if "history" not in strategy_context:
                    strategy_context["history"] = []
            else:
                debug("Starting new turn, no prior turns")
                strategy_context["history"] = []
                strategy_context["iteration_count"] = 0
            
            strategy_context["session_id"] = session_id
            strategy_context["max_turns"] = self.middleware_config.get("max_turns", 100)
            
            state["strategy_context"] = strategy_context
            
            # Create new turn
            current_turn_id = f"turn_{uuid.uuid4().hex[:8]}"
            state["current_turn"] = {"turn_id": current_turn_id}
            state["session_id"] = session_id
            
            # Persist started_at on the very first turn
            if strategy_context.get("iteration_count", 0) == 0:
                _now = datetime.utcnow().isoformat()
                await db_ops.update_run(run_id, {"started_at": _now, "updated_at": _now})
            
            await db_ops.create_manual_turn(
                session_id=session_id,
                turn_id=current_turn_id,
                run_id=run_id,
                index=state['strategy_context']['iteration_count']
            )
            step("Manual turn created", turn=current_turn_id, session=session_id)
            
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
            
            if node_name == "attack" and self.middleware_config.get("save_attacks"):
                await self._save_attack(db_ops, run_id, session_id, iteration, state, current_turn_id)
            
            elif node_name == "defence" and self.middleware_config.get("save_defences"):
                await self._save_defence(db_ops, run_id, session_id, iteration, state, current_turn_id)
            
            elif node_name == "eval" and self.middleware_config.get("save_evaluations"):
                await self._save_evaluation(db_ops, run_id, session_id, iteration, state, current_turn_id)
            
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
            
            await db_ops.update_manual_session_state(
                session_id=session_id,
                run_id=run_id,
                final_score=final_score,
                best_score=best_score
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
        turn_id: str
    ) -> None:
        """Save attack data"""
        current_turn = state.get("current_turn", {})
        attack = current_turn.get("attack")
        
        if not attack:
            return
        
        # Convert numpy types to Python native types for JSON serialization
        await db_ops.update_manual_turn_data(
            session_id=session_id,
            turn_id=turn_id,
            attack_prompt=attack.to_string(),
            attack_metadata=attack.metadata,
            turn_index=int(iteration)
        )
        debug("Attack saved", turn=turn_id)
    
    async def _save_defence(
        self, 
        db_ops:DatabaseOperations, 
        run_id: str, 
        session_id: str, 
        iteration: int, 
        state: SystemState, 
        turn_id: str
    ) -> None:
        """Save defence data"""
        current_turn = state.get("current_turn", {})
        defence = current_turn.get("defence")
        
        if not defence:
            return
        
        # ✓ REFACTORED: Direct property access
        # Convert numpy types to Python native types for JSON serialization
        await db_ops.update_manual_turn_data(
            session_id=session_id,
            turn_id=turn_id,
            defence_response=defence.response_text,  # Direct property
            defence_status_code=int(defence.status_code),
            defence_was_blocked=bool(defence.was_blocked()),
            defence_metadata=defence.metadata,
            turn_index=int(iteration)
        )
        debug("Defence saved", turn=turn_id)
    
    async def _save_evaluation(
        self, 
        db_ops, 
        run_id: str, 
        session_id: str, 
        iteration: int, 
        state: SystemState, 
        turn_id: str
    ) -> None:
        """Save evaluation data"""
        current_turn = state.get("current_turn", {})
        evaluation = current_turn.get("evaluation")
        
        if not evaluation:
            return
        
        # ✓ REFACTORED: All direct property access
        # Convert numpy types to Python native types for JSON serialization
        await db_ops.update_manual_turn_data(
            session_id=session_id,
            turn_id=turn_id,
            evaluation_score=float(evaluation.score),        # Direct property
            evaluation_success=bool(evaluation.success),    # Direct property
            evaluation_category=evaluation.category,  # Direct property
            evaluation_feedback=evaluation.reasoning, # Direct property
            evaluation_metadata=evaluation.metadata,
            turn_index=int(iteration)
        )
        debug("Evaluation saved", turn=turn_id)