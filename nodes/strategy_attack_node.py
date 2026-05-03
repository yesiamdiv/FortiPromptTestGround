"""
Refactored Attack Node

The attack node simply delegates to the strategy - it doesn't make LLM calls itself.
The strategy has full control over LLM interactions, allowing for complex multi-call
patterns, data processing, and custom workflows.
"""

from typing import Dict, Any
from nodes.base import BaseAdversarialNode


class StrategyDrivenAttackNode(BaseAdversarialNode):
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
        """
        Initialize attack node.
        
        Args:
            config: Optional node configuration
        """
        super().__init__(config)
    
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute attack generation by delegating to strategy.
        
        The strategy has full control and can:
        - Call LLMs multiple times
        - Process responses
        - Store complex data structures in strategy_context
        - Return the final attack payload
        
        Args:
            state: Current system state
            config: Runtime configuration containing strategy
        
        Returns:
            Updated state with new attack payload
        """
        strategy:BaseAdversarialNode = self.config.get('strategy')
        
        if not strategy:
            raise AttributeError("Strategy instance not found in Attack Node's config.")
            
        result = await strategy.execute(state, config)
        return result