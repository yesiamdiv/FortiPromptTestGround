"""Base Middleware Interface"""

from abc import ABC
from typing import Dict, Any


class BaseMiddleware(ABC):
    """Abstract interface for system observers"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.name = self.__class__.__name__
    
    async def before_run(self, initial_state: Dict[str, Any], config: Dict[str, Any], run_id: str):
        """Triggered once before graph starts"""
        pass
    
    async def after_step(self, step_data: Dict[str, Any], run_id: str):
        """Triggered after every node execution"""
        pass
    
    async def after_run(self, final_state: Dict[str, Any], run_id: str):
        """Triggered once when graph completes"""
        pass
    
    async def on_error(self, error: Exception, run_id: str, step_data: Dict[str, Any] = None):
        """Triggered when an error occurs"""
        pass
