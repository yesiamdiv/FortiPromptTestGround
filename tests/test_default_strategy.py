# test_default_strategy.py

import pytest
from unittest.mock import MagicMock

from engine.state_schema import SystemState, RoutingSignals
from strategies.default_strategy import DefaultStrategy


@pytest.fixture
def default_strategy_config():
    return {
        "max_attempts": 3,
        "attack_prefix": "TestAttack",
        "always_succeed": True
    }

@pytest.pytest.fixture
def default_strategy(default_strategy_config):
    return DefaultStrategy(config=default_strategy_config)

def test_default_strategy_init(default_strategy):
    assert default_strategy.config["max_attempts"] == 3
    assert default_strategy.config["attack_prefix"] == "TestAttack"

def test_default_strategy_initialize(default_strategy):
    initial_state = {
        "run_id": "test_run_123",
        "payload": {"intent": "find vulnerability"},
        "config": {
            "strategy_config": {"strategy_name": "default"}
        }
    }
    updated_state = default_strategy.initialize(initial_state)
    
    assert updated_state["strategy_context"]["intent"] == "find vulnerability"
    assert updated_state["strategy_context"]["attempt_count"] == 0
    assert updated_state["strategy_context"]["max_attempts"] == 3
    assert updated_state["routing_signal"] == RoutingSignals.CONTINUE

@pytest.mark.asyncio
async def test_default_strategy_execute_generation(default_strategy):
    initial_state = {
        "strategy_context": {
            "attempt_count": 0,
            "max_attempts": 3,
            "history": []
        }
    }
    
    # Mock necessary components if execute_generation depended on them directly
    # For DefaultStrategy, it relies on random and config, which are simple.
    
    result = await default_strategy.execute_generation(initial_state, config={})
    
    assert "current_turn" in result
    assert result["current_turn"]["turn_id"].startswith("turn_")
    assert "attack" in result["current_turn"]
    assert result["current_turn"]["attack"].prompt.startswith("TestAttack: ")
    assert result["strategy_context"]["attempt_count"] == 1

def test_default_strategy_route():
    strategy = DefaultStrategy(config={"max_attempts": 2})
    
    # Test case 1: Should continue
    state_continue = {
        "strategy_context": {"attempt_count": 0, "max_attempts": 2}
    }
    route_continue = strategy.route(state_continue)
    assert route_continue["routing_signal"] == RoutingSignals.ATTACK

    # Test case 2: Should end
    state_end = {
        "strategy_context": {"attempt_count": 2, "max_attempts": 2}
    }
    route_end = strategy.route(state_end)
    assert route_end["routing_signal"] == RoutingSignals.END

def test_default_strategy_get_dependency_schema():
    schema = DefaultStrategy.get_dependency_schema()
    assert schema["type"] == "object"
    assert "max_iterations" in schema["properties"]
    assert schema["properties"]["max_iterations"]["default"] == 1
    assert schema["required"] == []
