"""
================================================================================
BATCH DATABASE MIDDLEWARE
================================================================================

ARCHITECTURAL ROLE:
--------------------------------------------------------------------------------
BatchDatabaseMiddleware is a thin orchestration wrapper around the exact same
save functions used by AutomaticDatabaseMiddleware.

After the eval node fires (node_name == "eval"), the middleware reads
strategy_context["current_chunk_results"] — the list of
{turn_id, prompt, attack, defence, evaluation} records filled in by
BatchWrapperNode — and calls the SAME _save_attack / _save_defence /
_save_evaluation helpers one record at a time, sequentially.

NO new DB logic. NO bulk ops. NO insert_many.
The loop just calls the same helpers the automatic middleware already uses.

LIFECYCLE HOOKS:
  before_run  — record started_at (identical to AutomaticDatabaseMiddleware)
  after_step  — on "eval": persist entire chunk sequentially
  after_run   — mark run COMPLETED with aggregate stats
  on_error    — mark run FAILED
================================================================================
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from middlewares.base import BaseMiddleware
from server.database.connection import get_db
from server.database.operations import get_db_ops
from engine.debug_utils import debug, tracer, step, warn, err
from engine.state_schema import SystemState


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
        """Record started_at — identical to AutomaticDatabaseMiddleware."""
        tracer("BatchDatabaseMiddleware.before_run", run_id=run_id)
        db = get_db()
        if db is None:
            warn("Database not connected, skipping persistence")
            return
        try:
            db_ops = get_db_ops(db)
            _now = datetime.utcnow().isoformat()
            await db_ops.update_run(run_id, {"started_at": _now, "updated_at": _now})
            debug("Batch run started_at recorded", run_id=run_id)
        except Exception as e:
            err("BatchDatabaseMiddleware.before_run error", error=str(e))

    async def after_step(
        self,
        state: SystemState,
        run_id: str,
        node_name: Optional[str] = None,
    ) -> None:
        """
        After the eval node: persist every record in current_chunk_results sequentially.
        Uses the same _save_* helpers as AutomaticDatabaseMiddleware — no new DB logic.
        """
        # Only act once per chunk cycle — after eval, when all three payloads are set
        if node_name != "eval":
            return

        db = get_db()
        if db is None:
            return

        try:
            db_ops = get_db_ops(db)
            context = state.get("strategy_context", {})
            chunk_results: List[Dict[str, Any]] = context.get("current_chunk_results", [])

            if not chunk_results:
                warn("BatchDatabaseMiddleware: no chunk_results to persist")
                return

            step("BatchDatabaseMiddleware: persisting chunk", items=len(chunk_results))
            successful_in_chunk = 0

            # ── Sequential persistence — NO bulk ops, NO concurrency ──
            for record in chunk_results:
                turn_id: str = record.get("turn_id", f"batch_{run_id}_{record.get('global_index', 0)}")
                global_index: int = record.get("global_index", 0)

                if self.middleware_config.get("save_attacks"):
                    await self._save_attack(db_ops, run_id, global_index, record, turn_id)

                if self.middleware_config.get("save_defences"):
                    await self._save_defence(db_ops, run_id, global_index, record, turn_id)

                if self.middleware_config.get("save_evaluations"):
                    await self._save_evaluation(db_ops, run_id, global_index, record, turn_id)
                    eval_obj = record.get("evaluation")
                    if eval_obj and hasattr(eval_obj, "success") and eval_obj.success:
                        successful_in_chunk += 1

            # Increment run-level counters (same $inc pattern as AutomaticDatabaseMiddleware)
            inc_update = {
                "$inc": {
                    "total_iterations": len(chunk_results),
                    "successful_iterations": successful_in_chunk,
                }
            }
            await db_ops.runs.update_one({"run_id": run_id}, inc_update)

            step(
                "BatchDatabaseMiddleware: chunk persisted",
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
            successful = context.get("successful_iterations", 0)
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
            await db_ops.save_attack(
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
            await db_ops.save_defence(
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
            await db_ops.save_evaluation(
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
