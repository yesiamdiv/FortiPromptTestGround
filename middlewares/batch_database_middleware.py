"""
================================================================================
BATCH DATABASE MIDDLEWARE
================================================================================

ARCHITECTURAL ROLE:
--------------------------------------------------------------------------------
BatchDatabaseMiddleware is a thin orchestration wrapper around the exact same
save functions used by AutomaticDatabaseMiddleware.

It mirrors the automatic middleware's per-node trigger pattern exactly, but
reads from strategy_context["current_chunk_results"] instead of current_turn,
because BatchWrapperNode accumulates a whole chunk before returning.

TRIGGER MAPPING (mirrors AutomaticDatabaseMiddleware node-by-node):
  "defence" node — chunk_results has {attack, defence} per item at this point.
                   Save attacks + defences immediately, just like automatic does
                   on "attack" and "defence" nodes respectively.

  "eval" node    — chunk_results gains {evaluation} per item.
                   Save evaluations immediately, then update run counters.

This ensures data appears in the DB as soon as each batch phase completes,
not all at once at the end of the cycle.

NO new DB logic. NO bulk ops. NO insert_many.
The loop just calls the same helpers the automatic middleware already uses.

LIFECYCLE HOOKS:
  before_run  — record started_at (identical to AutomaticDatabaseMiddleware)
  after_step  — on "defence": persist attacks + defences from chunk_results
                on "eval":    persist evaluations from chunk_results
  after_run   — mark run COMPLETED with aggregate stats
  on_error    — mark run FAILED
================================================================================
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from middlewares.base import BaseMiddleware
from server.database.connection import get_db
from server.database.operations import get_db_ops
from core.logging import debug, tracer, step, warn, err
from core.constants import NodeName
from engine.state import SystemState


class BatchDatabaseMiddleware(BaseMiddleware):
    """
    Database middleware for batch runs.
    Iterates current_chunk_results and calls the same single-item save
    helpers used in AutomaticDatabaseMiddleware — one record at a time.
    """

    def __init__(self, middleware_config: Dict[str, Any] = None):
        default_config = {
            "save_attacks": True,
            "save_defences": True,
            "save_evaluations": True,
        }
        if middleware_config:
            default_config.update(middleware_config)
        super().__init__(default_config)

    # =========================================================================
    # LIFECYCLE HOOKS
    # =========================================================================

    async def before_run(
        self,
        state: SystemState,
        runtime_config: Dict[str, Any],
        run_id: str,
    ) -> None:
        """Record started_at and create one Session for this batch run."""
        tracer("BatchDatabaseMiddleware.before_run", run_id=run_id)
        db = get_db()
        if db is None:
            warn("Database not connected, skipping persistence")
            return
        try:
            db_ops = get_db_ops(db)
            _now = datetime.utcnow().isoformat()
            await db_ops.update_run(run_id, {"started_at": _now, "updated_at": _now})

            # Create one Session per batch run
            session_id = f"sess_{run_id}"
            run_doc = await db_ops.get_run(run_id)
            run_name = run_doc.name if run_doc else run_id
            await db_ops.create_session(
                session_id=session_id,
                run_id=run_id,
                name=run_name,
                run_type="batch",
            )
            state["session_id"] = session_id
            step("Batch session created", session_id=session_id)
        except Exception as e:
            err("BatchDatabaseMiddleware.before_run error", error=str(e))

    async def after_step(
        self,
        state: SystemState,
        run_id: str,
        node_name: Optional[str] = None,
    ) -> None:
        """
        Persist batch data immediately as each phase completes — mirrors the
        per-node pattern of AutomaticDatabaseMiddleware.

        "defence" — chunk_results now has {attack, defence} per item.
                    Save attacks + defences right away so they appear in the DB
                    as soon as the batch defence phase finishes, not at eval time.

        "eval"    — chunk_results now has {evaluation} filled in per item.
                    Save evaluations and update run-level counters.

        All other nodes are ignored (no data to persist yet).
        """
        if node_name not in (NodeName.DEFENCE, NodeName.EVAL):
            return

        db = get_db()
        if db is None:
            return

        try:
            db_ops = get_db_ops(db)
            context = state.get("strategy_context", {})
            chunk_results: List[Dict[str, Any]] = context.get("current_chunk_results", [])

            if not chunk_results:
                warn("BatchDatabaseMiddleware: no chunk_results to persist", node=node_name)
                return

            session_id = state.get("session_id", f"sess_{run_id}")

            # ── "defence" node: create turns, save attacks + defences ────────
            if node_name == NodeName.DEFENCE:
                step("BatchDatabaseMiddleware: persisting attacks+defences", items=len(chunk_results))
                for record in chunk_results:
                    turn_id: str = record.get("turn_id", f"batch_{run_id}_{record.get('global_index', 0)}")
                    global_index: int = record.get("global_index", 0)

                    # Create Turn document for this batch item
                    await db_ops.create_turn(session_id, turn_id, run_id, index=global_index)

                    attack_id = None
                    if self.middleware_config.get("save_attacks"):
                        attack_id = await self._save_attack(db_ops, run_id, global_index, record, turn_id)

                    defence_id = None
                    if self.middleware_config.get("save_defences"):
                        defence_id = await self._save_defence(db_ops, run_id, global_index, record, turn_id)

                    await db_ops.update_turn_references(
                        turn_id,
                        attack_data_id=attack_id,
                        defence_data_id=defence_id,
                    )

                step("BatchDatabaseMiddleware: attacks+defences persisted", items=len(chunk_results))

            # ── "eval" node: save evaluations + update counters ──────────────
            elif node_name == NodeName.EVAL:
                step("BatchDatabaseMiddleware: persisting evaluations", items=len(chunk_results))
                successful_in_chunk = 0

                for record in chunk_results:
                    turn_id = record.get("turn_id", f"batch_{run_id}_{record.get('global_index', 0)}")
                    global_index = record.get("global_index", 0)

                    if self.middleware_config.get("save_evaluations"):
                        eval_id = await self._save_evaluation(db_ops, run_id, global_index, record, turn_id)
                        if eval_id:
                            await db_ops.update_turn_references(turn_id, evaluation_data_id=eval_id)
                        eval_obj = record.get("evaluation")
                        if eval_obj and hasattr(eval_obj, "success") and eval_obj.success:
                            successful_in_chunk += 1

                step(
                    "BatchDatabaseMiddleware: evaluations persisted",
                    items=len(chunk_results),
                    successful=successful_in_chunk,
                )

        except Exception as e:
            err("BatchDatabaseMiddleware.after_step error", error=str(e), node=node_name)

    async def after_run(
        self,
        state: SystemState,
        run_id: str,
    ) -> None:
        """Mark batch run COMPLETED — mirrors AutomaticDatabaseMiddleware.after_run."""
        tracer("BatchDatabaseMiddleware.after_run", run_id=run_id)
        db = get_db()
        if db is None:
            return
        try:
            db_ops = get_db_ops(db)
            context = state.get("strategy_context", {})
            total_processed = context.get("total_processed", 0)
            # successful_iterations is no longer cached on RunModel; derive from context.
            successful = context.get("total_successful", context.get("successful_count", 0))
            final_score = (successful / total_processed) if total_processed > 0 else 0.0

            await db_ops.update_run(run_id, {
                "status": "completed",
                "completed_at": datetime.utcnow().isoformat(),
                "final_score": final_score,
                "best_score": final_score,
                "manual_wait_active": False,
                "manual_input_required": None,
            })
            step(
                "Batch run marked COMPLETED",
                run_id=run_id,
                total_processed=total_processed,
                successful=successful,
                final_score=final_score,
            )
        except Exception as e:
            err("BatchDatabaseMiddleware.after_run error", error=str(e))

    async def on_error(
        self,
        error: Exception,
        run_id: str,
        state: Optional[SystemState] = None,
    ) -> None:
        """Mark run FAILED — identical to AutomaticDatabaseMiddleware.on_error."""
        db = get_db()
        if db is None:
            return
        try:
            db_ops = get_db_ops(db)
            await db_ops.mark_run_failed(run_id, str(error))
            err("Batch run marked FAILED", run_id=run_id)
        except Exception as e:
            err("BatchDatabaseMiddleware.on_error handler error", error=str(e))

    # =========================================================================
    # PRIVATE HELPERS — same signatures as AutomaticDatabaseMiddleware
    # =========================================================================

    async def _save_attack(self, db_ops, run_id: str, index: int, record: Dict, turn_id: str) -> None:
        try:
            attack = record.get("attack")
            if not attack:
                return
            return await db_ops.save_attack(
                run_id=run_id,
                index=index,
                turn_id=turn_id,
                prompt=attack.to_string(),
                metadata=attack.metadata,
            )
            debug("Attack saved", run_id=run_id, index=index)
        except Exception as e:
            err("Failed to save attack", index=index, error=str(e))

    async def _save_defence(self, db_ops, run_id: str, index: int, record: Dict, turn_id: str) -> None:
        try:
            defence = record.get("defence")
            if not defence:
                return
            return await db_ops.save_defence(
                run_id=run_id,
                index=index,
                turn_id=turn_id,
                response=defence.response_text,
                status_code=defence.status_code,
                was_blocked=defence.was_blocked(),
                metadata=defence.metadata,
            )
            debug("Defence saved", run_id=run_id, index=index)
        except Exception as e:
            err("Failed to save defence", index=index, error=str(e))

    async def _save_evaluation(self, db_ops, run_id: str, index: int, record: Dict, turn_id: str) -> None:
        try:
            evaluation = record.get("evaluation")
            if not evaluation:
                return
            return await db_ops.save_evaluation(
                run_id=run_id,
                index=index,
                turn_id=turn_id,
                score=evaluation.score,
                success=evaluation.success,
                category=evaluation.category,
                feedback=evaluation.reasoning,
                metadata=evaluation.metadata,
            )
            debug("Evaluation saved", run_id=run_id, index=index)
        except Exception as e:
            err("Failed to save evaluation", index=index, error=str(e))