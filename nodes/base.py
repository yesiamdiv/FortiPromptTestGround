"""
Base Node Interface"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from engine.state import SystemState
from core.logging import debug, tracer, step, warn, err


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
    
