"""
================================================================================
BATCH WRAPPER NODE
================================================================================

ARCHITECTURAL ROLE:
--------------------------------------------------------------------------------
BatchWrapperNode is a GENERIC orchestration adapter that wraps any single-item
node (defence or eval). It is the ONLY place where the batch execution loop lives.

LangGraph calls this node exactly as it would call any other node.
Internally, it reads the current chunk from strategy_context["current_chunk"],
loops sequentially (NO concurrency) over each prompt, calls the injected
single-item node once per item, and aggregates the results back into
strategy_context["current_chunk_results"].

USAGE (in ConfigurableGraphBuilder for batch graph_type):
    single_defence = HTTPDefenceNode(config={...})
    graph.add_node("defence", BatchWrapperNode(single_node=single_defence, role="defence"))

    single_eval = LLMEvalNode(config={...})
    graph.add_node("eval", BatchWrapperNode(single_node=single_eval, role="eval"))

    # Attack node stays unchanged — StrategyDrivenAttackNode delegates to BatchStrategy

ROLES:
    "defence" — reads current_chunk, calls single_node once per prompt,
                stores DefencePayload per item into current_chunk_results[i]["defence"]
                sets current_turn["defence"] to the LAST item's payload (for middlewares)

    "eval"    — reads current_chunk_results (already has "defence" per item),
                calls single_node once per pair,
                stores EvalResult per item into current_chunk_results[i]["evaluation"]
                sets current_turn["evaluation"] to the LAST item's result
                updates strategy_context counters (total_processed, successful_iterations)

CONCURRENCY: NONE. Strictly sequential for-loops. No asyncio.gather.

SINGLE RESPONSIBILITY:
    This node contains ZERO defence or evaluation logic.
    It only orchestrates: read chunk → loop → call delegate → aggregate.
    All actual logic stays inside the injected single_node instance.

GENERIC DESIGN:
    Adding a new defence node (e.g. LocalModelDefenceNode) in the future requires
    zero changes here. Just pass the new instance as single_node.
================================================================================
"""

import copy
import uuid
from typing import Dict, Any, List, Optional

from nodes.base import BaseAdversarialNode
from engine.domain_models import (
    AttackPayload, DefencePayload, EvalResult,
    create_simple_attack, create_defence_response, create_eval_result,
)
from engine.state_schema import SystemState, create_turn_data
from engine.debug_utils import debug, tracer, step, warn, err, checkpoint


class BatchWrapperNode(BaseAdversarialNode):
    """
    Generic sequential wrapper around any single-item BaseAdversarialNode.
    Handles both the defence loop and the eval loop depending on `role`.
    """

    ROLE_DEFENCE = "defence"
    ROLE_EVAL = "eval"

    def __init__(self, config: Dict[str, Any] = None):
        """
        Config keys:
            single_node : BaseAdversarialNode  — the injected single-item delegate (required)
            role        : str                   — "defence" or "eval" (required)
        """
        super().__init__(config)

        self._single_node: Optional[BaseAdversarialNode] = self.config.get("single_node")
        self._role: str = self.config.get("role", "")

        if self._single_node is None:
            raise ValueError(
                "BatchWrapperNode requires 'single_node' in config. "
                "Pass the single-item node instance to wrap."
            )
        if self._role not in (self.ROLE_DEFENCE, self.ROLE_EVAL):
            raise ValueError(
                f"BatchWrapperNode 'role' must be '{self.ROLE_DEFENCE}' or '{self.ROLE_EVAL}', "
                f"got: '{self._role}'"
            )

        step(
            "BatchWrapperNode ready",
            role=self._role,
            delegate=type(self._single_node).__name__,
        )

    # =========================================================================
    # MAIN EXECUTE — called by LangGraph
    # =========================================================================

    async def execute(
        self, state: SystemState, runtime_config: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Dispatch to the correct loop based on role.
        Returns a state delta — does NOT mutate state directly.
        """
        if runtime_config is None:
            runtime_config = {}
        tracer("BatchWrapperNode.execute", role=self._role)

        if self._role == self.ROLE_DEFENCE:
            return await self._run_defence_loop(state, runtime_config)
        else:
            return await self._run_eval_loop(state, runtime_config)

    # =========================================================================
    # DEFENCE LOOP
    # =========================================================================

    async def _run_defence_loop(
        self, state: SystemState, runtime_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Read current_chunk from strategy_context.
        For each prompt → build a single-item state → call single_node.execute().
        Store DefencePayload for each item in current_chunk_results.
        Set current_turn["defence"] to the last item's payload.
        """
        context = state.get("strategy_context", {})
        chunk: List[str] = context.get("current_chunk", [])

        if not chunk:
            warn("BatchWrapperNode(defence): current_chunk is empty — skipping loop")
            return {}

        step("BatchWrapperNode(defence): starting loop", chunk_size=len(chunk))

        # global_index base = prompts already processed before this chunk.
        # We derive it from total_processed (set by the PREVIOUS eval loop) + local index.
        # Do NOT use total_processed + i here because total_processed hasn't been
        # incremented for the current chunk yet (that happens in the eval loop).
        global_index_base: int = context.get("total_processed", 0)

        # Initialise chunk_results list (one entry per prompt)
        chunk_results: List[Dict[str, Any]] = [
            {
                "prompt": prompt_text,
                "attack": None,
                "defence": None,
                "evaluation": None,
                "turn_id": f"batch_d_{i}_{uuid.uuid4().hex[:4]}",
                "index": i,
                "global_index": global_index_base + i,
            }
            for i, prompt_text in enumerate(chunk)
        ]

        last_defence: Optional[DefencePayload] = None

        # ── Sequential loop — NO concurrency ──
        for i, record in enumerate(chunk_results):
            prompt_text = record["prompt"]
            turn_id = record["turn_id"]
            debug("BatchWrapperNode(defence): item", index=i, total=len(chunk))

            # Build single-item state for this prompt
            item_state = self._build_item_state_for_defence(state, context, prompt_text, turn_id)

            # Call the real single-item defence node
            try:
                delta = await self._single_node.execute(item_state, runtime_config)
                defence_payload: Optional[DefencePayload] = (
                    delta.get("current_turn", {}).get("defence")
                )
            except Exception as e:
                err("BatchWrapperNode(defence): delegate raised", index=i, error=str(e))
                defence_payload = create_defence_response(
                    text=f"[BATCH ERROR] Defence failed: {e}",
                    status_code=500,
                )

            record["attack"] = item_state["current_turn"]["attack"]
            record["defence"] = defence_payload
            last_defence = defence_payload

            debug(
                "BatchWrapperNode(defence): item done",
                index=i,
                blocked=defence_payload.was_blocked() if defence_payload else None,
            )

        checkpoint("BatchWrapperNode(defence): loop complete", processed=len(chunk_results))

        # Update context with results (eval loop will extend these same records)
        updated_context = copy.deepcopy(context)
        updated_context["current_chunk_results"] = chunk_results

        # Update current_turn with last item's defence so single-item middlewares work
        current_turn = copy.deepcopy(state.get("current_turn", {}))
        current_turn["defence"] = last_defence
        current_turn["node_name"] = "defence"

        return {
            "current_turn": current_turn,
            "strategy_context": updated_context,
        }

    # =========================================================================
    # EVAL LOOP
    # =========================================================================

    async def _run_eval_loop(
        self, state: SystemState, runtime_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Read current_chunk_results from strategy_context (set by defence loop).
        For each {prompt, attack, defence} record → build single-item state →
        call single_node.execute().
        Store EvalResult for each item back in current_chunk_results.
        Update counters (total_processed, successful_iterations).
        Set current_turn["evaluation"] to the last item's result.
        """
        context = state.get("strategy_context", {})
        chunk_results: List[Dict[str, Any]] = context.get("current_chunk_results", [])

        if not chunk_results:
            warn("BatchWrapperNode(eval): current_chunk_results is empty — skipping loop")
            return {}

        step("BatchWrapperNode(eval): starting loop", items=len(chunk_results))

        last_eval: Optional[EvalResult] = None
        successful_in_chunk = 0

        # ── Sequential loop — NO concurrency ──
        for i, record in enumerate(chunk_results):
            prompt_text: str = record.get("prompt", "")
            attack_payload: Optional[AttackPayload] = record.get("attack")
            defence_payload: Optional[DefencePayload] = record.get("defence")
            turn_id: str = record.get("turn_id", f"batch_e_{i}_{uuid.uuid4().hex[:4]}")

            debug("BatchWrapperNode(eval): item", index=i, total=len(chunk_results))

            if defence_payload is None:
                warn("BatchWrapperNode(eval): missing defence for item, using error result", index=i)
                record["evaluation"] = create_eval_result(
                    score=0.0, success=False,
                    category="batch_error",
                    reasoning="[BATCH ERROR] Defence payload missing — cannot evaluate.",
                )
                continue

            # Build single-item state for this pair
            item_state = self._build_item_state_for_eval(
                state, context, prompt_text, attack_payload, defence_payload, turn_id
            )

            # Call the real single-item eval node
            try:
                delta = await self._single_node.execute(item_state, runtime_config)
                eval_result: Optional[EvalResult] = (
                    delta.get("current_turn", {}).get("evaluation")
                )
            except Exception as e:
                err("BatchWrapperNode(eval): delegate raised", index=i, error=str(e))
                eval_result = create_eval_result(
                    score=0.0, success=False,
                    category="batch_error",
                    reasoning=f"[BATCH ERROR] Eval failed: {e}",
                )

            record["evaluation"] = eval_result
            last_eval = eval_result

            if eval_result and eval_result.success:
                successful_in_chunk += 1

            debug(
                "BatchWrapperNode(eval): item done",
                index=i,
                success=eval_result.success if eval_result else None,
                score=eval_result.score if eval_result else None,
            )

        checkpoint("BatchWrapperNode(eval): loop complete", processed=len(chunk_results))

        # ── Update cumulative counters ──
        updated_context = copy.deepcopy(context)
        updated_context["current_chunk_results"] = chunk_results
        updated_context["total_processed"] = (
            updated_context.get("total_processed", 0) + len(chunk_results)
        )
        updated_context["successful_iterations"] = (
            updated_context.get("successful_iterations", 0) + successful_in_chunk
        )

        step(
            "BatchWrapperNode(eval): counters updated",
            total_processed=updated_context["total_processed"],
            successful=updated_context["successful_iterations"],
        )

        # Update current_turn with last item's evaluation so single-item middlewares work
        current_turn = copy.deepcopy(state.get("current_turn", {}))
        current_turn["evaluation"] = last_eval
        current_turn["node_name"] = "eval"

        return {
            "current_turn": current_turn,
            "strategy_context": updated_context,
        }

    # =========================================================================
    # PRIVATE STATE BUILDERS
    # =========================================================================

    def _build_item_state_for_defence(
        self,
        root_state: SystemState,
        context: Dict[str, Any],
        prompt_text: str,
        turn_id: str,
    ) -> SystemState:
        """
        Build a single-item SystemState for one defence call.
        Populates current_turn["attack"] from the prompt text.
        """
        item_state = copy.deepcopy(root_state)
        turn = create_turn_data(turn_id, "attack")
        turn["attack"] = create_simple_attack(
            prompt_text,
            strategy="batch",
            batch_iteration=context.get("iteration_count", 0),
        )
        item_state["current_turn"] = turn
        item_state["strategy_context"] = context
        return item_state

    def _build_item_state_for_eval(
        self,
        root_state: SystemState,
        context: Dict[str, Any],
        prompt_text: str,
        attack_payload: Optional[AttackPayload],
        defence_payload: DefencePayload,
        turn_id: str,
    ) -> SystemState:
        """
        Build a single-item SystemState for one eval call.
        Populates current_turn["attack"] and current_turn["defence"].
        """
        item_state = copy.deepcopy(root_state)
        turn = create_turn_data(turn_id, "defence")

        # Use the real attack payload from the defence loop; fall back to recreating it
        if attack_payload is not None:
            turn["attack"] = attack_payload
        else:
            turn["attack"] = create_simple_attack(
                prompt_text,
                strategy="batch",
                batch_iteration=context.get("iteration_count", 0),
            )
        turn["defence"] = defence_payload
        item_state["current_turn"] = turn
        item_state["strategy_context"] = context
        return item_state

    @classmethod
    def get_node_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "single_node": {
                    "description": (
                        "Instance of any BaseAdversarialNode to wrap. "
                        "The wrapper calls this node once per item in the chunk."
                    ),
                },
                "role": {
                    "type": "string",
                    "enum": ["defence", "eval"],
                    "description": "Whether this wrapper handles the defence or eval loop.",
                },
            },
            "required": ["single_node", "role"],
            "description": (
                "Generic sequential batch wrapper. Loops a single-item node over "
                "the current chunk stored in strategy_context['current_chunk']. "
                "Zero logic inside — pure orchestration."
            ),
        }
