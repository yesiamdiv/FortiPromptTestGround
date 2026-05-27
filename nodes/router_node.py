"""
================================================================================
UNIVERSAL ROUTER NODE
================================================================================

DEVELOPER INSTRUCTIONS:
--------------------------------------------------------------------------------
1. Architectural Role: This is a Strategy-Delegation Node. It does not decide
   where to go on its own; it asks the active strategy.
2. State Deltas: It returns only the `routing_signal` dictionary update.
3. Fail-Safe Design: It validates the signal against `RoutingSignals` and 
   forces an `END` signal if a strategy behaves unexpectedly.
================================================================================
"""

from typing import Dict, Any
from nodes.base import BaseAdversarialNode
from engine.state_schema import SystemState, RoutingSignals
from engine.debug_utils import debug, tracer, step, warn, err


class RouterNode(BaseAdversarialNode):
    """
    Universal router that delegates routing decisions to the active strategy.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        
    async def execute(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        if runtime_config is None: runtime_config = {}
        tracer("RouterNode.execute")
        
        # 1. STRICT CONFIG ACCESS
        if "strategy" not in self.config:
            err("Strategy instance not found in Router Node config")
            raise AttributeError("Strategy instance not found in Router Node's self.config.")
            
        strategy = self.config["strategy"]
        debug("Delegating routing to strategy", strategy_type=type(strategy).__name__)
        
        # 2. DELEGATE TO STRATEGY
        try:
            # Pass the strict state and dynamic runtime_config down
            signal = strategy.route(state, runtime_config)
        except Exception as e:
            err("Strategy routing method crashed", error=str(e))
            # Fail-safe: End the graph if the strategy's brain breaks
            return {"routing_signal": RoutingSignals.END}
        
        # 3. VALIDATE SIGNAL
        valid_signals = [RoutingSignals.CONTINUE, RoutingSignals.ATTACK, RoutingSignals.END]
        if signal not in valid_signals:
            warn(f"Invalid routing signal '{signal}' returned by strategy. Defaulting to END.")
            signal = RoutingSignals.END
            
        step("Routing decision complete", signal=signal)
        
        # 4. RETURN CLEAN DELTA
        return {"routing_signal": signal}

    @classmethod
    def get_node_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "description": "Router node delegates entirely to strategy.route(). No node-specific params."
        }