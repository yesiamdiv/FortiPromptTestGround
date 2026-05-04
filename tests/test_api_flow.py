import pytest
import pytest_asyncio
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch
import asyncio

# Assuming the main FastAPI app is in server/main.py
# and database operations are in server/database/operations.py
# and socketio manager is in server/websocket/socketio_manager.py
# and RunManager is in server/run_manager.py
# We will import the app in a fixture and mock dependencies
from server.main import app

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest_asyncio.fixture
async def client():
    async with AsyncClient(client=app, base_url="http://test") as client:
        yield client

@pytest.fixture
def mock_get_db_ops():
    with patch("server.database.operations.get_db_ops") as mock_db_ops:
        mock_collection = AsyncMock()
        mock_collection.insert_one.return_value.inserted_id = "test_id"
        mock_db_ops.return_value.runs_collection = mock_collection
        mock_db_ops.return_value.sessions_collection = mock_collection
        yield mock_db_ops

@pytest.fixture
def mock_socketio_manager():
    with patch("server.websocket.socketio_manager.get_socketio_manager") as mock_sio_manager:
        yield mock_sio_manager

@pytest.fixture
def mock_run_manager():
    with patch("server.run_manager.RunManager") as mock_manager:
        mock_manager_instance = AsyncMock()
        mock_manager.from_run_id.return_value = mock_manager_instance
        mock_manager.from_session_id.return_value = mock_manager_instance
        yield mock_manager

@pytest.mark.asyncio
async def test_automatic_run_flow(client, mock_get_db_ops, mock_run_manager, mock_socketio_manager):
    # Test POST /runs to create an automatic run
    run_config_payload = {
        "graph_config": {
            "type": "Automatic",
            "max_turns": 10,
            "attack_strategy_name": "default",
            "defense_strategy_name": "default",
        },
        "llm_config": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 1000
        },
        "eval_config": {
            "max_turns": 5
        },
        "description": "Test Automatic Run",
        "human_input_mode": "NEVER"
    }
    response = await client.post("/runs", json=run_config_payload)
    assert response.status_code == 200
    run_data = response.json()
    assert run_data["id"] == "test_id"
    mock_get_db_ops.return_value.runs_collection.insert_one.assert_called_once()

    # Test POST /runs/{run_id}/start to trigger it
    run_id = run_data["id"]
    response = await client.post(f"/runs/{run_id}/start")
    assert response.status_code == 200
    assert response.json() == {"message": f"Run {run_id} started."}
    
    # Verify RunManager.from_run_id and start_run were called
    mock_run_manager.from_run_id.assert_called_once_with(run_id)
    mock_run_manager.from_run_id.return_value.start_run.assert_called_once()
    mock_socketio_manager.return_value.emit_event.assert_called_once()


@pytest.mark.asyncio
async def test_manual_session_flow(client, mock_get_db_ops, mock_run_manager, mock_socketio_manager):
    # First, create a mock run for the session to attach to
    mock_run_id = "mock_run_id_for_manual_session"
    mock_get_db_ops.return_value.runs_collection.insert_one.return_value.inserted_id = mock_run_id
    run_config_payload = {
        "graph_config": {
            "type": "Manual",
            "max_turns": 5,
            "attack_strategy_name": "default",
            "defense_strategy_name": "default",
        },
        "llm_config": {
            "provider": "openai",
            "model": "gpt-4o",
            "temperature": 0.7,
            "max_tokens": 1000
        },
        "eval_config": {
            "max_turns": 5
        },
        "description": "Test Manual Run for Session",
        "human_input_mode": "NEVER"
    }
    await client.post("/runs", json=run_config_payload) # Create a dummy run

    # Test POST /runs/{run_id}/sessions to create a manual session
    session_payload = {
        "description": "Test Manual Session",
        "max_turns": 3,
        "human_input_mode": "NEVER"
    }
    response = await client.post(f"/runs/{mock_run_id}/sessions", json=session_payload)
    assert response.status_code == 200
    session_data = response.json()
    assert session_data["id"] == "test_id" # This comes from mock_collection.insert_one.return_value.inserted_id
    mock_get_db_ops.return_value.sessions_collection.insert_one.assert_called_once()

    # Test POST /runs/{run_id}/sessions/{session_id}/manual_turn
    session_id = session_data["id"]
    manual_turn_payload = {
        "input_data": "user input for manual turn"
    }
    response = await client.post(f"/runs/{mock_run_id}/sessions/{session_id}/manual_turn", json=manual_turn_payload)
    assert response.status_code == 200
    assert response.json() == {"message": f"Manual turn submitted for session {session_id}"}

    # Verify RunManager.from_session_id and submit_manual_turn were called
    mock_run_manager.from_session_id.assert_called_once_with(session_id)
    mock_run_manager.from_session_id.return_value.submit_manual_turn.assert_called_once_with(manual_turn_payload["input_data"])
    # Two calls to emit_event, one for session creation, one for manual turn submission
    assert mock_socketio_manager.return_value.emit_event.call_count == 2
