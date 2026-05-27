"""
================================================================================
BATCH WEBSOCKET MIDDLEWARE
================================================================================

ARCHITECTURAL ROLE:
--------------------------------------------------------------------------------
BatchWSMiddleware is a thin orchestration wrapper around the exact same WebSocket
broadcast operations used by AutomaticWSMiddleware.

It mirrors the automatic middleware's per-node trigger pattern exactly, but
reads from strategy_context["current_chunk_results"] instead of current_turn.

TRIGGER MAPPING (mirrors AutomaticWSMiddleware node-by-node):
  "defence" node — chunk_results has {attack, defence} per item.
                   Emit broadcast_attack_generated + broadcast_defence_response
                   immediately so the UI updates as each batch phase completes.

  "eval" node    — chunk_results gains {evaluation} per item.
                   Emit broadcast_evaluation_complete + broadcast_turn_completed
                   + evaluation_stats_updated, then a progress bar update.

  "router" node  — emit routing progress (same as AutomaticWSMiddleware).

NO new event types. NO new frontend contracts.
To the frontend, a batch run looks like many normal turns firing quickly in sequence.

CONCURRENCY: NONE. The loop is strictly sequential.
================================================================================
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from middlewares.base import BaseMiddleware
from server.websocket.socketio_manager import SocketIOManager
from server.websocket.operations import get_ws_ops
from engine.debug_utils import debug, tracer, step, warn, err
from engine.state_schema import SystemState


class BatchWSMiddleware(BaseMiddleware):
    """
    WebSocket middleware for batch runs.
    Iterates current_chunk_results after eval and emits the existing
    single-item WS events for each record — sequentially, in order.
    """

    def __init__(
        self,
        socketio_manager: SocketIOManager,
        middleware_config: Dict[str, Any] = None,
    ):
        default_config = {
            "broadcast_attacks": True,
            "broadcast_defences": True,
            "broadcast_evaluations": True,
        }
        if middleware_config:
            default_config.update(middleware_config)
        super().__init__(default_config)
        self.ws_ops = get_ws_ops(socketio_manager)

    # =========================================================================
    # LIFECYCLE HOOKS
    # =========================================================================

    async def before_run(
        self,
        state: SystemState,
        runtime_config: Dict[str, Any],
        run_id: str,
    ) -> None:
        """Broadcast run start — same event as AutomaticWSMiddleware."""
        tracer("BatchWSMiddleware.before_run", run_id=run_id)
        try:
            config_dict = state.get("config", {})
            strategy_config = config_dict.get("strategy_config", {})
            strategy_name = strategy_config.get("strategy_name", "batch")
            payload = state.get("payload", {})

            await self.ws_ops.broadcast_run_started(
                run_id,
                {
                    "strategy": strategy_name,
                    "intent": payload.get("intent", "batch adversarial testing"),
                    "target": payload.get("target"),
                    "timestamp": state.get("start_time"),
                },
            )
            debug("Batch run started broadcast sent", run_id=run_id)
        except Exception as e:
            err("BatchWSMiddleware.before_run error", error=str(e))

    async def after_step(
        self,
        state: SystemState,
        run_id: str,
        node_name: Optional[str] = None,
    ) -> None:
        """
        Broadcast batch data immediately as each phase completes — mirrors the
        per-node pattern of AutomaticWSMiddleware.

        "router"  — routing progress (unchanged).

        "defence" — chunk_results now has {attack, defence} per item.
                    Emit broadcast_attack_generated + broadcast_defence_response
                    for each record right away, so the UI sees attacks and
                    defences as soon as the batch defence phase finishes.

        "eval"    — chunk_results now has {evaluation} filled in per item.
                    Emit broadcast_evaluation_complete + broadcast_turn_completed
                    + evaluation_stats_updated per record, then a progress update.

        All other nodes are ignored.
        """
        if node_name == "router":
            await self._broadcast_routing(run_id, state)
            return

        if node_name not in ("defence", "eval"):
            return

        try:
            context = state.get("strategy_context", {})
            chunk_results: List[Dict[str, Any]] = context.get("current_chunk_results", [])

            if not chunk_results:
                warn("BatchWSMiddleware: no chunk_results to broadcast", node=node_name)
                return

            total_processed = context.get("total_processed", 0)
            dataset_total = len(context.get("dataset_prompts", []))
            # Reconstruct where this chunk started so per-item global index is correct.
            chunk_start_total = total_processed - len(chunk_results)

            # ── "defence" node: broadcast attacks + defences ─────────────────
            if node_name == "defence":
                step("BatchWSMiddleware: broadcasting attacks+defences", items=len(chunk_results))

                for local_idx, record in enumerate(chunk_results):
                    global_index: int = record.get("global_index", chunk_start_total + local_idx)
                    turn_id: str = record.get("turn_id", f"batch_{run_id}_{global_index}")
                    attack = record.get("attack")
                    defence = record.get("defence")

                    # broadcast_attack_generated (existing event)
                    if self.middleware_config.get("broadcast_attacks") and attack:
                        try:
                            attack_text = attack.to_string()
                            await self.ws_ops.broadcast_attack_generated(
                                run_id,
                                turn_id,
                                global_index,
                                {
                                    "preview": attack_text[:200],
                                    "full_text": attack_text,
                                    "type": attack._infer_type() if hasattr(attack, "_infer_type") else "text",
                                    "metadata": attack.metadata,
                                    "timestamp": datetime.utcnow().isoformat(),
                                },
                            )
                        except Exception as e:
                            err("BatchWSMiddleware: attack broadcast failed", index=global_index, error=str(e))

                    # broadcast_defence_response (existing event)
                    if self.middleware_config.get("broadcast_defences") and defence:
                        try:
                            await self.ws_ops.broadcast_defence_response(
                                run_id,
                                turn_id,
                                global_index,
                                {
                                    "preview": defence.response_text[:200],
                                    "full_text": defence.response_text,
                                    "status_code": defence.status_code,
                                    "was_blocked": defence.was_blocked(),
                                    "latency_ms": defence.metadata.get("latency_ms"),
                                    "timestamp": datetime.utcnow().isoformat(),
                                },
                            )
                        except Exception as e:
                            err("BatchWSMiddleware: defence broadcast failed", index=global_index, error=str(e))

                    debug("BatchWSMiddleware: attack+defence broadcast complete", index=global_index)

                step("BatchWSMiddleware: attacks+defences broadcast done", items=len(chunk_results))

            # ── "eval" node: broadcast evaluations + stats ───────────────────
            elif node_name == "eval":
                step("BatchWSMiddleware: broadcasting evaluations", items=len(chunk_results))

                # Running success counter — start from where we left off before this chunk.
                running_successful = context.get("successful_iterations", 0) - sum(
                    1 for r in chunk_results
                    if r.get("evaluation") and getattr(r["evaluation"], "success", False)
                )

                for local_idx, record in enumerate(chunk_results):
                    global_index = record.get("global_index", chunk_start_total + local_idx)
                    turn_id = record.get("turn_id", f"batch_{run_id}_{global_index}")
                    evaluation = record.get("evaluation")

                    if self.middleware_config.get("broadcast_evaluations") and evaluation:
                        try:
                            await self.ws_ops.broadcast_evaluation_complete(
                                run_id,
                                turn_id,
                                global_index,
                                {
                                    "score": evaluation.score,
                                    "success": evaluation.success,
                                    "category": evaluation.category,
                                    "reasoning": evaluation.reasoning,
                                    "summary": evaluation.to_summary(),
                                    "timestamp": datetime.utcnow().isoformat(),
                                },
                            )
                            await self.ws_ops.broadcast_turn_completed(run_id, turn_id, global_index)

                            # evaluation_stats_updated (existing event)
                            current_total = chunk_start_total + local_idx + 1
                            if evaluation.success:
                                running_successful += 1

                            await self.ws_ops.broadcast_to_room(
                                run_id,
                                "evaluation_stats_updated",
                                {
                                    "type": "evaluation_stats_updated",
                                    "run_id": run_id,
                                    "stats": {
                                        "total_evaluations": current_total,
                                        "success_rate": (
                                            running_successful / current_total if current_total else 0.0
                                        ),
                                        "latest_score": evaluation.score,
                                        "latest_success": evaluation.success,
                                        "latest_category": evaluation.category,
                                    },
                                },
                            )
                        except Exception as e:
                            err("BatchWSMiddleware: eval broadcast failed", index=global_index, error=str(e))

                    debug("BatchWSMiddleware: eval broadcast complete", index=global_index)

                # Progress bar update after eval chunk
                try:
                    await self.ws_ops.broadcast_run_progress(
                        run_id,
                        current=total_processed,
                        total=dataset_total if dataset_total else total_processed,
                        message=f"Batch chunk complete — {total_processed}/{dataset_total} processed",
                    )
                except Exception as e:
                    err("BatchWSMiddleware: progress broadcast failed", error=str(e))

                step("BatchWSMiddleware: evaluations broadcast done", items=len(chunk_results))

        except Exception as e:
            err("BatchWSMiddleware.after_step error", error=str(e), node=node_name)

    async def after_run(
        self,
        state: SystemState,
        run_id: str,
    ) -> None:
        """Broadcast run completion — reuses broadcast_run_completed (existing event)."""
        tracer("BatchWSMiddleware.after_run", run_id=run_id)
        try:
            context = state.get("strategy_context", {})
            total_processed = context.get("total_processed", 0)
            successful = context.get("successful_iterations", 0)
            final_score = (successful / total_processed) if total_processed > 0 else 0.0
            routing_signal = state.get("routing_signal")
            current_turn = state.get("current_turn", {})

            # Same structure as AutomaticWSMiddleware.after_run — no new event
            await self.ws_ops.broadcast_run_completed(
                run_id,
                {
                    "total_attempts": total_processed,
                    "routing_signal": routing_signal,
                    "timestamp": current_turn.get("timestamp"),
                    "final_evaluation": {
                        "score": final_score,
                        "success": successful > 0,
                        "category": "batch_complete",
                        "summary": (
                            f"Batch finished: {successful}/{total_processed} successful "
                            f"({final_score:.1%} success rate)"
                        ),
                    },
                },
            )

            # Notify sidebar to refresh — same as AutomaticWSMiddleware
            await self.ws_ops.broadcast_new_run_available(
                run_id,
                {
                    "strategy": context.get("strategy_name", "batch"),
                    "status": "completed",
                },
            )
            step("Batch run completed broadcast sent", run_id=run_id)
        except Exception as e:
            err("BatchWSMiddleware.after_run error", error=str(e))

    async def on_error(
        self,
        error: Exception,
        run_id: str,
        state: Optional[SystemState] = None,
    ) -> None:
        """Broadcast error — same as AutomaticWSMiddleware.on_error."""
        try:
            await self.ws_ops.broadcast_run_error(
                run_id,
                error=str(error),
                error_type=type(error).__name__,
            )
            debug("Batch error broadcast sent")
        except Exception as e:
            err("BatchWSMiddleware.on_error handler error", error=str(e))

    # =========================================================================
    # PRIVATE HELPERS
    # =========================================================================

    async def _broadcast_routing(self, run_id: str, state: SystemState) -> None:
        """Routing progress — same as AutomaticWSMiddleware._broadcast_routing."""
        try:
            context = state.get("strategy_context", {})
            current = context.get("total_processed", 0)
            total = len(context.get("dataset_prompts", [])) or (current + 1)
            routing_signal = state.get("routing_signal", "")
            await self.ws_ops.broadcast_run_progress(
                run_id,
                current=current,
                total=total,
                message=f"Routing: {routing_signal}",
            )
        except Exception as e:
            err("BatchWSMiddleware: routing broadcast failed", error=str(e))