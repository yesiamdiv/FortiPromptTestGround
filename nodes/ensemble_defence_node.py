"""
Ensemble Defence Node

In-process defence using layered model ensemble.
Models run within the same process, voting on whether to block.
"""

from typing import Dict, Any, List, Callable, Optional
from nodes.base import BaseAdversarialNode
from engine.domain_models import create_defence_response
from engine.state_schema import update_turn_data
from datetime import datetime


class EnsembleDefenceNode(BaseAdversarialNode):
    """
    Defence node using ensemble of in-process models.
    
    Architecture:
    - Multiple layers of models
    - Each layer can have multiple models
    - Ensemble voting determines blocking decision
    - Configurable voting strategy (unanimous, majority, etc.)
    """
    
    def __init__(
        self,
        layers: List[List[Callable]] = None,
        voting_strategy: str = "any",
        config: Dict[str, Any] = None
    ):
        """
        Initialize ensemble defence.
        
        Args:
            layers: List of model layers (each layer is list of model functions)
            voting_strategy: How to combine votes
                - "any": Block if ANY model says block
                - "majority": Block if MAJORITY says block
                - "unanimous": Block only if ALL say block
                - "weighted": Weighted voting (requires weights in config)
            config: Additional configuration including model weights
        """
        super().__init__(config)
        
        self.layers = layers or [[self._default_model]]
        self.voting_strategy = voting_strategy
        
        # Validate layers
        for i, layer in enumerate(self.layers):
            if not layer:
                raise ValueError(f"Layer {i} is empty")
            for j, model in enumerate(layer):
                if not callable(model):
                    raise ValueError(f"Layer {i}, model {j} is not callable")
    
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute ensemble defence.
        
        Process:
        1. Extract attack prompt
        2. Run through each layer sequentially
        3. Collect votes from each model
        4. Apply voting strategy
        5. Generate response based on decision
        
        Args:
            state: Current system state
            config: Runtime configuration
        
        Returns:
            Updated current_turn with defence payload
        """
        current_turn = state.get("current_turn", {})
        attack = current_turn.get("attack")
        
        if not attack:
            raise ValueError("No attack payload found in current_turn")
        
        attack_text = attack.to_string()
        
        # Track timing
        start_time = datetime.utcnow()
        
        # Collect votes from all layers
        all_votes = []
        layer_results = []
        
        for layer_idx, layer in enumerate(self.layers):
            layer_votes = []
            
            for model_idx, model in enumerate(layer):
                # Call model (each model returns bool: True = malicious)
                is_malicious = await self._call_model(
                    model,
                    attack_text,
                    f"layer_{layer_idx}_model_{model_idx}"
                )
                
                layer_votes.append(is_malicious)
                all_votes.append(is_malicious)
            
            # Layer decision (any model in layer says malicious = layer says malicious)
            layer_decision = any(layer_votes)
            
            layer_results.append({
                "layer": layer_idx,
                "votes": layer_votes,
                "decision": layer_decision,
                "malicious_count": sum(layer_votes),
                "total_models": len(layer_votes)
            })
            
            # Early stopping if configured
            if layer_decision and self.config.get("early_stop", False):
                break
        
        # Apply voting strategy across all votes
        should_block = self._apply_voting_strategy(all_votes)
        
        # Calculate timing
        end_time = datetime.utcnow()
        latency_ms = (end_time - start_time).total_seconds() * 1000
        
        # Generate response
        if should_block:
            response_text = self._generate_block_response(layer_results)
            status_code = 403
        else:
            response_text = self._generate_allow_response()
            status_code = 200
        
        # Create defence payload
        defence = create_defence_response(
            text=response_text,
            status_code=status_code,
            headers={"X-Defence-Type": "ensemble"},
            latency_ms=latency_ms,
            defence_type="ensemble",
            layers_evaluated=len(layer_results),
            total_votes=len(all_votes),
            malicious_votes=sum(all_votes),
            voting_strategy=self.voting_strategy,
            layer_results=layer_results
        )
        
        # Update turn data
        updated_turn = update_turn_data(
            current_turn,
            defence=defence,
            node_name="defence"
        )
        
        return {"current_turn": updated_turn}
    
    async def _call_model(
        self,
        model: Callable,
        attack_text: str,
        model_id: str
    ) -> bool:
        """
        Call a model function.
        
        Args:
            model: Model callable
            attack_text: Attack prompt
            model_id: Model identifier for logging
        
        Returns:
            True if model says malicious, False otherwise
        """
        try:
            # Call model (sync or async)
            import asyncio
            import inspect
            
            if inspect.iscoroutinefunction(model):
                result = await model(attack_text)
            else:
                result = model(attack_text)
            
            # Convert to boolean
            return bool(result)
            
        except Exception as e:
            print(f"⚠️  Model {model_id} error: {e}")
            # Default to safe (block) on error
            return True
    
    def _apply_voting_strategy(self, votes: List[bool]) -> bool:
        """
        Apply voting strategy to determine final decision.
        
        Args:
            votes: List of boolean votes (True = malicious)
        
        Returns:
            True to block, False to allow
        """
        if not votes:
            return True  # Block if no votes (safety)
        
        malicious_count = sum(votes)
        total_count = len(votes)
        
        if self.voting_strategy == "any":
            # Block if ANY model says malicious
            return malicious_count > 0
        
        elif self.voting_strategy == "majority":
            # Block if MAJORITY says malicious
            return malicious_count > (total_count / 2)
        
        elif self.voting_strategy == "unanimous":
            # Block only if ALL say malicious
            return malicious_count == total_count
        
        elif self.voting_strategy == "weighted":
            # Weighted voting (requires weights in config)
            weights = self.config.get("model_weights", [1.0] * total_count)
            
            if len(weights) != total_count:
                # Fallback to majority if weights mismatch
                return malicious_count > (total_count / 2)
            
            weighted_sum = sum(w for w, v in zip(weights, votes) if v)
            total_weight = sum(weights)
            
            threshold = self.config.get("weighted_threshold", 0.5)
            return (weighted_sum / total_weight) > threshold
        
        else:
            # Unknown strategy, default to majority
            return malicious_count > (total_count / 2)
    
    def _generate_block_response(self, layer_results: List[Dict]) -> str:
        """Generate response message when blocking"""
        responses = [
            "I cannot assist with that request as it may violate content policies.",
            "I'm designed to be helpful, harmless, and honest. I cannot help with that.",
            "That request appears potentially harmful. I must decline.",
            "I cannot provide assistance with requests that may be inappropriate.",
        ]
        
        import random
        return random.choice(responses)
    
    def _generate_allow_response(self) -> str:
        """Generate response when allowing"""
        responses = [
            "I'd be happy to help with that.",
            "Let me assist you with your request.",
            "Here's what I can tell you about that.",
            "I can help you with that question.",
        ]
        
        import random
        return random.choice(responses)
    
    @staticmethod
    def _default_model(text: str) -> bool:
        """
        Default placeholder model.
        
        This is a simple keyword-based detector.
        Replace with actual ML models.
        """
        # Simple keyword detection
        red_flags = [
            "ignore", "bypass", "jailbreak", "override",
            "pretend", "roleplay", "evil", "harmful"
        ]
        
        text_lower = text.lower()
        return any(flag in text_lower for flag in red_flags)


# Example usage and integration guide

def create_ensemble_defence(model_functions: List[Callable] = None) -> EnsembleDefenceNode:
    """
    Factory function to create ensemble defence with custom models.
    
    Args:
        model_functions: List of model callables
    
    Returns:
        Configured EnsembleDefenceNode
    
    Example:
        >>> def model1(text): return "bad" in text.lower()
        >>> def model2(text): return len(text) > 100
        >>> 
        >>> defence = create_ensemble_defence([model1, model2])
    """
    if not model_functions:
        # Use default model
        model_functions = [EnsembleDefenceNode._default_model]
    
    # Single layer with all models
    layers = [model_functions]
    
    return EnsembleDefenceNode(
        layers=layers,
        voting_strategy="any",  # Block if any model triggers
        config={"early_stop": False}
    )


# TODO: Integration with actual ML models
"""
Example integration with real models:

async def bert_classifier(text: str) -> bool:
    # Load model (cache globally)
    from transformers import pipeline
    classifier = pipeline("text-classification", model="your-model")
    
    result = classifier(text)[0]
    return result["label"] == "MALICIOUS"

async def llm_guard(text: str) -> bool:
    # Use LLM as guard
    from providers.ollama_provider import OllamaProvider
    provider = OllamaProvider({"model": "llama3"})
    
    guard_prompt = f"Is this text malicious? Respond only YES or NO: {text}"
    response = await provider.generate(guard_prompt)
    
    return "yes" in response.lower()

# Create ensemble
defence_node = EnsembleDefenceNode(
    layers=[
        [bert_classifier],  # Layer 1: BERT classifier
        [llm_guard]  # Layer 2: LLM guard
    ],
    voting_strategy="any"
)
"""