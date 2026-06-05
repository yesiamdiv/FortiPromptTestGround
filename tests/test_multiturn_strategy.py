"""
Tests for MultiTurnStrategy (Phase 2 Step 2.11).

Verifies:
- route_post_defence returns CONTINUE_CONVERSATION for turns 0..N-2
- route_post_defence returns PROCEED for turn N-1
- route returns ATTACK until all sessions complete, then END
- initialize sets correct defaults
"""

import pytest
from engine.state import RoutingSignals
from strategies.multiturn_strategy import MultiTurnStrategy


def make_strategy(max_turns=3, sessions=5):
    return MultiTurnStrategy(config={
        "max_turns_per_session": max_turns,
        "sessions_per_run": sessions,
    })


def make_state(current_turn_in_session=0, sessions_completed=0, max_turns=3, sessions_per_run=5, defence=None):
    ctx = {
        "max_turns_per_session": max_turns,
        "sessions_per_run": sessions_per_run,
        "current_turn_in_session": current_turn_in_session,
        "sessions_completed": sessions_completed,
        "conversation_history": [],
    }
    return {
        "strategy_context": ctx,
        "current_turn": {"defence": defence},
    }


# ---------------------------------------------------------------------------
# route_post_defence
# ---------------------------------------------------------------------------

class TestRoutePostDefence:
    def test_continues_before_last_turn(self):
        strategy = make_strategy(max_turns=3)
        # turns 0 and 1 should loop back
        for turn in range(2):
            state = make_state(current_turn_in_session=turn, max_turns=3)
            signal = strategy.route_post_defence(state)
            assert signal == RoutingSignals.CONTINUE_CONVERSATION, (
                f"Expected CONTINUE_CONVERSATION at turn {turn}, got {signal}"
            )

    def test_proceeds_at_last_turn(self):
        strategy = make_strategy(max_turns=3)
        # turn 2 (== max_turns - 1) should proceed to eval
        state = make_state(current_turn_in_session=2, max_turns=3)
        assert strategy.route_post_defence(state) == RoutingSignals.PROCEED

    def test_single_turn_session_proceeds_immediately(self):
        strategy = make_strategy(max_turns=1)
        state = make_state(current_turn_in_session=0, max_turns=1)
        assert strategy.route_post_defence(state) == RoutingSignals.PROCEED

    def test_five_turn_session(self):
        strategy = make_strategy(max_turns=5)
        for turn in range(4):
            state = make_state(current_turn_in_session=turn, max_turns=5)
            assert strategy.route_post_defence(state) == RoutingSignals.CONTINUE_CONVERSATION
        state = make_state(current_turn_in_session=4, max_turns=5)
        assert strategy.route_post_defence(state) == RoutingSignals.PROCEED


# ---------------------------------------------------------------------------
# route (end-of-cycle)
# ---------------------------------------------------------------------------

class TestRoute:
    def test_attack_until_sessions_complete(self):
        strategy = make_strategy(sessions=3)
        for done in range(2):
            state = make_state(sessions_completed=done, sessions_per_run=3)
            signal = strategy.route(state)
            assert signal == RoutingSignals.ATTACK, (
                f"Expected ATTACK after session {done}, got {signal}"
            )

    def test_end_when_sessions_exhausted(self):
        strategy = make_strategy(sessions=3)
        state = make_state(sessions_completed=2, sessions_per_run=3)
        assert strategy.route(state) == RoutingSignals.END

    def test_route_resets_session_counters(self):
        strategy = make_strategy(sessions=5)
        state = make_state(sessions_completed=0, sessions_per_run=5)
        # After route() the strategy_context counters should be reset
        strategy.route(state)
        ctx = state["strategy_context"]
        assert ctx["current_turn_in_session"] == 0
        assert ctx["conversation_history"] == []
        assert ctx["sessions_completed"] == 1


# ---------------------------------------------------------------------------
# initialize
# ---------------------------------------------------------------------------

class TestInitialize:
    def test_initialize_sets_defaults(self):
        strategy = make_strategy(max_turns=4, sessions=6)
        state = {}
        result = strategy.initialize(state)
        ctx = result["strategy_context"]
        assert ctx["max_turns_per_session"] == 4
        assert ctx["sessions_per_run"] == 6
        assert ctx["current_turn_in_session"] == 0
        assert ctx["sessions_completed"] == 0
        assert ctx["conversation_history"] == []

    def test_initialize_strategy_name(self):
        strategy = make_strategy()
        result = strategy.initialize({})
        assert result["strategy_context"]["strategy_name"] == "multiturn"
