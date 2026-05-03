"""
Refactored Attack Node

The attack node simply delegates to the strategy - it doesn't make LLM calls itself.
The strategy has full control over LLM interactions, allowing for complex multi-call
patterns, data processing, and custom workflows.
"""

from typing import Dict, Any
from nodes.base import BaseAdversarialNode
from engine.state_schema import SystemState


class LLMAttackNode(BaseAdversarialNode):
    """
    Attack node that fully delegates to strategy.
    
    The strategy is responsible for:
    - Making LLM calls (single or multiple)
    - Processing data
    - Managing complex workflows
    - Storing intermediate results
    
    This node simply calls the strategy's execute_generation method.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
    
    async def execute(self, state: SystemState, runtime_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute attack generation by delegating to strategy.
        
        Args:
            state: Current system state
            runtime_config: Runtime configuration containing strategy
        
        Returns:
            Updated state with new attack payload
        """
        # Get strategy from self.config, as it's baked in during node instantiation
        strategy = self.config.get('strategy')
        if not strategy:
            raise AttributeError("Strategy instance not found in node's self.config.")
        
        # Strategy does everything - LLM calls, processing, etc.
        # Pass state and runtime_config to the strategy method
        result = await strategy.execute_generation(state, runtime_config)
        
        return result
