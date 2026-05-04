# test_manual_strategy.py

import pytest
from unittest.mock import MagicMock, patch

from strategies.manual_strategy import ManualStrategy
from engine.state_schema import SystemState, RoutingSignals


@pytest.fixture
def manual_strategy_config():
    return {
        "max_turns": 5
    }

@pytest.pytest.fixture
def manual_strategy(manual_strategy_config):
    return ManualStrategy(config=manual_strategy_config)

def test_manual_strategy_init(manual_strategy):
    assert manual_strategy.config["max_turns"] == 5

def test_manual_strategy_initialize_success(manual_strategy):
    mock_db_ops = MagicMock()
    # Mock get_last_manual_turn_for_session to return mock data
    mock_last_turn = MagicMock()
    mock_last_turn.turn_id = "turn_abc"
    mock_last_turn.index = 2
    mock_last_turn.attack_prompt = "Previous attack prompt."
    mock_db_ops.get_last_manual_turn_for_session.return_value = mock_last_turn

    # Mock get_db_ops to return mock_db_ops
    with patch("strategies.manual_strategy.get_db_ops", return_value=mock_db_ops):
        initial_state = {
            "run_id": "test_run_789",
            "payload": {"session_id": "sess_xyz", "prompt": "User turn 3"},
            "config": {
                "strategy_config": {"strategy_name": "manual"}
            }
        }
        updated_state = manual_strategy.initialize(initial_state)

        assert updated_state["strategy_context"]["session_id"] == "sess_xyz"
        assert updated_state["strategy_context"]["iteration_count"] == 3
        assert updated_state["strategy_context"]["history"] == ["Previous attack prompt."]
        assert updated_state["routing_signal"] == RoutingSignals.CONTINUE

def test_manual_strategy_initialize_new_session(manual_strategy):
    mock_db_ops = MagicMock()
    mock_db_ops.get_last_manual_turn_for_session.return_value = None # No prior turns

    with patch("strategies.manual_strategy.get_db_ops", return_value=mock_db_ops):
        initial_state = {
            "run_id": "test_run_789",
            "payload": {"session_id": "sess_new", "prompt": "User turn 1"},
            "config": {
                "strategy_config": {"strategy_name": "manual"}
            }
        }
        updated_state = manual_strategy.initialize(initial_state)

        assert updated_state["strategy_context"]["session_id"] == "sess_new"
        assert updated_state["strategy_context"]["iteration_count"] == 0
        assert updated_state["strategy_context"]["history"] == []
        assert updated_state["routing_signal"] == RoutingSignals.CONTINUE

def test_manual_strategy_initialize_missing_session_id(manual_strategy):
    # Test that it raises an error if session_id is missing
    initial_state = {
        "run_id": "test_run_789",
        "payload": {"prompt": "User turn 1"} # Missing session_id
    }
    with pytest.raises(ValueError, match="ManualStrategy requires a 'session_id' in the initial payload"):
        manual_strategy.initialize(initial_state)

@pytest.mark.asyncio
async def test_manual_strategy_execute_generation(manual_strategy):
    mock_db_ops = MagicMock()
    mock_db_ops.get_last_manual_turn_for_session.return_value = None # Simulate new session
    
    # Mock create_manual_turn to capture arguments
    mock_db_ops.create_manual_turn = MagicMock()

    with patch("strategies.manual_strategy.get_db_ops", return_value=mock_db_ops):
        initial_state = {
            "run_id": "test_run_abc",
            "payload": {"session_id": "sess_def", "prompt": "User attack prompt"},
            "strategy_context": {"iteration_count": 0, "max_turns": 5},
            "current_turn": { "turn_id": "turn_ghi" }
        }

        result = await manual_strategy.execute_generation(initial_state, config={})

        # Assertions for the output state
        assert "current_turn" in result
        assert result["current_turn"]["turn_id"].startswith("turn_")
        assert "attack" in result["current_turn"]
        assert result["current_turn"]["attack"].prompt == "User attack prompt"
        assert result["strategy_context"]["history"] == ["User attack prompt"]
        assert result["strategy_context"]["iteration_count"] == 1
        assert result["session_id"] == "sess_def"
        
        # Assert that create_manual_turn was called correctly
        mock_db_ops.create_manual_turn.assert_called_once() 
        args, kwargs = mock_db_ops.create_manual_turn.call_args
        assert kwargs["session_id"] == "sess_def"
        assert kwargs["turn_id"] == result["current_turn"]["turn_id"]
        assert kwargs["index"] == 1


def test_manual_strategy_route_end():
    strategy = ManualStrategy(config={"max_turns": 3})
    
    # Mock state and context for routing
    state = {
        "strategy_context": {
            "session_id": "sess_jkl",
            "iteration_count": 0,
            "max_turns": 3,
            "history": []
        },
        "current_turn": {"turn_id": "turn_mno"}
    }

    route_result = strategy.route(state)
    
    assert route_result["routing_signal"] == RoutingSignals.END
    assert route_result["strategy_context"]["iteration_count"] == 0 # Should not increment here
    assert route_result["strategy_context"]["session_id"] == "sess_jkl"

def test_manual_strategy_get_dependency_schema():
    schema = ManualStrategy.get_dependency_schema()
    assert schema["type"] == "object"
    assert "max_turns" in schema["properties"]
    assert schema["properties"]["max_turns"]["default"] == 100
    assert schema["required"] == []
