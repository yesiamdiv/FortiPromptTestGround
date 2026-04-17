"""
Production Attack Node

Uses actual LLM providers to generate attacks based on strategy output.
"""

from typing import Dict, Any
from nodes.base import BaseAdversarialNode
from engine.domain_models import create_simple_attack
from engine.state_schema import update_turn_data


class LLMAttackNode(BaseAdversarialNode):
    """
    Attack node that uses LLM providers for attack generation.
    
    The strategy can either:
    1. Generate the full attack itself (strategy does all the work)
    2. Provide a prompt in metadata for LLM enhancement
    """
    
    def __init__(self, provider, config: Dict[str, Any] = None):
        """
        Initialize with an LLM provider.
        
        Args:
            provider: An LLM provider instance (OllamaProvider, GeminiProvider, etc.)
            config: Additional configuration
        """
        super().__init__(config)
        self.provider = provider
    
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate attack using strategy and optionally enhance with LLM.
        
        Workflow:
        1. Call strategy.execute_generation() to get base attack
        2. If attack has 'llm_prompt' in metadata, use LLM to enhance it
        3. Otherwise, use attack as-is
        
        Args:
            state: Current system state
            config: Runtime configuration containing strategy
        
        Returns:
            Updated current_turn with attack payload
        """
        # Get strategy from config
        strategy = config["configurable"]["strategy"]
        
        # Strategy generates the base attack
        result = strategy.execute_generation(state)
        
        # Extract attack from result
        current_turn = result["current_turn"]
        attack = current_turn.get("attack")
        
        if not attack:
            raise ValueError("Strategy did not return an attack payload")
        
        # Check if strategy wants LLM enhancement
        if "llm_prompt" in attack.metadata:
            llm_prompt = attack.metadata["llm_prompt"]
            
            # Use LLM to generate enhanced attack
            enhanced_text = await self.provider.generate(
                llm_prompt,
                temperature=attack.metadata.get("temperature", 0.9),
                max_tokens=attack.metadata.get("max_tokens", 500)
            )
            
            # Create new attack with LLM output
            enhanced_attack = create_simple_attack(
                enhanced_text,
                metadata={
                    **attack.metadata,
                    "llm_model": self.provider.get_model_name(),
                    "original_attack": attack.to_string(),
                    "llm_enhanced": True
                }
            )
            
            # Update turn with enhanced attack
            current_turn["attack"] = enhanced_attack
            result["current_turn"] = current_turn
        
        return result
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Get information about the LLM provider"""
        return {
            "model": self.provider.get_model_name(),
            "config": self.provider.get_config()
        }
