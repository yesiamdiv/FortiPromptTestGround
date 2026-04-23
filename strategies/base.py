"""Base Strategy Interface"""

from abc import ABC, abstractmethod
from typing import Dict, Any


class AttackStrategy(ABC):
    """Abstract base class for attack strategies"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = self.__class__.__name__
    
    @abstractmethod
    def setup(self, initial_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Initialize strategy - called once at start"""
        raise NotImplementedError
    
    @abstractmethod
    async def execute_generation(self, state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate next attack - called by AttackNode.
        
        Strategy has full control over LLM calls and data processing.
        Can make multiple LLM calls, process data, etc.
        
        Args:
            state: Current system state
            config: Runtime configuration
        
        Returns:
            Dictionary with updated current_turn and strategy_context
        """
        raise NotImplementedError
    
    @abstractmethod
    def process_end_of_loop(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Process evaluation and decide routing - called after EvalNode"""
        raise NotImplementedError
    
    def get_next_route(self, state: Dict[str, Any]) -> str:
        """Extract routing signal from state"""
        return state.get("routing_signal", "__end__")
