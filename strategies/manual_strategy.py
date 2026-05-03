"""
Manual Strategy Implementation

This strategy is designed for human-in-the-loop interaction.
"""

from typing import Dict, Any, List, Optional
from strategies.base import AttackStrategy
from engine.domain_models import create_simple_attack
from engine.state_schema import create_turn_data, RoutingSignals, SystemState
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
        print(f"Initializing ManualStrategy for run: {state.get('run_id')}")
        
        # Retrieve session_id from initial_state payload
        session_id = state.get("payload", {}).get("session_id")
        if not session_id:
            raise ValueError("ManualStrategy requires a 'session_id' in the initial payload for initialization.")

        # Hydrate strategy_context from previous turns via initial_state if available
        # The ManualDatabaseMiddleware should have already hydrated this.
        strategy_context = state.get("strategy_context", {})
        
        # Ensure history is present and iteration_count is correct
        if "history" not in strategy_context:
            strategy_context["history"] = [] # History of past attack prompts & responses
        if "iteration_count" not in strategy_context:
            strategy_context["iteration_count"] = 0
            
        # Add current session_id to context for easy access
        strategy_context["session_id"] = session_id
        strategy_context["max_turns"] = self.config.get("max_turns", 100)

        state["strategy_context"] = strategy_context
        state["routing_signal"] = RoutingSignals.CONTINUE # Always continue to attack initially

        return state

    async def execute_generation(self, state: SystemState, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates an attack based on user input and conversation history.
        """
        strategy_context = state["strategy_context"]
        current_iteration = strategy_context["iteration_count"]
        session_id = strategy_context["session_id"]
        
        # The prompt for this turn comes directly from the user payload.
        user_prompt = state.get("payload", {}).get("prompt")
        if not user_prompt:
            raise ValueError("ManualStrategy requires a 'prompt' in the payload for attack generation.")

        # Accumulate history: Frontend might send full history, or middleware hydrates it.
        # Assume middleware hydrates initial history, and we just append.
        conversation_history = strategy_context.get("history", [])
        
        # The full attack prompt for this turn includes past context + new user prompt
        full_attack_prompt = "\n".join(conversation_history + [f"User Input: {user_prompt}"])

        # Create AttackData
        turn_id = state.get("current_turn", {}).get("turn_id", f"turn_{uuid.uuid4().hex[:8]}")
        attack = create_simple_attack(
            full_attack_prompt,
            strategy="manual",
            iteration=current_iteration + 1,
            user_input=user_prompt # Store original user input as metadata
        )

        turn_data = create_turn_data(turn_id, "attack")
        turn_data["attack"] = attack

        # Update strategy_context with the new turn's data for persistence
        strategy_context["history"].append(f"Attack (Turn {current_iteration + 1}): {full_attack_prompt}")
        strategy_context["iteration_count"] += 1
        
        return {
            "current_turn": turn_data,
            "strategy_context": strategy_context,
            "session_id": session_id # Ensure session_id is propagated for middleware
        }

    def route(self, state: SystemState) -> Dict[str, Any]:
        """
        For a manual strategy, after one turn (Attack -> Defence -> Eval), we always end.
        The system then waits for the next user input to re-start the process.
        """
        strategy_context = state.get("strategy_context", {})
        
        # Always end a single manual turn, letting the RunManager/Middleware handle the IDLE state
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
