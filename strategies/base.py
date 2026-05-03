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
    def initialize(self, state: SystemState) -> Dict[str, Any]:
        """Initialize the strategy, potentially loading resources or setting up context.
        
        Args:
            state: Current system state.
        
        Returns:
            Modified state dictionary.
        """
        raise NotImplementedError

    @abstractmethod
    def route(self, state: SystemState) -> Dict[str, Any]:
        """Determine the next routing signal and update context based on state."""
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def get_dependency_schema(cls) -> Dict[str, Any]:
        """
        Return a JSON schema defining the strategy's dependencies.
        This is used by the frontend to render input fields for required parameters.
        """
        raise NotImplementedError
