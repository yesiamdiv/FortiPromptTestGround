# test_manual_ws_middleware.py

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

from middlewares.manual_ws_middleware import ManualWSMiddleware
from engine.state_schema import SystemState, RoutingSignals


@pytest.fixture
def mock_ws_ops():
    return MagicMock()

@pytest.pytest.fixture
def manual_ws_middleware(mock_ws_ops):
    # Mock get_ws_ops to return our mock
    with patch("middlewares.manual_ws_middleware.get_ws_ops", return_value=mock_ws_ops):
        yield ManualWSMiddleware(socketio_manager=MagicMock()) # Provide a mock socketio_manager

@pytest.mark.asyncio
async def test_manual_ws_middleware_before_run(manual_ws_middleware, mock_ws_ops):
    mock_initial_state = {
        "run_id": "test_run_ws_manual_1",
        "start_time": datetime.utcnow().isoformat(),
        "config": {"strategy_config": {"strategy_name": "manual_strategy"}},
        "payload": {"intent": "find vulnerability", "session_id": "sess_manual_1"}
    }
    mock_config = {"configurable": {"strategy": MagicMock(name="manual_strategy")}} 
    run_id = "test_run_ws_manual_1"
    session_id = "sess_manual_1"

    # Mock join_room method
    manual_ws_middleware.ws_ops.sio_manager.join_room = AsyncMock()

    await manual_ws_middleware.before_run(mock_initial_state, mock_config, run_id)

    mock_ws_ops_instance = mock_ws_ops.return_value
    manual_ws_middleware.ws_ops.sio_manager.join_room.assert_called_once_with(session_id)
    mock_ws_ops_instance.broadcast_run_started.assert_called_once_with(
        run_id,
        {
            'strategy': 'manual_strategy',
            'intent': 'find vulnerability',
            'target': None,
            'timestamp': mock_initial_state['start_time'],
            'session_id': session_id
        }
    )

@pytest.mark.asyncio
async def test_manual_ws_middleware_after_step_attack(manual_ws_middleware, mock_ws_ops):
    mock_step_data = {
        "attack": {
            "current_turn": {
                "turn_id": "turn_A",
                "attack": MagicMock(to_string=lambda: "Mock attack prompt...", metadata={"tag": "a"}),
                "timestamp": datetime.utcnow().isoformat()
            },
            "strategy_context": {"iteration_count": 1, "session_id": "sess_manual_1"}
        }
    }
    run_id = "test_run_ws_manual_2"
    session_id = "sess_manual_1"
    turn_id = "turn_A"
    iteration = 1

    await manual_ws_middleware.after_step(mock_step_data, run_id)
    
    mock_ws_ops_instance = mock_ws_ops.return_value
    mock_ws_ops_instance.broadcast_manual_attack_generated.assert_called_once_with(
        run_id, session_id, turn_id, iteration,
        {"preview": "Mock attack prompt...", "full_text": "Mock attack prompt...", "type": "text", "metadata": {"tag": "a"}, "timestamp": mock_step_data["current_turn"]["timestamp"]}
    )

@pytest.mark.asyncio
async def test_manual_ws_middleware_after_step_defence(manual_ws_middleware, mock_ws_ops):
    mock_step_data = {
        "defence": {
            "current_turn": {
                "turn_id": "turn_B",
                "defence": MagicMock(get_text=lambda: "Defense response", status_code=200, was_blocked=False, get_latency_ms=lambda: 50, metadata={"tag": "d"}),
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    }
    run_id = "test_run_ws_manual_2"
    session_id = "sess_manual_1"
    turn_id = "turn_B"
    iteration = 0 # Default if not in context

    await manual_ws_middleware.after_step(mock_step_data, run_id)
    
    mock_ws_ops_instance = mock_ws_ops.return_value
    mock_ws_ops_instance.broadcast_manual_defence_response.assert_called_once_with(
        run_id, session_id, turn_id, iteration, {
            'preview': 'Defense response',
            'full_text': 'Defense response',
            'status_code': 200,
            'was_blocked': False,
            'latency_ms': 50,
            'timestamp': mock_step_data["current_turn"]["timestamp"]
        }
    )

@pytest.mark.asyncio
async def test_manual_ws_middleware_after_step_eval(manual_ws_middleware, mock_ws_ops):
    mock_step_data = {
        "eval": {
            "current_turn": {
                "turn_id": "turn_C",
                "evaluation": MagicMock(score=0.8, success=True, category="cat", feedback="Good", to_summary=lambda: "Eval Summary", metadata={"tag": "e"})
            }
        }
    }
    run_id = "test_run_ws_manual_2"
    session_id = "sess_manual_1"
    turn_id = "turn_C"
    iteration = 0 # Default if not in context

    await manual_ws_middleware.after_step(mock_step_data, run_id)
    
    mock_ws_ops_instance = mock_ws_ops.return_value
    mock_ws_ops_instance.broadcast_manual_evaluation_complete.assert_called_once_with(
        run_id, session_id, turn_id, iteration, {
            'score': 0.8,
            'success': True,
            'category': 'cat',
            'reasoning': 'Good',
            'summary': 'Eval Summary',
            'timestamp': mock_step_data["current_turn"]["timestamp"]
        }
    )
    mock_ws_ops_instance.broadcast_manual_turn_completed.assert_called_once_with(
        run_id, session_id, turn_id, iteration
    )

@pytest.mark.asyncio
async def test_manual_ws_middleware_after_run(manual_ws_middleware, mock_ws_ops):
    mock_final_state = {
        "strategy_context": {"iteration_count": 2, "max_turns": 5, "session_id": "sess_manual_1"},
        "current_turn": {"turn_id": "turn_D", "timestamp": datetime.utcnow().isoformat()}
    }
    run_id = "test_run_ws_manual_3"
    session_id = "sess_manual_1"

    await manual_ws_middleware.after_run(mock_final_state, run_id)
    
    mock_ws_ops_instance = mock_ws_ops.return_value
    mock_ws_ops_instance.broadcast_run_idle.assert_called_once_with(
        run_id,
        {
            'message': 'Awaiting user input for next turn',
            'last_turn_id': 'turn_D',
            'iteration_count': 2,
            'session_id': session_id
        }
    )

async def test_manual_ws_middleware_on_error(manual_ws_middleware, mock_ws_ops):
    error = Exception("Manual WS test error")
    run_id = "test_run_ws_manual_4"
    
    await manual_ws_middleware.on_error(error, run_id)
    
    mock_ws_ops_instance = mock_ws_ops.return_value
    mock_ws_ops_instance.broadcast_run_error.assert_called_once_with(
        run_id,
        error='Manual WS test error',
        error_type='Exception'
    )

async def test_manual_ws_middleware_missing_session_id_after_step(manual_ws_middleware, mock_ws_ops):
    mock_step_data = {
        "attack": {
            "current_turn": {"turn_id": "turn_E"},
            "strategy_context": {"iteration_count": 1} # Missing session_id
        }
    }
    run_id = "test_run_ws_manual_5"
    
    # Mock print to capture warnings
    with patch("builtins.print", new_callable=MagicMock) as mock_print:
        await manual_ws_middleware.after_step(mock_step_data, run_id)
        mock_ws_ops_instance = mock_ws_ops.return_value
        # Ensure no broadcast methods were called due to missing session_id
        mock_ws_ops_instance.broadcast_manual_attack_generated.assert_not_called()
        mock_print.assert_called_with("[ManualWSMiddleware] Warning: session_id missing in context for node attack. Skipping manual broadcast.")

