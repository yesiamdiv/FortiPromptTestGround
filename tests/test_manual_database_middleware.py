# test_manual_database_middleware.py

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

from middlewares.manual_database_middleware import ManualDatabaseMiddleware
from engine.state_schema import SystemState, RoutingSignals
from server.database.models_v2 import ManualTurn, ManualSession # Import Pydantic models


@pytest.fixture
def mock_db_ops():
    return MagicMock()

@pytest.pytest.fixture
def manual_db_middleware(mock_db_ops):
    # Mock get_db_ops to return our mock
    with patch("middlewares.manual_database_middleware.get_db_ops", return_value=mock_db_ops):
        yield ManualDatabaseMiddleware()

@pytest.mark.asyncio
async def test_manual_db_middleware_before_run_new_session(manual_db_middleware, mock_db_ops):
    mock_initial_state_no_session = {
        "run_id": "test_run_manual_db_1",
        "config": {"strategy_config": {"strategy_name": "manual"}},
        "payload": {"session_id": "sess_abc", "prompt": "Initial prompt"},
        "start_time": datetime.utcnow().isoformat()
    }
    mock_db = MagicMock()
    manual_db_middleware.db = mock_db

    # Mock create_manual_session to return a new session ID
    mock_db_ops.return_value.create_manual_session = AsyncMock(return_value="sess_abc")
    mock_db_ops.return_value.get_last_manual_turn_for_session = AsyncMock(return_value=None) # No prior turns
    mock_db_ops.return_value.update_run = AsyncMock() # Mock update_run

    with patch("middlewares.manual_database_middleware.get_db", return_value=mock_db):
        await manual_db_middleware.before_run(mock_initial_state_no_session, {}, "test_run_manual_db_1")

        mock_db_ops.assert_called_once_with(mock_db)
        db_ops_instance = mock_db_ops.return_value
        db_ops_instance.create_manual_session.assert_called_once_with(run_id="test_run_manual_db_1", name=pytest.approx("Run test_run_manual_db_1"), description=None)
        db_ops_instance.get_last_manual_turn_for_session.assert_called_once_with("sess_abc")
        db_ops_instance.update_run.assert_called_once_with("test_run_manual_db_1", {"status": "idle", "manual_wait_active": True})

def test_manual_db_middleware_before_run_existing_session(manual_db_middleware, mock_db_ops):
    mock_initial_state_with_session = {
        "run_id": "test_run_manual_db_2",
        "config": {"strategy_config": {"strategy_name": "manual"}},
        "payload": {"session_id": "sess_def", "prompt": "User turn 2"},
        "start_time": datetime.utcnow().isoformat()
    }
    mock_db = MagicMock()
    manual_db_middleware.db = mock_db

    # Mock fetching last turn data
    mock_last_turn = ManualTurn(
        session_id="sess_def", turn_id="turn_1", run_id="test_run_manual_db_2", index=0, attack_prompt="Initial attack"
    )
    mock_db_ops.return_value.get_last_manual_turn_for_session = AsyncMock(return_value=mock_last_turn)
    mock_db_ops.return_value.create_manual_turn = AsyncMock()
    mock_db_ops.return_value.update_run = AsyncMock()

    with patch("middlewares.manual_database_middleware.get_db", return_value=mock_db):
        manual_db_middleware.before_run(mock_initial_state_with_session, {}, "test_run_manual_db_2")

        mock_db_ops.assert_called_once_with(mock_db)
        db_ops_instance = mock_db_ops.return_value
        db_ops_instance.get_last_manual_turn_for_session.assert_called_once_with("sess_def")
        assert mock_initial_state_with_session["strategy_context"]["history"] == ["Initial attack"]
        assert mock_initial_state_with_session["strategy_context"]["iteration_count"] == 1
        db_ops_instance.create_manual_turn.assert_called_once()
        db_ops_instance.update_run.assert_called_once_with("test_run_manual_db_2", {"status": "idle"})

@pytest.mark.asyncio
async def test_manual_db_middleware_after_step_attack(manual_db_middleware, mock_db_ops):
    mock_step_data = {
        "attack": {
            "current_turn": {
                "turn_id": "turn_xyz",
                "attack": MagicMock(to_string=lambda: "Attack prompt", metadata={"tag": "a"}),
                "timestamp": datetime.utcnow().isoformat()
            },
            "strategy_context": {"iteration_count": 1, "session_id": "sess_def"}
        }
    }
    run_id = "test_run_manual_db_3"
    
    await manual_db_middleware.after_step(mock_step_data, run_id)
    
    mock_db_ops_instance = mock_db_ops.return_value
    mock_db_ops_instance.update_manual_turn_data.assert_called_once_with(
        session_id="sess_def",
        turn_id="turn_xyz",
        iteration=1,
        attack_prompt="Attack prompt",
        attack_metadata={"tag": "a"}
    )

@pytest.mark.asyncio
async def test_manual_db_middleware_after_run(manual_db_middleware, mock_db_ops):
    mock_final_state = {
        "strategy_context": {"iteration_count": 1, "best_score": 0.75, "session_id": "sess_def"},
        "current_turn": {"evaluation": MagicMock(score=0.75, success=True, category="cat", feedback="Good eval", to_summary=lambda: "Eval Summary")}
    }
    run_id = "test_run_manual_db_4"

    # Mock session retrieval if needed
    mock_session = ManualSession(session_id="sess_def", run_id="test_run_manual_db_4", name="Session 1", turn_ids=["turn_xyz"])
    mock_db_ops.return_value.get_manual_session = AsyncMock(return_value=mock_session)
    mock_db_ops.return_value.update_manual_session_state = AsyncMock()
    mock_db_ops.return_value.update_run = AsyncMock()

    await manual_db_middleware.after_run(mock_final_state, run_id)
    
    mock_db_ops_instance = mock_db_ops.return_value
    mock_db_ops_instance.get_manual_session.assert_called_once_with("sess_def")
    mock_db_ops_instance.update_manual_session_state.assert_called_once_with(
        session_id="sess_def",
        run_id="test_run_manual_db_4",
        state_checkpoint=mock_final_state,
        final_score=0.75,
        best_score=0.75
    )
    mock_db_ops_instance.update_run.assert_called_once_with("test_run_manual_db_4", {"status": "idle"})

async def test_manual_db_middleware_on_error(manual_db_middleware, mock_db_ops):
    error = Exception("Manual test error")
    run_id = "test_run_manual_db_5"
    
    await manual_db_middleware.on_error(error, run_id)
    
    mock_db_ops_instance = mock_db_ops.return_value
    mock_db_ops_instance.mark_run_failed.assert_called_once_with(run_id, "Manual test error")

async def test_manual_db_middleware_missing_session_id_before_run(manual_db_middleware, mock_db_ops):
    mock_initial_state_missing_session = {
        "run_id": "test_run_manual_db_6",
        "config": {"strategy_config": {"strategy_name": "manual"}},
        "payload": {"prompt": "User turn 1"} # Missing session_id
    }
    mock_db = MagicMock()
    manual_db_middleware.db = mock_db

    with patch("middlewares.manual_database_middleware.get_db", return_value=mock_db):
        with pytest.raises(ValueError, match="Manual run requires a 'session_id' in the payload"): 
            manual_db_middleware.before_run(mock_initial_state_missing_session, {}, "test_run_manual_db_6")

