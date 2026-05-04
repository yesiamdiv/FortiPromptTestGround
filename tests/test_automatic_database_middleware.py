# test_automatic_database_middleware.py

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from middlewares.automatic_database_middleware import AutomaticDatabaseMiddleware
from engine.state_schema import SystemState, RoutingSignals


@pytest.fixture
def mock_db_ops():
    return MagicMock()

@pytest.pytest.fixture
def automatic_db_middleware(mock_db_ops):
    # Mock get_db_ops to return our mock
    with patch("middlewares.automatic_database_middleware.get_db_ops", return_value=mock_db_ops):
        yield AutomaticDatabaseMiddleware()

@pytest.mark.asyncio
async def test_automatic_db_middleware_before_run(automatic_db_middleware, mock_db_ops):
    mock_initial_state = {
        "run_id": "test_run_db_auto_1",
        "start_time": datetime.utcnow().isoformat(),
        "config": {
            "strategy_config": {"strategy_name": "test_auto_strategy"}
        },
        "payload": {"intent": "find vulnerability"}
    }
    mock_config = {"configurable": {"strategy": MagicMock(name="test_auto_strategy")}} 
    run_id = "test_run_db_auto_1"

    # Mock get_db to return a mock database object
    mock_db = MagicMock()
    automatic_db_middleware.db = mock_db # Assign mock db to middleware

    with patch("middlewares.automatic_database_middleware.get_db", return_value=mock_db):
        await automatic_db_middleware.before_run(mock_initial_state, mock_config, run_id)

        mock_db_ops.assert_called_once_with(mock_db)
        mock_db_ops_instance = mock_db_ops.return_value
        mock_db_ops_instance.create_run.assert_called_once()
        created_run_data = mock_db_ops_instance.create_run.call_args[1]
        assert created_run_data["run_id"] == run_id
        assert created_run_data["strategy"] == "test_auto_strategy"
        assert created_run_data["intent"] == "find vulnerability"

async def test_automatic_db_middleware_after_step_attack(automatic_db_middleware, mock_db_ops):
    mock_step_data = {
        "attack": {
            "current_turn": {
                "turn_id": "turn_A",
                "attack": MagicMock(to_string=lambda: "Attack prompt", metadata={"tag": "a"})
            },
            "strategy_context": {"iteration_count": 1}
        }
    }
    run_id = "test_run_db_auto_2"
    
    await automatic_db_middleware.after_step(mock_step_data, run_id)
    
    mock_db_ops_instance = mock_db_ops.return_value
    mock_db_ops_instance.save_attack.assert_called_once_with(
        run_id=run_id,
        index=1,
        turn_id="turn_A",
        prompt="Attack prompt",
        metadata={"tag": "a"}
    )

async def test_automatic_db_middleware_after_step_defence(automatic_db_middleware, mock_db_ops):
    mock_step_data = {
        "defence": {
            "current_turn": {
                "turn_id": "turn_B",
                "defence": MagicMock(get_text=lambda: "Defense response", status_code=200, was_blocked=False, metadata={"tag": "d"})
            }
        }
    }
    run_id = "test_run_db_auto_2"
    
    await automatic_db_middleware.after_step(mock_step_data, run_id)
    
    mock_db_ops_instance = mock_db_ops.return_value
    mock_db_ops_instance.save_defence.assert_called_once_with(
        run_id=run_id,
        index=0, # Default iteration count is 0 if not in context
        turn_id="turn_B",
        response="Defense response",
        status_code=200,
        was_blocked=False,
        metadata={"tag": "d"}
    )

async def test_automatic_db_middleware_after_step_eval(automatic_db_middleware, mock_db_ops):
    mock_step_data = {
        "eval": {
            "current_turn": {
                "turn_id": "turn_C",
                "evaluation": MagicMock(score=0.8, success=True, category="cat", feedback="Good", metadata={"tag": "e"})
            }
        }
    }
    run_id = "test_run_db_auto_2"
    
    await automatic_db_middleware.after_step(mock_step_data, run_id)
    
    mock_db_ops_instance = mock_db_ops.return_value
    mock_db_ops_instance.save_evaluation.assert_called_once_with(
        run_id=run_id,
        index=0, # Default iteration count is 0 if not in context
        turn_id="turn_C",
        score=0.8,
        success=True,
        category="cat",
        feedback="Good",
        metadata={"tag": "e"}
    )

async def test_automatic_db_middleware_after_run(automatic_db_middleware, mock_db_ops):
    mock_final_state = {
        "strategy_context": {"iteration_count": 2, "best_score": 0.85},
        "current_turn": {"evaluation": MagicMock(score=0.8, success=True)}
    }
    run_id = "test_run_db_auto_3"

    await automatic_db_middleware.after_run(mock_final_state, run_id)
    
    mock_db_ops_instance = mock_db_ops.return_value
    mock_db_ops_instance.mark_run_completed.assert_called_once_with(
        run_id=run_id,
        final_score=0.8,
        best_score=0.85
    )

async def test_automatic_db_middleware_on_error(automatic_db_middleware, mock_db_ops):
    error = Exception("Test error")
    run_id = "test_run_db_auto_4"

    await automatic_db_middleware.on_error(error, run_id)
    
    mock_db_ops_instance = mock_db_ops.return_value
    mock_db_ops_instance.mark_run_failed.assert_called_once_with(run_id, "Test error")

async def test_automatic_db_middleware_no_db_connection(automatic_db_middleware, mock_db_ops):
    # Ensure no DB operations are called if DB is not connected
    automatic_db_middleware.db = None
    mock_step_data = {"attack": {"current_turn": {"attack": MagicMock(to_string=lambda: "Attack")}}}
    run_id = "test_run_db_auto_5"
    
    with patch("builtins.print") as mock_print:
        await automatic_db_middleware.before_run(initial_state={}, config={}, run_id=run_id)
        mock_db_ops.assert_not_called()
        mock_print.assert_called_with("⚠️  Database not connected, skipping persistence")
        
        await automatic_db_middleware.after_step(mock_step_data, run_id)
        mock_db_ops.assert_not_called()
        
        await automatic_db_middleware.after_run({}, run_id)
        mock_db_ops.assert_not_called()
        
        await automatic_db_middleware.on_error(Exception("Test error"), run_id)
        mock_db_ops.assert_not_called()

