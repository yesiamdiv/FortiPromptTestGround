
"""
Base Node Interface"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from engine.state_schema import SystemState # NEW IMPORT


class BaseAdversarialNode(ABC):
    """Abstract base class for all execution nodes"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.node_type = self.__class__.__name__
    
    @abstractmethod
    async def execute(self, state: SystemState, runtime_config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the node's operation and return state updates"""
        raise NotImplementedError
    

class StrategyProxyNode(BaseAdversarialNode):
    """Base class for nodes that delegate to strategy methods"""
    
    async def execute(self, state: SystemState, runtime_config: Dict[str, Any]) -> Dict[str, Any]:
        # Access strategy directly from self.config as it's baked in during node instantiation
        strategy = self.config.get('strategy')
        if not strategy:
            raise AttributeError("Strategy instance not found in node's self.config.")
            
        method_name = self.get_strategy_method()
        method = getattr(strategy, method_name)
        # Pass the state and any relevant runtime config if strategy needs it
        return method(state, runtime_config)
    
    @abstractmethod
    def get_strategy_method(self) -> str:
        """Return the name of the strategy method to call"""
        raise NotImplementedError
