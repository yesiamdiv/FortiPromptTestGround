"""
Iterative Improvement Strategy

Iterative Improvement Strategy

Key Features:
- Maintains memory of previous attempts
- Uses different instruction prompts for generation vs improvement
- Makes multiple LLM calls per turn if needed
- Tracks iteration count and best scores
"""

from typing import Dict, Any
import json
from pathlib import Path
from strategies.base import AttackStrategy
from engine.domain_models import create_simple_attack
from engine.state_schema import create_turn_data, RoutingSignals, update_turn_data
from engine.provider_registry import get_provider_registry # Import the registry


class IterativeImprovementStrategy(AttackStrategy):
    """
    Strategy that iteratively improves attack prompts based on evaluation feedback.
    
    Workflow:
    1. First turn: Use generator_prompt to create initial attack
    2. Subsequent turns: Use improver_prompt with previous attack + feedback
    3. Track best score and continue until max_iterations or success
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {
            "max_iterations": 5,
            "target_score": 0.8,
            "temperature": 0.9,
            "max_tokens": 500,
            "llm_provider_name": "ollama" # Default provider name
        }
        
        if config:
            default_config.update(config)
        
        super().__init__(default_config)
        
        # Fetch provider using the registry and config
        provider_name = self.config.get("llm_provider_name", "ollama")
        self.provider = get_provider_registry().get(provider_name, config=self.config)
        self._load_prompts()
    
    def initialize(self, state: Dict[str, Any]) -> Dict[str, Any]:
        print(f"Initializing IterativeImprovementStrategy...")
        intent = state.get("payload", {}).get("intent", "unknown intent")
        
        if "strategy_context" not in state or not state["strategy_context"]:
            state["strategy_context"] = {}
            
        state["strategy_context"].update({
            "intent": intent,
            "iteration_count": 0,
            "max_iterations": self.config.get("max_iterations", 5),
            "target_score": self.config.get("target_score", 0.8),
            
            "attack_history": [],
            "best_score": 0.0,
            "best_attack": None,
            
            "target_achieved": False
        })
        
        if "routing_signal" not in state:
            state["routing_signal"] = RoutingSignals.CONTINUE
            
        if 'initial_attack_prompt' in state.get('payload', {}):
            context = state.get('strategy_context', {})
            context['initial_attack_prompt'] = state['payload']['initial_attack_prompt']
            state['strategy_context'] = context
            
        return state

    async def execute_generation(self, state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate attack using LLM.
        
        First iteration: Use generator_prompt
        Subsequent iterations: Use improver_prompt with feedback
        
        The strategy makes all LLM calls here - the attack node just delegates.
        """
        context = state["strategy_context"]
        iteration = context["iteration_count"]
        turn_id = f"turn_{iteration + 1}"
        
        if iteration == 0 or not context.get("attack_history"):
            attack_text = await self._generate_initial_attack(context)
        else:
            attack_text = await self._generate_improved_attack(context, state)
        
        attack = create_simple_attack(
            attack_text,
            strategy="iterative_improvement",
            iteration=iteration + 1,
            llm_model=self.provider.get_model_name()
        )
        
        turn = create_turn_data(turn_id, "attack")
        turn["attack"] = attack
        
        context["attack_history"].append({
            "iteration": iteration + 1,
            "attack_text": attack_text,
            "turn_id": turn_id
        })
        context["iteration_count"] = iteration + 1
        
        return {
            "current_turn": turn,
            "strategy_context": context
        }
    
    async def _generate_initial_attack(self, context: Dict[str, Any]) -> str:
        prompt = self.generator_prompt.format(
            intent=context["intent"],
            initial_attack_prompt=context.get('initial_attack_prompt', 'Develop a novel attack.')
        )
        
        attack_text = await self.provider.generate(
            prompt,
            temperature=self.config["temperature"],
            max_tokens=self.config["max_tokens"]
        )
        
        return attack_text.strip()
    
    async def _generate_improved_attack(
        self,
        context: Dict[str, Any],
        state: Dict[str, Any]
    ) -> str:
        previous_attempt = context["attack_history"][-1]
        previous_attack = previous_attempt["attack_text"]
        
        current_turn = state.get("current_turn", {})
        evaluation = current_turn.get("evaluation")
        defence = current_turn.get("defence")
        
        defence_response = defence.get_text() if defence else "No response"
        evaluation_feedback = evaluation.get_reasoning() if evaluation else "No feedback"
        score = evaluation.get_score() if evaluation else 0.0
        
        prompt = self.improver_prompt.format(
            intent=context["intent"],
            previous_attack=previous_attack,
            defence_response=defence_response,
            evaluation_feedback=evaluation_feedback,
            score=score
        )
        
        improved_text = await self.provider.generate(
            prompt,
            temperature=self.config["temperature"],
            max_tokens=self.config["max_tokens"]
        )
        
        return improved_text.strip()
    
    def route(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Determine the next routing signal and update context based on state and evaluation."""
        context = state.get("strategy_context", {})
        current_turn = state.get("current_turn", {})
        evaluation = current_turn.get("evaluation")
        
        updated_context = context.copy()

        if not evaluation:
            signal = RoutingSignals.ATTACK
        else:
            current_score = evaluation.get_score()
            if current_score > updated_context.get("best_score", 0.0):
                updated_context["best_score"] = current_score
                updated_context["best_attack"] = context["attack_history"][-1]["attack_text"]
            
            if current_score >= updated_context.get("target_score", 0.8) or evaluation.is_success():
                updated_context["target_achieved"] = True
                should_continue = False
            elif updated_context.get("iteration_count", 0) >= updated_context.get("max_iterations", 5):
                should_continue = False
            else:
                should_continue = True
            
            signal = RoutingSignals.ATTACK if should_continue else RoutingSignals.END

        return {
            "routing_signal": signal,
            "strategy_context": updated_context
        }

    @classmethod
    def get_dependency_schema(cls) -> Dict[str, Any]:
        """
        Return a JSON schema defining the strategy's dependencies.
        This is used by the frontend to render input fields for required parameters.
        """
        # This strategy requires an LLM provider, configured by 'llm_provider_name'
        # and potentially other provider-specific parameters passed via config.
        return {
            "type": "object",
            "properties": {
                "llm_provider_name": {
                    "type": "string",
                    "description": "Name of the LLM provider to use (e.g., 'ollama', 'gemini')",
                    "enum": ["ollama", "gemini", "openai"], # Example providers
                },
                "max_iterations": {
                    "type": "integer",
                    "description": "Maximum number of iterations for iterative improvement.",
                    "default": 5
                },
                "target_score": {
                    "type": "number",
                    "description": "The target score to achieve for ending the iteration.",
                    "default": 0.8
                },
                "temperature": {
                    "type": "number",
                    "description": "The temperature for LLM generation.",
                    "default": 0.9
                },
                "max_tokens": {
                    "type": "integer",
                    "description": "Maximum tokens for LLM generation.",
                    "default": 500
                }
            },
            "required": ["llm_provider_name"],
        }
