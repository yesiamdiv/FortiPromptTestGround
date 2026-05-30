"""
================================================================================
ENSEMBLE DEFENCE NODE
================================================================================

In-process defence using a layered model ensemble.
If the ensemble allows the prompt through AND enable_llm_forwarding=True,
forwards the prompt to a configured LLM and records the LLM's response.
================================================================================
"""

from typing import Dict, Any, Callable, List, Optional
from datetime import datetime
from nodes.base import BaseAdversarialNode
from nodes.llm_forwarding_mixin import LLMForwardingMixin
from core.models import create_defence_response
from engine.state import SystemState
from core.logging import debug, tracer, step, warn, err


class EnsembleDefenceNode(LLMForwardingMixin, BaseAdversarialNode):

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.node_params = self.config.get("node_params", {})

        self.layers = self.node_params.get("layers", [[self._default_model]])
        self.voting_strategy = self.node_params.get("voting_strategy", "any")

        for i, layer in enumerate(self.layers):
            if not layer:
                raise ValueError(f"Layer {i} is empty")
            for j, model in enumerate(layer):
                if not callable(model):
                    raise ValueError(f"Layer {i}, model {j} is not callable")

        # Initialise LLM forwarding
        self._init_llm_forwarding(self.node_params)

    async def execute(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        if runtime_config is None:
            runtime_config = {}
        tracer("EnsembleDefenceNode.execute")

        if "current_turn" not in state:
            raise ValueError("Corrupted state: Missing 'current_turn'.")

        current_turn = state["current_turn"]
        attack = current_turn.get("attack")
        if not attack:
            raise ValueError("No attack payload found in current_turn")

        attack_text = attack.to_string()
        start_time = datetime.utcnow()
        all_votes, layer_results = [], []

        for layer_idx, layer in enumerate(self.layers):
            layer_votes = []
            for model_idx, model in enumerate(layer):
                is_malicious = await self._call_model(model, attack_text, f"layer_{layer_idx}_model_{model_idx}")
                layer_votes.append(is_malicious)
                all_votes.append(is_malicious)

            layer_decision = any(layer_votes)
            layer_results.append({"layer": layer_idx, "votes": layer_votes, "decision": layer_decision})

            if layer_decision and self.node_params.get("early_stop", False):
                break

        should_block = self._apply_voting_strategy(all_votes)
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

        status_code = 403 if should_block else 200
        response_text = "Request blocked by ensemble." if should_block else "Request allowed."

        defence = create_defence_response(
            text=response_text,
            status_code=status_code,
            latency_ms=latency_ms,
            voting_strategy=self.voting_strategy,
            layer_results=layer_results,
        )

        # Forward to LLM if allowed and toggled on
        defence = await self.maybe_forward_to_llm(defence, attack_text, runtime_config)

        return {"current_turn": {"defence": defence, "node_name": getattr(self, "name", "ensemble_defence")}}

    async def _call_model(self, model: Callable, attack_text: str, model_id: str) -> bool:
        try:
            import inspect
            if inspect.iscoroutinefunction(model):
                result = await model(attack_text)
            else:
                result = model(attack_text)
            return bool(result)
        except Exception:
            return True

    def _apply_voting_strategy(self, votes: List[bool]) -> bool:
        if not votes:
            return True
        malicious_count = sum(votes)
        if self.voting_strategy == "any":
            return malicious_count > 0
        if self.voting_strategy == "majority":
            return malicious_count > (len(votes) / 2)
        if self.voting_strategy == "unanimous":
            return malicious_count == len(votes)
        return malicious_count > 0

    @staticmethod
    def _default_model(text: str) -> bool:
        red_flags = ["ignore", "bypass", "jailbreak", "override"]
        return any(flag in text.lower() for flag in red_flags)

    @classmethod
    def get_node_schema(cls) -> Dict[str, Any]:
        props = {
            "voting_strategy": {
                "type": "string",
                "enum": ["any", "majority", "unanimous"],
                "default": "any",
                "description": "How ensemble votes are combined to reach a block decision",
            },
            "early_stop": {
                "type": "boolean",
                "default": False,
                "description": "Stop evaluating layers as soon as one blocks",
            },
        }
        props.update(LLMForwardingMixin.llm_forwarding_schema_fragment())
        return {"type": "object", "properties": props}
