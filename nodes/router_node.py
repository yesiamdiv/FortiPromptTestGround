
"""
Router Node

This node delegates routing decisions to the strategy.
"""

from typing import Dict, Any
from nodes.base import BaseAdversarialNode, StrategyProxyNode
from engine.state_schema import RoutingSignals, SystemState


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
        try:
            # Access strategy directly from self.config, as it's baked in during node instantiation
            strategy = self.config.get('strategy')
            if not strategy:
                raise AttributeError("Strategy instance not found in node's self.config.")
            
            # Delegate to strategy's route method, passing state and runtime_config if needed by strategy
            # For now, only state is passed as per strategy interface.
            routing_signal = strategy.route(state)
            
            if not isinstance(routing_signal, str):
                raise TypeError("Strategy's route method must return a string routing signal.")
            
            # Return the routing signal to be placed in the state
            return {"routing_signal": routing_signal}
            
        except AttributeError as e:
            raise AttributeError(f"Strategy error: {e}")
        except TypeError as e:
            raise TypeError(f"Error in strategy routing method: {e}")
        except Exception as e:
            print(f"Error during routing: {e}")
            # Default to END on error for safety
            return {"routing_signal": RoutingSignals.END}
