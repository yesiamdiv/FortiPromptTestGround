
"""
Strategy Router Node

Refined to correctly interpret manual wait signals and interact with RunExecutor events for pausing.
"""

from typing import Dict, Any
from nodes.base import BaseAdversarialNode, StrategyProxyNode
from engine.state_schema import RoutingSignals, SystemState


class StrategyRouterNode(StrategyProxyNode):
    """
    Node responsible for routing decisions based on strategy output and manual signals.
    It also facilitates pausing/resuming the execution via RunExecutor interaction.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)

    def get_strategy_method(self) -> str:
        """Returns the method on the strategy to call for routing decisions."""
        return "process_end_of_loop"

    async def execute(self, state: SystemState, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the router node.
        
        1. Detect manual wait state from state flags.
        2. If waiting, signal RunExecutor to pause (this signaling is implicit via the state flags).
        3. Maintain the wait signal in the graph loop.
        4. If not waiting, delegate to strategy's routing logic.
        
        Args:
            state: Current system state (SystemState TypedDict).
            config: Runtime configuration (contains strategy and graph_type).
        
        Returns:
            Updated state with potentially new routing signal.
        """
        current_turn = state.get("current_turn", {{}})
        manual_wait_active = state.get("manual_wait_active", False)
        wait_signal_value = "WAITING_FOR_MANUAL_INPUT"
        
        # --- Check for manual wait signal first ---
        if manual_wait_active and state.get("routing_signal") == wait_signal_value:
            # If manual wait is active, the router should simply return the wait signal.
            # The RunExecutor's _run_loop checks for manual_wait_active and pauses.
            # No direct signaling needed FROM the router TO the executor event here;
            # the executor monitors the state flags.
            print(f"Router: Manual wait active. Maintaining {wait_signal_value} signal.")
            return {
                "routing_signal": wait_signal_value # Maintain the wait signal for the graph loop
            }

        # --- If not waiting, delegate to strategy ---
        try:
            strategy = config["configurable"]["strategy"]
            strategy_routing_result = strategy.process_end_of_loop(state)
            
            if not isinstance(strategy_routing_result, dict) or "routing_signal" not in strategy_routing_result:
                raise TypeError("Strategy's process_end_of_loop must return a dict with 'routing_signal'")
            
            # If strategy decides to continue, ensure manual wait is reset if it was previously active.
            # This prevents getting stuck if a strategy decides to proceed after manual input was given.
            if strategy_routing_result["routing_signal"] in [RoutingSignals.ATTACK, RoutingSignals.CONTINUE]:
                if state.get("manual_wait_active") == True:
                    print("Router: Strategy decided to proceed. Resetting manual wait flag in state.")
                    # Update state to reflect that manual wait is no longer active
                    state["manual_wait_active"] = False
                    state["manual_input_required"] = None
                    # The strategy's routing signal will now guide the graph flow.

            # Update state with strategy's routing decision
            return strategy_routing_result
            
        except Exception as e:
            print(f"Error in strategy routing: {e}")
            # Default to END on error for safety
            return {"routing_signal": RoutingSignals.END}

