"""
Base Node Interface"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from engine.state_schema import SystemState
from engine.debug_utils import debug, tracer, step, warn, err


class BaseAdversarialNode(ABC):
    """Abstract base class for all execution nodes"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.node_type = self.__class__.__name__
    
    @abstractmethod
    async def execute(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute the node's operation and return state updates"""
        tracer(f"{self.__class__.__name__}.execute", node_type=self.node_type)
        raise NotImplementedError
    
    @classmethod
    def get_node_schema(cls) -> Dict[str, Any]:
        """
        Return JSON schema describing the node's parameters.
        Override in subclasses to provide node-specific schema.
        """
        return {
            "type": "object",
            "properties": {},
            "description": "No parameters defined for this node"
        }
    

class StrategyProxyNode(BaseAdversarialNode):
    """Base class for nodes that delegate to strategy methods"""
    
    async def execute(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        tracer("StrategyProxyNode.execute", node_type=self.node_type)
        strategy = self.config.get('strategy')
        if not strategy:
            err("Strategy instance not found in node config")
            raise AttributeError("Strategy instance not found in node's self.config.")
        
        if runtime_config is None:
            runtime_config = {}
            
        method_name = self.get_strategy_method()
        debug("Delegating to strategy method", method=method_name)
        method = getattr(strategy, method_name)
        return method(state, runtime_config)
    
    def get_strategy_method(self) -> str:
        """Return the name of the strategy method to call"""
        err("get_strategy_method not implemented", node_type=self.node_type)
        raise NotImplementedError