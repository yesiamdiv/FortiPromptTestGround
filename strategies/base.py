"""
Base Strategy Interface
"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from engine.state import SystemState, RoutingSignals
from core.logging import debug, tracer, step

class AttackStrategy(ABC):
    """
    Abstract base class for all attack strategies.
    Strategies hold the core business logic (LLM calls, prompt crafting, routing rules).
    """
    
    def __init__(self, config: Dict[str, Any]):
        # self.config holds the static 'strategy_params' passed from the GraphBuilder
        self.config = config or {}
        self.name = self.__class__.__name__
    
    @abstractmethod
    def initialize(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Initialize the strategy, setting up memory and execution context.
        Must return a dictionary (delta) containing the 'strategy_context' updates.
        """
        raise NotImplementedError

    @abstractmethod
    async def execute_generation(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Generate the next attack. 
        Must return a dictionary (delta) containing 'current_turn' and 'strategy_context' updates.
        """
        raise NotImplementedError

    @abstractmethod
    def route(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> str:
        """
        Determine the next routing signal (e.g., CONTINUE, END).
        Note: The router node expects the raw string signal to be returned, 
        or a dictionary containing {"routing_signal": signal}.
        """
        raise NotImplementedError

    def route_post_attack(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> str:
        """Routing signal after the attack node. Default: proceed to defence.

        Override in strategies that need to retry or branch after attack
        (e.g. quality-gate before sending to defence).
        """
        return RoutingSignals.PROCEED

    def route_post_defence(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> str:
        """Routing signal after the defence node. Default: proceed to eval.

        Override in multi-turn strategies to return CONTINUE_CONVERSATION
        when the session should loop back to attack without evaluating yet.
        """
        return RoutingSignals.PROCEED

    @classmethod
    @abstractmethod
    def get_dependency_schema(cls) -> Dict[str, Any]:
        """
        Return a JSON schema defining the strategy's required static parameters.
        """
        raise NotImplementedError
    
    @classmethod
    def get_strategy_schema(cls) -> Dict[str, Any]:
        """Alias for get_dependency_schema."""
        return cls.get_dependency_schema()