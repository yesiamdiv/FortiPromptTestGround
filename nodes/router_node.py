"""
Router Node

This node delegates routing decisions to the strategy.
"""

from typing import Dict, Any
from nodes.base import BaseAdversarialNode, StrategyProxyNode
from engine.state_schema import RoutingSignals, SystemState
from engine.debug_utils import debug, tracer, step, warn, err


class RouterNode(StrategyProxyNode):
    """
    Node responsible for routing decisions based on strategy output.
    It directly calls the strategy's `route` method.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)

    def get_strategy_method(self) -> str:
        return "route"

    async def execute(self, state: SystemState, runtime_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the router node by delegating to the strategy's route method.
        
        Args:
            state: Current system state (SystemState TypedDict).
            runtime_config: Runtime configuration.
        
        Returns:
            Updated state with the routing signal determined by the strategy.
        """
        tracer("RouterNode.execute")
        try:
            strategy = self.config.get('strategy')
            if not strategy:
                raise AttributeError("Strategy instance not found in node's self.config.")
            
            routing_result = strategy.route(state)
            
            if not isinstance(routing_result, dict):
                raise TypeError("Strategy's route method must return a dictionary with 'routing_signal' and 'strategy_context'.")
            
            if "routing_signal" not in routing_result or "strategy_context" not in routing_result:
                raise ValueError("Strategy's route method must return a dictionary containing 'routing_signal' and 'strategy_context'.")

            step("Routing complete", signal=routing_result.get("routing_signal"))
            return routing_result
            
        except AttributeError as e:
            raise AttributeError(f"Strategy error: {e}")
        except (TypeError, ValueError) as e:
            debug("Error in strategy routing method", error=str(e))
            return {"routing_signal": RoutingSignals.END, "strategy_context": {}}
        except Exception as e:
            debug("Unexpected error during routing", error=str(e))
            return {"routing_signal": RoutingSignals.END, "strategy_context": {}}