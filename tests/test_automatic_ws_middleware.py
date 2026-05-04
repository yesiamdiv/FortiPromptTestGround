# test_automatic_ws_middleware.py

import pytest
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime

from middlewares.automatic_ws_middleware import AutomaticWSMiddleware
from engine.state_schema import SystemState, RoutingSignals


@pytest.fixture
def mock_ws_ops():
    return MagicMock()

@pytest.pytest.fixture
def automatic_ws_middleware(mock_ws_ops):
    # Mock get_ws_ops to return our mock
    with patch("middlewares.automatic_ws_middleware.get_ws_ops", return_value=mock_ws_ops):
        yield AutomaticWSMiddleware(socketio_manager=MagicMock()) # Provide a mock socketio_manager

@pytest.mark.asyncio
async def test_automatic_ws_middleware_before_run(automatic_ws_middleware, mock_ws_ops):
    mock_initial_state = {
        "run_id": "test_run_ws_auto_1",
        "start_time": datetime.utcnow().isoformat(),
        "config": {
            "strategy_config": {"strategy_name": "test_auto_strategy"}
        },
        "payload": {"intent": "find vulnerability"}
    }
    mock_config = {"configurable": {"strategy": MagicMock(name="test_auto_strategy")}} 
    run_id = "test_run_ws_auto_1"

    await automatic_ws_middleware.before_run(mock_initial_state, mock_config, run_id)

    mock_ws_ops_instance = mock_ws_ops.return_value
    mock_ws_ops_instance.broadcast_run_started.assert_called_once_with(
        run_id,
        {
            'strategy': 'test_auto_strategy',
            'intent': 'find vulnerability',
            'target': None,
            'timestamp': mock_initial_state['start_time']
        }
    )

@pytest.mark.asyncio
async def test_automatic_ws_middleware_after_step_attack(automatic_ws_middleware, mock_ws_ops):
    mock_step_data = {
        "attack": {
            "current_turn": {
                "turn_id": "turn_A",
                "attack": MagicMock(to_string=lambda: "Mock attack prompt...", metadata={"tag": "a"}),
                "timestamp": datetime.utcnow().isoformat()
            },
            "strategy_context": {"iteration_count": 1}
        }
    }
    run_id = "test_run_ws_auto_2"
    
    await automatic_ws_middleware.after_step(mock_step_data, run_id)
    
    mock_ws_ops_instance = mock_ws_ops.return_value
    mock_ws_ops_instance.broadcast_attack_generated.assert_called_once_with(
        run_id,
        "turn_A",
        1,
        {
            'preview': 'Mock attack prompt...', 
            'full_text': 'Mock attack prompt...', 
            'type': 'text', 
            'metadata': {'tag': 'a'},
            'timestamp': mock_step_data['attack']['current_turn']['timestamp']
        }
    )

async def test_automatic_ws_middleware_after_step_defence(automatic_ws_middleware, mock_ws_ops):
    mock_step_data = {
        "defence": {
            "current_turn": {
                "turn_id": "turn_B",
                "defence": MagicMock(get_text=lambda: "Defense response", status_code=200, was_blocked=False, get_latency_ms=lambda: 50, metadata={"tag": "d"}),
                "timestamp": datetime.utcnow().isoformat()
            }
        }
    }
    run_id = "test_run_ws_auto_2"
    
    await automatic_ws_middleware.after_step(mock_step_data, run_id)
    
    mock_ws_ops_instance = mock_ws_ops.return_value
    mock_ws_ops_instance.broadcast_defence_response.assert_called_once_with(
        run_id,
        "turn_B",
        0, # Default iteration count is 0
        {
            'preview': 'Defense response', 
            'full_text': 'Defense response', 
            'status_code': 200, 
            'was_blocked': False, 
            'latency_ms': 50,
            'timestamp': mock_step_data['defence']['current_turn']['timestamp']
        }
    )

async def test_automatic_ws_middleware_after_step_eval(automatic_ws_middleware, mock_ws_ops):
    mock_step_data = {
        "eval": {
            "current_turn": {
                "turn_id": "turn_C",
                "evaluation": MagicMock(score=0.8, success=True, category="cat", feedback="Good", to_summary=lambda: "Eval Summary", metadata={"tag": "e"})
            }
        }
    }
    run_id = "test_run_ws_auto_2"
    
    await automatic_ws_middleware.after_step(mock_step_data, run_id)
    
    mock_ws_ops_instance = mock_ws_ops.return_value
    mock_ws_ops_instance.broadcast_evaluation_complete.assert_called_once_with(
        run_id,
        "turn_C",
        0,
        {
            'score': 0.8,
            'success': True,
            'category': 'cat',
            'reasoning': 'Good',
            'summary': 'Eval Summary',
            'timestamp': mock_step_data['eval']['current_turn']['timestamp']
        }
    )
    mock_ws_ops_instance.broadcast_turn_completed.assert_called_once_with(
        run_id,
        "turn_C",
        0
    )

async def test_automatic_ws_middleware_after_run(automatic_ws_middleware, mock_ws_ops):
    mock_final_state = {
        "strategy_context": {"iteration_count": 2, "best_score": 0.85, "session_id": "sess_1"},
        "current_turn": {"evaluation": MagicMock(score=0.8, success=True, to_summary=lambda: "Final Eval Summary")},
        "routing_signal": RoutingSignals.END
    }
    run_id = "test_run_ws_auto_3"

    await automatic_ws_middleware.after_run(mock_final_state, run_id)
    
    mock_ws_ops_instance = mock_ws_ops.return_value
    mock_ws_ops_instance.broadcast_run_completed.assert_called_once_with(
        run_id,
        {
            'total_attempts': 2,
            'routing_signal': RoutingSignals.END,
            'timestamp': mock_final_state['current_turn']['timestamp'],
            'final_evaluation': {
                'score': 0.8,
                'success': True,
                'category': None, # Assumes category is None if not set in mock
                'summary': 'Final Eval Summary'
            }
        }
    )

async def test_automatic_ws_middleware_on_error(automatic_ws_middleware, mock_ws_ops):
    error = Exception("Test error")
    run_id = "test_run_ws_auto_4"
    
    await automatic_ws_middleware.on_error(error, run_id)
    
    mock_ws_ops_instance = mock_ws_ops.return_value
    mock_ws_ops_instance.broadcast_run_error.assert_called_once_with(
        run_id,
        error="Test error",
        error_type="Exception"
    )

async def test_automatic_ws_middleware_broadcast_routing(automatic_ws_middleware, mock_ws_ops):
    mock_node_output = {
        "routing_signal": RoutingSignals.ATTACK,
        "strategy_context": {"iteration_count": 5, "max_turns": 10}
    }
    run_id = "test_run_ws_auto_5"
    
    await automatic_ws_middleware._broadcast_routing(run_id, mock_node_output)
    
    mock_ws_ops_instance = mock_ws_ops.return_value
    mock_ws_ops_instance.broadcast_run_progress.assert_called_once_with(
        run_id,
        current=5,
        total=10,
        message="Routing: ATTACK"
    )

async def test_automatic_ws_middleware_missing_session_id_in_start(automatic_ws_middleware, mock_ws_ops):
    mock_initial_state = {
        "run_id": "test_run_ws_auto_6",
        "start_time": datetime.utcnow().isoformat(),
        "config": {"strategy_config": {"strategy_name": "test_auto_strategy"}},
        "payload": {"intent": "find vulnerability"} # No session_id here
    }
    mock_config = {"configurable": {"strategy": MagicMock(name="test_auto_strategy")}} 
    run_id = "test_run_ws_auto_6"

    await automatic_ws_middleware.before_run(mock_initial_state, mock_config, run_id)
    # Expecting broadcast_run_started to be called without session_id or with None
    # The method handles this by not joining a room if session_id is None.
    mock_ws_ops_instance = mock_ws_ops.return_value
    mock_ws_ops_instance.broadcast_run_started.assert_called_once()
    called_kwargs = mock_ws_ops_instance.broadcast_run_started.call_args[1]
    assert 'session_id' not in called_kwargs or called_kwargs['session_id'] is None

