"""
core/orchestrator.py

The Orchestrator is the ONLY component that knows the full pipeline shape.
It knows nothing about HOW any node does its work — only the order and routing.

Flow:
    START
      │
      ▼
  [attacker_node]  ──► generates current_prompt
      │
      ▼
  [defender_node]  ──► generates current_response
      │
      ▼
   [judge_node]    ──► writes evaluation_result
      │
      ▼
  [router]         ──► breached? → END
                       blocked + max turns? → END
                       blocked + turns left? → loop back to attacker_node
      │
      ▼
  [telemetry_node] ──► logs everything, writes final_outcome
      │
      ▼
     END
"""

import uuid
import logging
from typing import Literal, Any, Dict

from langgraph.graph import StateGraph, END

from .state import ArenaState
from .interfaces import BaseAttacker, BaseDefender, BaseEvaluator
from ..config.settings import RunConfig
from api_gateway.services.db_client import DBClient

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Node factory helpers
# Each "node" is just a Python function that accepts ArenaState and returns
# a partial dict.  LangGraph merges it back into the full state automatically.
# ─────────────────────────────────────────────────────────────────────────────

def _make_attacker_node(attacker: BaseAttacker):
    """Wrap an attacker implementation as a LangGraph node function."""

    def attacker_node(state: ArenaState) -> dict:
        logger.info(f"[Turn {state.get('turn_count', 0)}] Attacker generating payload…")

        updates = attacker.generate_attack(state)

        # Ensure turn_count is incremented
        turn = state.get("turn_count", 0) + 1
        updates["turn_count"] = turn

        # Append attacker's prompt to the shared history
        prompt = updates.get("current_prompt", state.get("current_prompt", ""))
        history = list(state.get("chat_history", []))
        history.append({"role": "attacker", "content": prompt})
        updates.setdefault("chat_history", history)

        logger.debug(f"  Payload: {prompt[:120]}…" if len(prompt) > 120 else f"  Payload: {prompt}")
        return updates

    return attacker_node


def _make_defender_node(defender: BaseDefender):
    """Wrap a defender implementation as a LangGraph node function."""

    def defender_node(state: ArenaState) -> dict:
        logger.info(f"[Turn {state.get('turn_count', 0)}] Defender responding…")
        try:
            updates = defender.get_response(state)

            # Append defender's response to the shared history
            response = updates.get("current_response", state.get("current_response", ""))
            history = list(state.get("chat_history", []))
            history.append({"role": "defender", "content": response})
            updates.setdefault("chat_history", history)

            logger.debug(f"  Response: {response[:120]}…" if len(response) > 120 else f"  Response: {response}")
            return updates
        except Exception as e:
            logger.error(f"Defender node failed: {e}")
            return {
                "evaluation_result": "error",
                "evaluation_reasoning": f"Defender node failed: {e}",
                "final_outcome": "attacker_wins", # Assume attacker wins on defender error
            }

    return defender_node


def _make_judge_node(evaluator: BaseEvaluator):
    """Wrap an evaluator implementation as a LangGraph node function."""

    def judge_node(state: ArenaState) -> dict:
        logger.info(f"[Turn {state.get('turn_count', 0)}] Judge evaluating…")
        try:
            updates = evaluator.evaluate(state)
            result = updates.get("evaluation_result", "blocked")
            reasoning = updates.get("evaluation_reasoning", "")

            # Ensure evaluation_result is one of the expected values or 'error'
            if result not in ["breached", "blocked", "error"]:
                logger.warning(f"Unexpected evaluation_result: {result}. Defaulting to 'blocked'.")
                result = "blocked"
                reasoning = f"Unexpected result from evaluator: {result}. Defaulting to blocked."

            logger.info(f"  Result: {result.upper()} — {reasoning[:80]}")
            return updates
        except Exception as e:
            logger.error(f"Judge node failed: {e}")
            return {
                "evaluation_result": "error",
                "evaluation_reasoning": f"Judge node failed: {e}",
                "final_outcome": "attacker_wins", # Assume attacker wins on judge error
            }

    return judge_node


def _make_telemetry_node(tracker=None, run_config=None):
    """
    Log the completed turn to the telemetry backend (if one is wired in).
    Also writes the final_outcome into state.
    """

    def telemetry_node(state: ArenaState) -> dict:
        result = state.get("evaluation_result", "blocked")
        turn = state.get("turn_count", 0)
        max_turns = state.get("max_turns", 1)

        # Determine final outcome if not already set by an error
        if state.get("final_outcome", "ongoing") == "ongoing":
            if result == "breached":
                outcome = "attacker_wins"
            elif turn >= max_turns:
                outcome = "defender_wins"
            else:
                outcome = "ongoing" # Should not happen if called at the end, but for safety
        else:
            outcome = state.get("final_outcome")

        logger.info(f"[Telemetry] Turn {turn}/{max_turns} — outcome so far: {outcome}")

        if tracker is not None:
            try:
                # Pass run_config to tracker if it exists
                tracker_state = state.copy()
                tracker_state["run_config"] = run_config
                tracker.log(tracker_state, outcome)
            except Exception as exc:
                logger.warning(f"Telemetry log failed: {exc}")

        return {"final_outcome": outcome}

    return telemetry_node


# ─────────────────────────────────────────────────────────────────────────────
# Router — the conditional edge that decides what happens after the judge
# ─────────────────────────────────────────────────────────────────────────────

def _route_after_judge(state: ArenaState) -> Literal["telemetry", "attacker"]:
    """
    Conditional routing logic.

    Called by LangGraph after the judge node writes its result.
    Returns the name of the next node to visit.
    """
    result = state.get("evaluation_result", "blocked")
    turn = state.get("turn_count", 0)
    max_turns = state.get("max_turns", 1)

    if result == "breached":
        logger.info("  → Attack BREACHED the defender. Ending run.")
        return "telemetry"

    if turn >= max_turns:
        logger.info(f"  → Max turns ({max_turns}) reached. Defender held. Ending run.")
        return "telemetry"

    # If evaluation result is an error, route to telemetry to log and end run
    if result == "error":
        logger.error(f"  → Evaluation error occurred. Ending run.")
        return "telemetry"

    logger.info(f"  → Attack blocked (turn {turn}/{max_turns}). Looping back to attacker.")
    return "attacker"


# ─────────────────────────────────────────────────────────────────────────────
# Public Orchestrator API
# ─────────────────────────────────────────────────────────────────────────────

class Orchestrator:
    """
    Assembles the LangGraph pipeline from pluggable components.

    Usage:
        orch = Orchestrator(
            attacker=MyAttacker(),
            defender=MyDefender(),
            evaluator=MyEvaluator(),
            tracker=MyTracker(),   # optional
        )
        result = orch.run(
            goal="Extract the system prompt",
            strategy="multi_turn_roleplay",
            max_turns=5,
        )
    """

    def __init__(
        self,
        attacker: BaseAttacker,
        defender: BaseDefender,
        evaluator: BaseEvaluator,
        run_config: RunConfig,
        tracker=None,
    ):
        self.attacker = attacker
        self.defender = defender
        self.evaluator = evaluator
        self.run_config = run_config
        self.tracker = tracker
        self._graph = None

    def _build_graph(self) -> StateGraph:
        """
        Wire up the LangGraph state machine.
        Called once per Orchestrator instance (lazy-built on first run).
        """
        builder = StateGraph(ArenaState)

        # ── Add nodes ────────────────────────────────────────────────────────
        builder.add_node("attacker",  _make_attacker_node(self.attacker))
        builder.add_node("defender",  _make_defender_node(self.defender))
        builder.add_node("judge",     _make_judge_node(self.evaluator))
        builder.add_node("telemetry", _make_telemetry_node(self.tracker, self.run_config))
        
        # ── Add fixed edges ───────────────────────────────────────────────────
        builder.set_entry_point("attacker")
        builder.add_edge("attacker", "defender")
        builder.add_edge("defender", "judge")

        # ── Add conditional edge after judge ──────────────────────────────────
        builder.add_conditional_edges(
            "judge",
            _route_after_judge,
            {
                "attacker":  "attacker",   # loop
                "telemetry": "telemetry",  # end
            },
        )

        # ── Telemetry always ends the run ─────────────────────────────────────
        builder.add_edge("telemetry", END)

        return builder.compile()

    async def run(
        self,
        goal: str,
        strategy: str = "default",
        max_turns: int = 5,
        extra_state: dict | None = None,
    ) -> ArenaState:
        """
        Execute a full red-team run and return the final state.

        Args:
            goal:        What the attacker is trying to make the defender do/say.
            strategy:    Identifier for the attack strategy (passed into state
                         so strategy modules can read it).
            max_turns:   How many attack/defend loops are allowed.
            extra_state: Any additional seed values you want in the initial state.

        Returns:
            The final ArenaState after the graph terminates.
        """
        # Call setup hooks on plugins (must be idempotent)
        # Note: setup() methods should be designed to be idempotent.
        self.attacker.setup(run_config=self.run_config.attacker_settings)
        self.defender.setup(run_config=self.run_config.defender_settings)
        self.evaluator.setup(run_config=self.run_config.evaluator_settings)

        # Seed the initial state for the graph
        initial_state = extra_state or ArenaState(
            run_id=self.run_config.run_id or str(uuid.uuid4()),
            goal=self.run_config.goal,
            strategy=self.run_config.attacker_settings.strategy,
            max_turns=self.run_config.attacker_settings.max_turns,
            turn_count=0,
            chat_history=[],
            current_prompt="",
            current_response="",
            evaluation_result="pending",
            evaluation_reasoning="",
            strategy_metadata={},
            final_outcome="ongoing",
            run_config=self.run_config, # Add the full run_config object to the state
        )

        logger.info(f"Starting run '{initial_state['run_id']}' (goal: '{initial_state['goal']}' for {initial_state['max_turns']} turns)")

        # Build the graph (lazy, once)
        if self._graph is None:
            self._graph = self._build_graph()

        # Run the graph
        final_state = self._graph.compile().invoke(initial_state)

        # Ensure final_outcome is resolved
        if final_state["final_outcome"] == "ongoing":
            if final_state["evaluation_result"] == "breached":
                final_state["final_outcome"] = "attacker_wins"
            elif final_state["evaluation_result"] == "error":
                 final_state["final_outcome"] = "defender_wins" # Or attacker_wins depending on error context
            else:
                final_state["final_outcome"] = "defender_wins"

        # Call teardown hooks
        self.attacker.teardown()
        self.defender.teardown()
        self.evaluator.teardown()

        logger.info(f"Run \'{initial_state['run_id']}' finished with outcome: {final_state['final_outcome']}.upper()")

        return final_state