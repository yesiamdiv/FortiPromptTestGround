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


class IterativeImprovementStrategy(AttackStrategy):
    """
    Strategy that iteratively improves attack prompts based on evaluation feedback.
    
    Workflow:
    1. First turn: Use generator_prompt to create initial attack
    2. Subsequent turns: Use improver_prompt with previous attack + feedback
    3. Track best score and continue until max_iterations or success
    """
    
    def __init__(self, provider, config: Dict[str, Any] = None):
        """
        Initialize strategy with LLM provider.
        
        Args:
            provider: LLM provider instance (OllamaProvider, GeminiProvider, etc.)
            config: Configuration including:
                - max_iterations: Maximum refinement iterations (default: 5)
                - target_score: Score threshold for success (default: 0.8)
                - temperature: LLM temperature (default: 0.9)
        """
        default_config = {
            "max_iterations": 5,
            "target_score": 0.8,
            "temperature": 0.9,
            "max_tokens": 500
        }
        
        if config:
            default_config.update(config)
        
        super().__init__(default_config)
        
        self.provider = provider
        self._load_prompts()
    
    def setup(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Initialize strategy context.
        
        Sets up tracking for iterations, scores, and attack history.
        """
        intent = payload.get("intent", "unknown intent")
        
        return {
            "strategy_context": {
                "intent": intent,
                "iteration_count": 0,
                "max_iterations": self.config["max_iterations"],
                "target_score": self.config["target_score"],
                
                # Memory of attempts
                "attack_history": [],
                "best_score": 0.0,
                "best_attack": None,
                
                # Track if we've achieved target
                "target_achieved": False
            },
            "routing_signal": RoutingSignals.CONTINUE
        }
    
    def initialize(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Initialize the strategy, potentially loading resources or setting up context.
        
        Args:
            state: Current system state.
        
        Returns:
            Modified state dictionary.
        """
        print(f"Initializing IterativeImprovementStrategy...")
        # Ensure prompts are loaded (should be done in __init__, but can be reloaded here if needed)
        # self._load_prompts() 
        
        # If the strategy needs to perform setup based on initial payload or config,
        # it can be done here.
        # Example: Load initial attack prompt if provided in payload
        if 'initial_attack_prompt' in state.get('payload', {}):
            context = state.get('strategy_context', {{}})
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
        
        # Determine which prompt to use
        if iteration == 0 or not context.get("attack_history"):
            # First attack: generate fresh
            attack_text = await self._generate_initial_attack(context)
        else:
            # Subsequent attacks: improve based on feedback
            attack_text = await self._generate_improved_attack(context, state)
        
        # Create attack payload
        attack = create_simple_attack(
            attack_text,
            strategy="iterative_improvement",
            iteration=iteration + 1,
            llm_model=self.provider.get_model_name()
        )
        
        # Create turn data
        turn = create_turn_data(turn_id, "attack")
        turn["attack"] = attack
        
        # Update context - store this attempt
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
        """
        Generate initial attack using generator_prompt.
        
        Args:
            context: Strategy context
        
        Returns:
            Generated attack text
        """
        prompt = self.generator_prompt.format(
            intent=context["intent"],
            initial_attack_prompt=context.get('initial_attack_prompt', 'Develop a novel attack.') # Use provided initial prompt or fallback
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
        """
        Generate improved attack using improver_prompt and previous feedback.
        
        Args:
            context: Strategy context with history
            state: Full state with previous turn data
        
        Returns:
            Improved attack text
        """
        # Get previous attempt data
        previous_attempt = context["attack_history"][-1]
        previous_attack = previous_attempt["attack_text"]
        
        # Get previous evaluation (from last completed turn)
        current_turn = state.get("current_turn", {})
        evaluation = current_turn.get("evaluation")
        defence = current_turn.get("defence")
        
        # Build feedback strings
        defence_response = defence.get_text() if defence else "No response"
        evaluation_feedback = evaluation.get_reasoning() if evaluation else "No feedback"
        score = evaluation.get_score() if evaluation else 0.0
        
        # Format improver prompt
        prompt = self.improver_prompt.format(
            intent=context["intent"],
            previous_attack=previous_attack,
            defence_response=defence_response,
            evaluation_feedback=evaluation_feedback,
            score=score
        )
        
        # Generate improved attack
        improved_text = await self.provider.generate(
            prompt,
            temperature=self.config["temperature"],
            max_tokens=self.config["max_tokens"]
        )
        
        return improved_text.strip()
    
    def process_end_of_loop(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process evaluation and decide whether to continue.
        
        Stops if:
        - Target score achieved
        - Max iterations reached
        - Evaluation indicates success
        """
        context = state["strategy_context"]
        current_turn = state.get("current_turn", {})
        evaluation = current_turn.get("evaluation")
        
        if not evaluation:
            # No evaluation yet, continue
            return {
                "strategy_context": context,
                "routing_signal": RoutingSignals.ATTACK
            }
        
        # Update best score tracking
        current_score = evaluation.get_score()
        if current_score > context["best_score"]:
            context["best_score"] = current_score
            context["best_attack"] = context["attack_history"][-1]["attack_text"]
        
        # Check if target achieved
        if current_score >= context["target_score"] or evaluation.is_success():
            context["target_achieved"] = True
            should_continue = False
        elif context["iteration_count"] >= context["max_iterations"]:
            # Max iterations reached
            should_continue = False
        else:
            # Continue improving
            should_continue = True
        
        return {
            "strategy_context": context,
            "routing_signal": RoutingSignals.ATTACK if should_continue else RoutingSignals.END
        }
    
    def get_status_summary(self, state: Dict[str, Any]) -> str:
        """Get human-readable status"""
        context = state.get("strategy_context", {})
        return (
            f"IterativeImprovement: "
            f"{context.get('iteration_count', 0)}/{context.get('max_iterations', 0)} iterations, "
            f"Best score: {context.get('best_score', 0.0):.2f}, "
            f"Target: {context.get('target_score', 0.0):.2f}"
        )

    def route(self, state: Dict[str, Any]) -> str:
        """Determine the next routing signal based on the current state."""
        context = state.get("strategy_context", {})
        evaluation = state.get("current_turn", {}).get("evaluation")
        
        # Check if target score is met or max iterations reached
        if context.get("target_achieved", False):
            return RoutingSignals.END
        elif context.get("iteration_count", 0) >= context.get("max_iterations", 0):
            return RoutingSignals.END
        
        # If evaluation is missing, continue to generate/improve
        if not evaluation:
            return RoutingSignals.ATTACK

        # Otherwise, continue if not met target and not max iterations
        # This logic is already in process_end_of_loop, so we can rely on that state update
        return state.get("routing_signal", RoutingSignals.ATTACK)
