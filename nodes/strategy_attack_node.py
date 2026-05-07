"""
Refactored Attack Node

The attack node simply delegates to the strategy - it doesn't make LLM calls itself.
The strategy has full control over LLM interactions, allowing for complex multi-call
patterns, data processing, and custom workflows.
"""

from typing import Dict, Any
from nodes.base import BaseAdversarialNode, StrategyProxyNode
from engine.debug_utils import debug, tracer, step, warn, err


class StrategyDrivenAttackNode(StrategyProxyNode):
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
        tracer("StrategyDrivenAttackNode.execute")
        strategy = self.config.get('strategy')
        
        if not strategy:
            err("Strategy instance not found in Attack Node config")
            raise AttributeError("Strategy instance not found in Attack Node's config.")
            
        debug("Delegating to strategy execute_generation", strategy_type=type(strategy).__name__)
        result = await strategy.execute_generation(state, config)
        step("Attack generation complete", result_keys=list(result.keys()))
        return result