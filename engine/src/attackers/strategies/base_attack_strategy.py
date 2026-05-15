"""
attackers/strategies/base_attack_strategy.py

Defines the interface for attack strategies.

Strategies are responsible for crafting the prompt that gets sent to the LLM attacker,
and for deciding whether the conversation history should be reset.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any

from src.core.state import ArenaState


class BaseAttackStrategy(ABC):
    """
    Abstract base class for all attack strategies.

    Strategies define the logic for generating prompts based on the current state
    and conversation history. They also determine if the history should be reset
    for a new attack turn.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize strategy with any necessary parameters."""
        # Store any strategy-specific parameters
        self.params = kwargs

    @abstractmethod
    def build_prompt(self, state: ArenaState) -> str:
        """
        Build the prompt for the LLM attacker based on the current state.

        Args:
            state: The current ArenaState, containing chat history, goal, etc.

        Returns:
            The constructed prompt string.
        """
        ...

    @abstractmethod
    def should_reset_history(self, state: ArenaState) -> bool:
        """
        Determine if the chat history should be reset before the next turn.

        This is useful for strategies that want to start fresh or avoid
        carrying over potentially harmful context.

        Args:
            state: The current ArenaState.

        Returns:
            True if the history should be reset, False otherwise.
        """
        ...

    def setup(self, **kwargs: Any) -> None:
        """
        Optional: called once before the graph runs.
        Use this for loading models, reading files, etc.
        """
        pass

    def teardown(self) -> None:
        """
        Optional: called once after the graph finishes.
        Use this for cleanup, closing connections, etc.
        """
        pass
