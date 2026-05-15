"""
core/interfaces.py

Abstract base classes that define the contract every pluggable component must implement.

The Orchestrator only ever talks to these interfaces — it has zero knowledge of
what's happening inside any concrete implementation.  Swap out any module without
touching anything else.
"""

from abc import ABC, abstractmethod
from .state import ArenaState


# ─────────────────────────────────────────────────────────────────────────────
# Attacker Interface
# ─────────────────────────────────────────────────────────────────────────────

class BaseAttacker(ABC):
    """
    Every attacker module must subclass this.

    The orchestrator calls `generate_attack(state)` and expects back a partial
    ArenaState dict containing at minimum `current_prompt`.

    What happens inside is entirely up to the implementation:
      - Call an LLM via LangChain
      - Read from a JSON file of pre-written payloads
      - Use a rule-based template engine
      - Run a GAN that generates adversarial text
      … none of this is the orchestrator's business.
    """

    @abstractmethod
    def generate_attack(self, state: ArenaState) -> dict:
        """
        Read from `state`, produce the next attack payload.

        Returns a partial state dict. Must include:
            - current_prompt (str)
        May optionally update:
            - strategy_metadata (dict)
            - chat_history (list)  — if the attacker manages history itself
        """
        ...

    def setup(self, **kwargs) -> None:
        """
        Optional: called once before the graph runs.
        Use this for loading models, reading files, warming up connections, etc.
        """
        pass

    def teardown(self) -> None:
        """
        Optional: called once after the graph finishes.
        """
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Defender Interface
# ─────────────────────────────────────────────────────────────────────────────

class BaseDefender(ABC):
    """
    Every defender module must subclass this.

    The orchestrator calls `get_response(state)` and expects back a partial
    ArenaState dict containing at minimum `current_response`.

    Implementations can be:
      - A raw HTTP POST to an external API endpoint
      - A local model running via Ollama
      - A full LangChain pipeline with pre/post filters
      - A mock that returns hardcoded strings for testing
    """

    @abstractmethod
    def get_response(self, state: ArenaState) -> dict:
        """
        Read `current_prompt` from `state`, return the defender's response.

        Returns a partial state dict. Must include:
            - current_response (str)
        """
        ...

    def setup(self, **kwargs) -> None:
        """Optional: pre-run initialisation."""
        pass

    def teardown(self) -> None:
        """Optional: post-run cleanup."""
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Evaluator (Judge) Interface
# ─────────────────────────────────────────────────────────────────────────────

class BaseEvaluator(ABC):
    """
    Every judge/evaluator module must subclass this.

    The orchestrator calls `evaluate(state)` and expects back a partial
    ArenaState dict containing at minimum `evaluation_result`.

    Implementations can be:
      - An LLM-as-judge (GPT-4, Claude, etc.) analysing the exchange
      - A deterministic string-match / regex checker
      - A fine-tuned classifier
    """

    @abstractmethod
    def evaluate(self, state: ArenaState) -> dict:
        """
        Read `current_prompt` and `current_response` from `state`.
        Determine whether the attack succeeded.

        Returns a partial state dict. Must include:
            - evaluation_result: "breached" | "blocked"
        May optionally include:
            - evaluation_reasoning (str)
        """
        ...

    def setup(self, **kwargs) -> None:
        """Optional: pre-run initialisation."""
        pass

    def teardown(self) -> None:
        """Optional: post-run cleanup."""
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Attack Strategy Interface
# ─────────────────────────────────────────────────────────────────────────────

class BaseAttackStrategy(ABC):
    """
    Strategies are the brains inside an LLM-based Attacker.

    A Strategy decides *how* to craft the next payload given the conversation
    so far. The LLMAttacker delegates all prompt-construction logic here,
    keeping the LLM-calling code separate from the attack reasoning.
    """

    @abstractmethod
    def build_prompt(self, state: ArenaState) -> str:
        """
        Construct the instruction/prompt that will be sent to the attacking LLM.

        This should encode the attack style:
          - Single-turn: ignore history, craft one-shot jailbreak
          - Multi-turn: use history to escalate or mutate
          - Roleplay: set up a fictional framing around the goal
        """
        ...

    @abstractmethod
    def should_reset_history(self, state: ArenaState) -> bool:
        """
        Return True if chat_history should be cleared before this turn.
        (e.g. single-turn strategies always return True)
        """
        ...