"""
core/state.py

The Shared State is the single source of truth that flows through the entire pipeline.
Every node reads from it, does its work, and writes back to it. Nothing else is shared.
"""

from typing import Any, Optional
from typing_extensions import TypedDict


class ArenaState(TypedDict, total=False):
    """
    The payload that travels between every node in the graph.

    All fields are optional (total=False) so nodes can be written to
    return only the keys they actually update — LangGraph will merge
    the partial dict back into the full state automatically.
    """

    # ── Run metadata ──────────────────────────────────────────────────────────
    run_id: str                        # Unique ID for this test run
    strategy: str                      # Name of the attack strategy in use
    max_turns: int                     # Maximum allowed attack/defend loops
    turn_count: int                    # Current loop iteration (starts at 0)
    goal: str                          # What the attacker is ultimately trying to achieve

    # ── Conversation history ──────────────────────────────────────────────────
    # Each entry: {"role": "attacker"|"defender", "content": str}
    chat_history: list[dict[str, str]]

    # ── Per-turn payloads ─────────────────────────────────────────────────────
    current_prompt: str                # The attack payload for this turn
    current_response: str             # The defender's response for this turn

    # ── Judge output ──────────────────────────────────────────────────────────
    evaluation_result: str            # "breached" | "blocked" | "pending"
    evaluation_reasoning: str         # Human-readable explanation from the judge

    # ── Attacker internal notes ───────────────────────────────────────────────
    # The attacker can use this to carry notes across turns (e.g. "tried base64, failed")
    strategy_metadata: dict[str, Any]

    # ── Final outcome ─────────────────────────────────────────────────────────
    run_config: dict[str, Any]                     # Full configuration for this run