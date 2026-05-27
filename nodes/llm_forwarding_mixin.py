"""
================================================================================
LLM FORWARDING MIXIN
================================================================================

WHAT IT DOES:
    When a defence node allows a prompt through (not blocked), this mixin
    forwards the prompt to a configured LLM and replaces the defence response
    text with the LLM's actual response.

    The block/allow decision and status_code from the defence remain unchanged.
    Only response_text is replaced — so the evaluation node sees a real LLM
    response to judge, not just "Request allowed." or similar placeholder text.

WHY THIS MATTERS:
    Evaluation nodes need a meaningful response to score. If the defence just
    says "Request processed successfully.", the evaluator has nothing to work
    with. The LLM response gives the evaluator real content.

HOW TO USE IT (in any defence node):
    class MyDefenceNode(LLMForwardingMixin, BaseAdversarialNode):
        async def execute(self, state, runtime_config=None):
            defence = ... # run normal defence logic
            defence = await self.maybe_forward_to_llm(defence, prompt_text, runtime_config)
            return {"current_turn": {"defence": defence}}

NODE_PARAMS EXPECTED:
    enable_llm_forwarding : bool   — toggle (default: False)
    llm_provider_name     : str    — "ollama" | "gemini" | "openai" (default: "ollama")
    model                 : str    — model identifier (default: "llama3.2:latest")

TOGGLING:
    enable_llm_forwarding=False → mixin is a no-op, original defence returned unchanged.
    enable_llm_forwarding=True  → LLM called only when prompt is NOT blocked.

SCHEMA FRAGMENT (add to each defence node's get_node_schema):
    Use LLMForwardingMixin.schema_fragment() to get the properties dict.
================================================================================
"""

from typing import Dict, Any, Optional
from engine.debug_utils import debug, step, warn, err, tracer
from engine.domain_models import DefencePayload


class LLMForwardingMixin:
    """
    Mixin that adds optional LLM forwarding to any defence node.
    Add before BaseAdversarialNode in the MRO:
        class MyNode(LLMForwardingMixin, BaseAdversarialNode): ...
    """

    def _init_llm_forwarding(self, node_params: Dict[str, Any]) -> None:
        """
        Call this inside __init__ after super().__init__() to set up the mixin.
        """
        self._llm_forwarding_enabled: bool = node_params.get("enable_llm_forwarding", False)
        self._llm_provider_name: str = node_params.get("llm_provider_name", "ollama")
        self._llm_model: str = node_params.get("model", "llama3.2:latest")
        self._llm_provider = None  # lazy-initialised on first use

        if self._llm_forwarding_enabled:
            step(
                "LLM forwarding enabled",
                provider=self._llm_provider_name,
                model=self._llm_model,
            )
        else:
            debug("LLM forwarding disabled")

    def _get_llm_provider(self):
        """Lazy-initialise the LLM provider (avoids loading at startup when disabled)."""
        if self._llm_provider is None:
            from engine.provider_registry import get_provider_registry
            # Build a minimal config the provider expects
            provider_config = {
                "node_params": {
                    "model": self._llm_model,
                    "llm_provider_name": self._llm_provider_name,
                },
                "model": self._llm_model,
            }
            self._llm_provider = get_provider_registry().get(
                self._llm_provider_name,
                config=provider_config,
            )
            step("LLM provider initialised for forwarding", provider=self._llm_provider_name)
        return self._llm_provider

    async def maybe_forward_to_llm(
        self,
        defence: DefencePayload,
        prompt_text: str,
        runtime_config: Optional[Dict[str, Any]] = None,
    ) -> DefencePayload:
        """
        If forwarding is enabled AND the defence did not block the prompt,
        call the LLM and replace defence.response_text with the LLM's response.

        Args:
            defence:        The DefencePayload produced by the defence node.
            prompt_text:    The raw attack/prompt string to forward to the LLM.
            runtime_config: Optional runtime overrides (can override enable_llm_forwarding).

        Returns:
            The (potentially updated) DefencePayload.
            If disabled or prompt was blocked, returns defence unchanged.
        """
        if runtime_config is None:
            runtime_config = {}
        tracer("LLMForwardingMixin.maybe_forward_to_llm")

        # Allow runtime override of the toggle
        enabled = runtime_config.get("enable_llm_forwarding", self._llm_forwarding_enabled)

        if not enabled:
            debug("LLM forwarding disabled — returning original defence")
            return defence

        if defence.was_blocked():
            debug("Prompt was blocked by defence — skipping LLM forwarding")
            return defence

        # Prompt passed the defence — forward to LLM
        step("Forwarding allowed prompt to LLM", provider=self._llm_provider_name, model=self._llm_model)

        try:
            provider = self._get_llm_provider()
            llm_response_text = await provider.generate(
                prompt_text,
                temperature=0.7,
                max_tokens=1000,
            )

            # Replace response_text in-place on a new DefencePayload
            # (domain models are likely frozen/dataclass — rebuild via factory)
            from engine.domain_models import create_defence_response
            updated_defence = create_defence_response(
                text=llm_response_text,
                status_code=defence.status_code,   # keep original block decision
                headers=defence.headers,
                # Carry over all original metadata and add forwarding markers
                **{k: v for k, v in defence.metadata.items()
                   if k not in ("text", "status_code", "headers")},
                llm_forwarded=True,
                llm_provider=self._llm_provider_name,
                llm_model=self._llm_model,
            )

            step(
                "LLM response received",
                response_length=len(llm_response_text),
                provider=self._llm_provider_name,
            )
            return updated_defence

        except Exception as e:
            err("LLM forwarding failed — returning original defence response", error=str(e))
            # On failure, return original defence unchanged rather than crashing
            return defence

    @staticmethod
    def llm_forwarding_schema_fragment() -> Dict[str, Any]:
        """
        Returns the schema properties dict for LLM forwarding params.
        Merge this into each defence node's get_node_schema() properties.
        """
        return {
            "enable_llm_forwarding": {
                "type": "boolean",
                "description": (
                    "When enabled, prompts that pass the defence are forwarded to an LLM "
                    "and the LLM's response replaces the defence placeholder text. "
                    "This gives evaluation nodes a real response to score."
                ),
                "default": False,
            },
            "llm_provider_name": {
                "type": "string",
                "description": "LLM provider to use for forwarding (only used when enable_llm_forwarding=true).",
                "enum": ["ollama", "gemini", "openai"],
                "default": "ollama",
            },
            "model": {
                "type": "string",
                "description": "Model name for the forwarding LLM (e.g. 'llama3.2:latest', 'gemini-1.5-flash').",
                "default": "huihui_ai/dolphin3-abliterated:latest",
            },
        }
