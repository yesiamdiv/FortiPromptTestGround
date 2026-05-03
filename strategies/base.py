"""
Base Strategy Interface"""

from abc import ABC, abstractmethod
from typing import Dict, Any
from engine.state_schema import SystemState # IMPORT SYSTEMSTATE


class AttackStrategy(ABC):
    """Abstract base class for attack strategies"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.name = self.__class__.__name__
    
    @abstractmethod
    def setup(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Initialize strategy - called once at start"""
        raise NotImplementedError
    
    @abstractmethod
    async def execute_generation(self, state: SystemState, config: Dict[str, Any]) -> Dict[str, Any]:
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
    def process_end_of_loop(self, state: SystemState) -> Dict[str, Any]:
        """Process evaluation and decide routing - called after EvalNode"""
        raise NotImplementedError
    
    @abstractmethod
    def route(self, state: SystemState) -> str:
        """Determine the next routing signal based on the current state."""
        raise NotImplementedError

    # Placeholder for initialization - to be implemented by specific strategies
    @abstractmethod
    def initialize(self, state: SystemState) -> Dict[str, Any]:
        """Initialize the strategy, potentially loading resources or setting up context.
        
        Args:
            state: Current system state.
        
        Returns:
            Modified state dictionary.
        """
        raise NotImplementedError

    def get_next_route(self, state: SystemState) -> str:
        """Extract routing signal from state"""
        return state.get("routing_signal", "__end__")
