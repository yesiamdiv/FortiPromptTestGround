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
    async def execute(self, state: SystemState, config: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the node's operation and return state updates"""
        raise NotImplementedError
    

class StrategyProxyNode(BaseAdversarialNode):
    """Base class for nodes that delegate to strategy methods"""
    
    async def execute(self, state: SystemState, config: Dict[str, Any]) -> Dict[str, Any]:
        strategy = config["configurable"]["strategy"]
        method_name = self.get_strategy_method()
        method = getattr(strategy, method_name)
        return method(state)
    
    @abstractmethod
    def get_strategy_method(self) -> str:
        """Return the name of the strategy method to call"""
        raise NotImplementedError
