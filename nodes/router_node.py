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
from engine.state import SystemState, RoutingSignals
from core.logging import debug, tracer, step, warn, err


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

class PostAttackRouter(BaseAdversarialNode):
    """
    Intermediate router placed after the attack node.

    Delegates to strategy.route_post_attack(). Expected return: PROCEED (→ defence).
    Fail-safe: any unexpected signal is coerced to PROCEED so the graph
    cannot stall between attack and defence.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)

    async def execute(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        if runtime_config is None:
            runtime_config = {}
        tracer("PostAttackRouter.execute")

        if "strategy" not in self.config:
            err("Strategy instance not found in PostAttackRouter config")
            return {"routing_signal": RoutingSignals.PROCEED}

        strategy = self.config["strategy"]
        try:
            signal = strategy.route_post_attack(state, runtime_config)
        except Exception as e:
            err("PostAttackRouter: strategy raised", error=str(e))
            signal = RoutingSignals.PROCEED

        if signal not in (RoutingSignals.PROCEED,):
            warn("PostAttackRouter: unexpected signal, defaulting to PROCEED", signal=signal)
            signal = RoutingSignals.PROCEED

        step("PostAttackRouter decision", signal=signal)
        return {"routing_signal": signal}

    @classmethod
    def get_node_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "description": "Delegates to strategy.route_post_attack(). No node-specific params.",
        }


class PostDefenceRouter(BaseAdversarialNode):
    """
    Intermediate router placed after the defence node.

    Delegates to strategy.route_post_defence(). Valid signals:
      PROCEED              → eval  (default for all existing strategies)
      CONTINUE_CONVERSATION → attack (same session, used by MultiTurnStrategy)
    Fail-safe: any unexpected signal is coerced to PROCEED.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)

    async def execute(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        if runtime_config is None:
            runtime_config = {}
        tracer("PostDefenceRouter.execute")

        if "strategy" not in self.config:
            err("Strategy instance not found in PostDefenceRouter config")
            return {"routing_signal": RoutingSignals.PROCEED}

        strategy = self.config["strategy"]
        try:
            signal = strategy.route_post_defence(state, runtime_config)
        except Exception as e:
            err("PostDefenceRouter: strategy raised", error=str(e))
            signal = RoutingSignals.PROCEED

        valid = (RoutingSignals.PROCEED, RoutingSignals.CONTINUE_CONVERSATION)
        if signal not in valid:
            warn("PostDefenceRouter: unexpected signal, defaulting to PROCEED", signal=signal)
            signal = RoutingSignals.PROCEED

        step("PostDefenceRouter decision", signal=signal)
        return {"routing_signal": signal}

    @classmethod
    def get_node_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "description": (
                "Delegates to strategy.route_post_defence(). "
                "PROCEED → eval, CONTINUE_CONVERSATION → attack."
            ),
        }
