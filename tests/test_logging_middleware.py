# test_logging_middleware.py

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

from middlewares.logging_middleware import LoggingMiddleware
from engine.state_schema import SystemState, RoutingSignals


@pytest.fixture
def logging_middleware():
    return LoggingMiddleware(config={"verbose": True, "timestamps": True})

@pytest.mark.asyncio
async def test_logging_middleware_before_run(logging_middleware):
    mock_initial_state = {
        "run_id": "test_run_log_1",
        "start_time": datetime.utcnow().isoformat(),
        "config": {
            "strategy_config": {"strategy_name": "test_strategy"}
        },
        "payload": {"intent": "test intent"}
    }
    mock_config = {"configurable": {"strategy": MagicMock(name="test_strategy"), "strategy_config": {"strategy_name": "test_strategy"}}}
    run_id = "test_run_log_1"

    # Mock print to capture output
    with patch("builtins.print", new_callable=MagicMock) as mock_print:
        await logging_middleware.before_run(mock_initial_state, mock_config, run_id)
        calls = mock_print.call_args_list
        assert any("🚀 RUN STARTED: test_run_log_1" in str(call) for call in calls)
        assert any("Strategy: test_strategy" in str(call) for call in calls)
        assert any("Intent: test intent" in str(call) for call in calls)

@pytest.mark.asyncio
async def test_logging_middleware_after_step(logging_middleware):
    # Mock step data for different nodes
    mock_step_data_attack = {
        "attack": {
            "current_turn": {
                "turn_id": "turn_1",
                "attack": MagicMock(to_string=lambda: "Mock attack prompt..."),
                "timestamp": datetime.utcnow().isoformat()
            },
            "strategy_context": {"iteration_count": 1, "session_id": "sess_1"}
        }
    }
    mock_step_data_defence = {
        "defence": {
            "current_turn": {
                "turn_id": "turn_1",
                "defence": MagicMock(get_text=lambda: "Mock defense response", was_blocked=False, status_code=200),
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    }
    mock_step_data_eval = {
        "eval": {
            "current_turn": {
                "turn_id": "turn_1",
                "evaluation": MagicMock(score=0.8, success=True, reasoning="Good eval", to_summary=lambda: "Eval Summary")
            }
        }
    }
    mock_step_data_router = {
        "router": {
            "routing_signal": RoutingSignals.ATTACK,
            "strategy_context": {"iteration_count": 2}
        }
    }
    mock_step_data_empty = {}

    run_id = "test_run_log_2"

    with patch("builtins.print", new_callable=MagicMock) as mock_print:
        await logging_middleware.after_step(mock_step_data_attack, run_id)
        calls = mock_print.call_args_list
        assert any("📍 NODE: attack" in str(call) for call in calls)
        assert any("⚔️  Attack: Mock attack prompt..." in str(call) for call in calls)
        
        await logging_middleware.after_step(mock_step_data_defence, run_id)
        assert any("🛡️  Defence: ✅ ALLOWED" in str(call) for call in calls)
        
        await logging_middleware.after_step(mock_step_data_eval, run_id)
        assert any("📊 Eval: Eval Summary" in str(call) for call in calls)
        
        await logging_middleware.after_step(mock_step_data_router, run_id)
        assert any("🔀 Routing: ATTACK" in str(call) for call in calls)
        
        await logging_middleware.after_step(mock_step_data_empty, run_id)
        # No specific log expected for empty step_data, but ensure no crash

def test_logging_middleware_after_run(logging_middleware):
    mock_final_state = {
        "strategy_context": {"iteration_count": 2, "best_score": 0.85, "session_id": "sess_1"},
        "current_turn": {"evaluation": MagicMock(to_summary=lambda: "Final Eval Summary")}
    }
    run_id = "test_run_log_3"
    
    # Mock the run timing storage
    logging_middleware.run_timings[run_id] = datetime.utcnow().timestamp() - 5.5 # Simulate 5.5 seconds duration

    with patch("builtins.print", new_callable=MagicMock) as mock_print:
        asyncio.run(logging_middleware.after_run(mock_final_state, run_id))
        calls = mock_print.call_args_list
        assert any("🏁 RUN COMPLETED: test_run_log_3" in str(call) for call in calls)
        assert any("Duration: 5.50s" in str(call) for call in calls)
        assert any("Final Result: Eval Summary" in str(call) for call in calls)
        assert run_id not in logging_middleware.run_timings # Ensure timing is cleared

def test_logging_middleware_on_error(logging_middleware):
    error = Exception("Something went wrong")
    run_id = "test_run_log_4"
    
    with patch("builtins.print", new_callable=MagicMock) as mock_print:
        asyncio.run(logging_middleware.on_error(error, run_id))
        calls = mock_print.call_args_list
        assert any("❌ ERROR in test_run_log_4: Exception" in str(call) for call in calls)
        assert any("Message: Something went wrong" in str(call) for call in calls)

