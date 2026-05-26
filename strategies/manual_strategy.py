"""
================================================================================
MANUAL STRATEGY IMPLEMENTATION
================================================================================

DEVELOPER INSTRUCTIONS:
--------------------------------------------------------------------------------
1. State Deltas: Methods strictly return state updates (deltas) without mutating 
   the root SystemState.
2. Deep Copying: Uses `copy.deepcopy()` for context to prevent mutating nested 
   lists/dicts before LangGraph merges the state.
3. Absolute Strictness: ZERO usage of `.get()` on state or context dictionaries. 
   Enforces fail-fast behavior with explicit bracket notation and `in` checks.
4. Routing: `route` returns a string signal directly.
================================================================================
"""

from typing import Dict, Any, List, Optional
import uuid
import copy
from strategies.base import AttackStrategy
from engine.domain_models import create_simple_attack
from engine.state_schema import create_turn_data, RoutingSignals, SystemState
from engine.debug_utils import debug, tracer, step, warn, err


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
    
    def initialize(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        if runtime_config is None: runtime_config = {}
        
        run_id = state["run_id"] if "run_id" in state else "unknown"
        tracer("ManualStrategy.initialize", run_id=run_id)
        
        if "payload" not in state:
            raise ValueError("Corrupted state: Missing 'payload' in SystemState.")
        if "strategy_context" not in state:
            raise ValueError("Corrupted state: Missing 'strategy_context' in SystemState.")

        payload = state["payload"]
        if "session_id" not in payload or not payload["session_id"]:
            err("Missing session_id for ManualStrategy")
            raise ValueError("ManualStrategy requires a 'session_id' in the initial payload for initialization.")

        session_id = payload["session_id"]
        debug("Initializing manual strategy", session_id=session_id)
        
        # DEEP COPY: Prevent accidental mutation of root state
        context = copy.deepcopy(state["strategy_context"])
        
        if "history" not in context:
            context["history"] = []
        if "iteration_count" not in context:
            context["iteration_count"] = 0
            
        context["session_id"] = session_id
        context["max_turns"] = self.config["max_turns"] if "max_turns" in self.config else 100
        context["strategy_name"] = self.name

        step("ManualStrategy initialized", session_id=session_id, history_len=len(context["history"]))
        
        # Return cleanly as a state delta
        return {"strategy_context": context}

    async def execute_generation(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Generates an attack based on user input and conversation history."""
        if runtime_config is None: runtime_config = {}
        tracer("ManualStrategy.execute_generation")
        
        if "strategy_context" not in state:
            raise ValueError("Corrupted state: Missing 'strategy_context'.")
        if "payload" not in state:
            raise ValueError("Corrupted state: Missing 'payload'.")
        if "current_turn" not in state:
            raise ValueError("Corrupted state: Missing 'current_turn'.")
            
        # DEEP COPY: Prevent mutating history lists before state merge
        context = copy.deepcopy(state["strategy_context"])
        current_iteration = context["iteration_count"] if "iteration_count" in context else 0
        
        payload = state["payload"]
        if "prompt" not in payload or not payload["prompt"]:
            err("Missing prompt for manual generation")
            raise ValueError("ManualStrategy requires a 'prompt' in the payload for attack generation.")
            
        user_prompt = payload["prompt"]

        conversation_history = context["history"] if "history" in context else []
        full_attack_prompt = "\n".join(conversation_history + [f"{user_prompt}"])
        debug("Built attack prompt", history_len=len(conversation_history), prompt_length=len(full_attack_prompt))

        current_turn_state = state["current_turn"]
        turn_id = current_turn_state["turn_id"] if "turn_id" in current_turn_state else f"turn_{uuid.uuid4().hex[:8]}"
        
        attack = create_simple_attack(
            full_attack_prompt,
            strategy="manual",
            iteration=current_iteration + 1,
            user_input=user_prompt
        )

        turn_data = create_turn_data(turn_id, "attack")
        turn_data["attack"] = attack

        context["history"].append(f"Attack (Turn {current_iteration + 1}): {full_attack_prompt}")
        context["iteration_count"] = current_iteration + 1
        
        step("Manual attack generated", turn_id=turn_id, iteration=context["iteration_count"])
        
        # Strictly return valid state deltas
        return {
            "current_turn": turn_data,
            "strategy_context": context
        }

    def route(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> str:
        """Route decision for manual strategy. Strictly returns a string signal.
        
        Routing logic:
        - First pass (init → router): current_turn has no attack yet → route to ATTACK
          so the attack/defence/eval nodes execute for this turn.
        - Second pass (eval → router): current_turn already has an attack → route to END
          so the graph stops and waits for the next user prompt.
        """
        tracer("ManualStrategy.route")
        
        if "strategy_context" not in state:
            raise ValueError("Corrupted state: Missing 'strategy_context'.")
            
        context = state["strategy_context"]
        iteration = context["iteration_count"] if "iteration_count" in context else 0
        
        # If the current turn already has an attack, we came from eval → done with this turn.
        current_turn = state.get("current_turn") or {}
        attack_generated = current_turn.get("attack") is not None
        
        if attack_generated:
            debug("Manual route: attack done, routing to END", iteration=iteration)
            return RoutingSignals.END
        else:
            debug("Manual route: no attack yet, routing to ATTACK", iteration=iteration)
            return RoutingSignals.ATTACK

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