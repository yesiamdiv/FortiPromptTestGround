"""
Manual Strategy Implementation

This strategy is designed for human-in-the-loop interaction.
"""

from typing import Dict, Any, List, Optional
from strategies.base import AttackStrategy
from engine.domain_models import create_simple_attack
from engine.state_schema import create_turn_data, RoutingSignals, SystemState
from engine.debug_utils import debug, tracer, step, warn, err
import uuid


class ManualStrategy(AttackStrategy):
    """
    Strategy for manual, human-in-the-loop interaction.
    
    Each execution represents a single turn in a manual session.
    It relies on external input to drive the next attack.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {"max_turns": 100} # Max turns for the whole session
        if config:
            default_config.update(config)
        super().__init__(default_config)
    
    def initialize(self, state: SystemState) -> Dict[str, Any]:
        tracer("ManualStrategy.initialize", run_id=state.get('run_id'))
        
        session_id = state.get("payload", {}).get("session_id")
        if not session_id:
            err("Missing session_id for ManualStrategy")
            raise ValueError("ManualStrategy requires a 'session_id' in the initial payload for initialization.")

        debug("Initializing manual strategy", session_id=session_id)
        strategy_context = state.get("strategy_context", {})
        
        if "history" not in strategy_context:
            strategy_context["history"] = []
        if "iteration_count" not in strategy_context:
            strategy_context["iteration_count"] = 0
            
        strategy_context["session_id"] = session_id
        strategy_context["max_turns"] = self.config.get("max_turns", 100)

        state["strategy_context"] = strategy_context
        state["routing_signal"] = RoutingSignals.CONTINUE

        step("ManualStrategy initialized", session_id=session_id, history_len=len(strategy_context["history"]))
        return state

    async def execute_generation(self, state: SystemState, config: Dict[str, Any]) -> Dict[str, Any]:
        """Generates an attack based on user input and conversation history."""
        tracer("ManualStrategy.execute_generation")
        strategy_context = state["strategy_context"]
        current_iteration = strategy_context["iteration_count"]
        session_id = strategy_context["session_id"]
        
        user_prompt = state.get("payload", {}).get("prompt")
        if not user_prompt:
            err("Missing prompt for manual generation")
            raise ValueError("ManualStrategy requires a 'prompt' in the payload for attack generation.")

        conversation_history = strategy_context.get("history", [])
        full_attack_prompt = "\n".join(conversation_history + [f"User Input: {user_prompt}"])
        debug("Built attack prompt", history_len=len(conversation_history), prompt_length=len(full_attack_prompt))

        turn_id = state.get("current_turn", {}).get("turn_id", f"turn_{uuid.uuid4().hex[:8]}")
        attack = create_simple_attack(
            full_attack_prompt,
            strategy="manual",
            iteration=current_iteration + 1,
            user_input=user_prompt
        )

        turn_data = create_turn_data(turn_id, "attack")
        turn_data["attack"] = attack

        strategy_context["history"].append(f"Attack (Turn {current_iteration + 1}): {full_attack_prompt}")
        strategy_context["iteration_count"] += 1
        
        step("Manual attack generated", turn_id=turn_id, iteration=strategy_context["iteration_count"])
        return {
            "current_turn": turn_data,
            "strategy_context": strategy_context,
            "session_id": session_id
        }

    def route(self, state: SystemState) -> Dict[str, Any]:
        """Route decision for manual strategy."""
        tracer("ManualStrategy.route")
        strategy_context = state.get("strategy_context", {})
        debug("Manual route: always END", iteration=strategy_context.get("iteration_count"))
        return {
            "routing_signal": RoutingSignals.END,
            "strategy_context": strategy_context
        }

    @classmethod
    def get_dependency_schema(cls) -> Dict[str, Any]:
        """
        Manual strategy typically relies on external user input, so its config is minimal.
        """
        return {
            "type": "object",
            "properties": {
                "max_turns": {
                    "type": "integer",
                    "description": "Maximum number of turns in a manual session.",
                    "default": 100
                }
            },
            "required": [],
        }
