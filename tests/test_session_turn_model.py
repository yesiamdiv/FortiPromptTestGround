"""
Tests for the unified Session/Turn data model (Phase 2 Step 2.11).

Verifies:
- Session created on run start
- Turn created per cycle with correct index
- All three _data_id refs populated after a full cycle
- get_turns_for_session returns turns in correct order
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_db_ops():
    """Create a DatabaseOperations mock with all needed async methods."""
    db_ops = MagicMock()
    db_ops.sessions = MagicMock()
    db_ops.sessions.insert_one = AsyncMock(return_value=MagicMock())
    db_ops.sessions.find_one = AsyncMock(return_value=None)
    db_ops.sessions.update_one = AsyncMock(return_value=MagicMock())
    db_ops.turns = MagicMock()
    db_ops.turns.insert_one = AsyncMock(return_value=MagicMock())
    db_ops.turns.find_one = AsyncMock(return_value=None)
    db_ops.turns.update_one = AsyncMock(return_value=MagicMock())

    # Patch find().sort().to_list() chain
    find_mock = MagicMock()
    sort_mock = MagicMock()
    sort_mock.to_list = AsyncMock(return_value=[])
    find_mock.sort = MagicMock(return_value=sort_mock)
    db_ops.turns.find = MagicMock(return_value=find_mock)
    db_ops.sessions.find = MagicMock(return_value=find_mock)

    return db_ops


# ---------------------------------------------------------------------------
# Session tests
# ---------------------------------------------------------------------------

class TestSessionCreation:
    @pytest.mark.asyncio
    async def test_create_session_inserts_document(self):
        from server.database.operations import DatabaseOperations

        db_ops = make_db_ops()
        db_ops.__class__ = DatabaseOperations  # duck-type for the call

        # Call the real method directly
        ops = DatabaseOperations.__new__(DatabaseOperations)
        ops.sessions = db_ops.sessions
        ops.turns = db_ops.turns

        session_id = await ops.create_session(
            session_id="sess_test001",
            run_id="run_abc",
            name="Test Session",
            run_type="automatic",
        )

        assert session_id == "sess_test001"
        db_ops.sessions.insert_one.assert_awaited_once()
        doc = db_ops.sessions.insert_one.call_args[0][0]
        assert doc["session_id"] == "sess_test001"
        assert doc["run_id"] == "run_abc"
        assert doc["run_type"] == "automatic"
        assert doc["status"] == "active"
        assert doc["total_turns"] == 0

    @pytest.mark.asyncio
    async def test_create_session_sets_timestamps(self):
        from server.database.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        db_ops = make_db_ops()
        ops.sessions = db_ops.sessions
        ops.turns = db_ops.turns

        await ops.create_session("sess_ts", "run_ts", "TS Session", "batch")
        doc = db_ops.sessions.insert_one.call_args[0][0]
        assert "created_at" in doc
        assert "updated_at" in doc
        # Both should be valid ISO strings
        datetime.fromisoformat(doc["created_at"])
        datetime.fromisoformat(doc["updated_at"])


# ---------------------------------------------------------------------------
# Turn tests
# ---------------------------------------------------------------------------

class TestTurnCreation:
    @pytest.mark.asyncio
    async def test_create_turn_inserts_and_appends_to_session(self):
        from server.database.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        db_ops = make_db_ops()
        ops.sessions = db_ops.sessions
        ops.turns = db_ops.turns

        turn_id = await ops.create_turn(
            session_id="sess_001",
            turn_id="turn_aaa",
            run_id="run_abc",
            index=0,
        )

        assert turn_id == "turn_aaa"
        db_ops.turns.insert_one.assert_awaited_once()
        turn_doc = db_ops.turns.insert_one.call_args[0][0]
        assert turn_doc["turn_id"] == "turn_aaa"
        assert turn_doc["session_id"] == "sess_001"
        assert turn_doc["index"] == 0
        assert turn_doc["attack_data_id"] is None
        assert turn_doc["defence_data_id"] is None
        assert turn_doc["evaluation_data_id"] is None

        # Session should be updated with $push
        db_ops.sessions.update_one.assert_awaited_once()
        update_call = db_ops.sessions.update_one.call_args[0]
        assert update_call[0] == {"session_id": "sess_001"}
        assert "turn_ids" in update_call[1]["$push"]

    @pytest.mark.asyncio
    async def test_update_turn_references_sets_all_ids(self):
        from server.database.operations import DatabaseOperations

        ops = DatabaseOperations.__new__(DatabaseOperations)
        db_ops = make_db_ops()
        ops.turns = db_ops.turns

        await ops.update_turn_references(
            "turn_aaa",
            attack_data_id="atk_1",
            defence_data_id="def_1",
            evaluation_data_id="eval_1",
        )

        db_ops.turns.update_one.assert_awaited_once()
        update_doc = db_ops.turns.update_one.call_args[0][1]["$set"]
        assert update_doc["attack_data_id"] == "atk_1"
        assert update_doc["defence_data_id"] == "def_1"
        assert update_doc["evaluation_data_id"] == "eval_1"

    @pytest.mark.asyncio
    async def test_get_turns_for_session_returns_ordered_list(self):
        from server.database.operations import DatabaseOperations
        from server.database.models import Turn

        ops = DatabaseOperations.__new__(DatabaseOperations)
        db_ops = make_db_ops()
        now = datetime.utcnow().isoformat()
        raw_docs = [
            {"turn_id": f"turn_{i}", "session_id": "sess_001", "run_id": "run_abc",
             "index": i, "attack_data_id": None, "defence_data_id": None,
             "evaluation_data_id": None, "created_at": now, "updated_at": now, "metadata": {}}
            for i in range(3)
        ]
        sort_mock = MagicMock()
        sort_mock.to_list = AsyncMock(return_value=raw_docs)
        find_mock = MagicMock()
        find_mock.sort = MagicMock(return_value=sort_mock)
        db_ops.turns.find = MagicMock(return_value=find_mock)
        ops.turns = db_ops.turns

        turns = await ops.get_turns_for_session("sess_001")
        assert len(turns) == 3
        assert [t.index for t in turns] == [0, 1, 2]
        assert all(isinstance(t, Turn) for t in turns)
