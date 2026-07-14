"""
API Endpoints for Manual Run Sessions and Turns
"""

from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime

from server.api.schemas import (
    CreateManualSessionRequest, ManualSessionResponse, SubmitManualTurnRequest,
    ManualTurnResponse, ManualTurnHistoryResponse, RunResponse, SubmitManualTurnResponse
)
from server.run_manager import get_run_manager, RunManager, RunStatus
from server.database.connection import get_db
from server.database.operations import get_db_ops
from core.logging import checkpoint, debug, err, tracer, step, warn
from server.database.models import AttackData, DefenceData, EvaluationData # Import Pydantic models
from engine.state import SystemState, RoutingSignals # For type hinting state_checkpoint
from server.websocket.socketio_manager import get_socketio_manager # Import for broadcasting


router = APIRouter()

async def _get_db_ops_dependency():
    db = get_db()
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database not connected.")
    return get_db_ops(db)

@router.post("/runs/{run_id}/sessions", response_model=ManualSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_manual_session(
    run_id: str,
    request: CreateManualSessionRequest,
    db_ops: Any = Depends(_get_db_ops_dependency)
):
    """
    Create a new manual interaction session within a given run.
    This is the entry point for a human-in-the-loop chat.
    """
    tracer("Creating manual session", run_id=run_id)
    try:
        run = await db_ops.get_run(run_id)
        if not run:
            warn("Run not found", run_id=run_id)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run with ID {run_id} not found.")
        
        # Ensure the run is configured for manual sessions
        if run.graph_config.graph_type != "manual":
            err("Run not configured for manual sessions", run_id=run_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run is not configured for manual sessions.")
        
        # Create session in the unified sessions collection
        import uuid as _uuid
        session_id = f"sess_{_uuid.uuid4().hex[:12]}"
        await db_ops.create_session(
            session_id=session_id,
            run_id=run_id,
            name=request.name,
            run_type="manual",
            description=request.description or "",
        )
        step("Manual session created", session_id=session_id)

        # If initial_payload contains a prompt, fire it as the first turn
        if request.initial_payload and request.initial_payload.get("prompt"):
            run_manager = get_run_manager()
            tracer("Initiating first manual turn from initial_payload", session_id=session_id)
            await run_manager.start_run(
                run_id=run_id,
                input_payload={**request.initial_payload, "session_id": session_id}
            )
            
        session = await db_ops.get_session(session_id)
        if not session:
            err("Failed to retrieve created session", session_id=session_id)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created session.")
        checkpoint("Manual session response ready", session_id=session_id)
        return ManualSessionResponse(**session.dict())
    except HTTPException as e:
        raise e
    except Exception as e:
        err(f"Failed to create manual session: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create manual session: {str(e)}")

@router.post("/runs/{run_id}/sessions/{session_id}/manual_turn", response_model=SubmitManualTurnResponse)
async def submit_manual_turn(
    run_id: str,
    session_id: str,
    request: SubmitManualTurnRequest,
    run_manager: RunManager = Depends(get_run_manager),
    db_ops: Any = Depends(_get_db_ops_dependency)
):
    """
    Submit user input (e.g., an attack prompt) for a manual turn within a session.
    This resumes the manual run's execution for one cycle.
    """
    tracer("Submitting manual turn", run_id=run_id, session_id=session_id)
    try:
        session = await db_ops.get_session(session_id)
        if not session or session.run_id != run_id:
            warn("Manual session not found", session_id=session_id, run_id=run_id)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Manual session {session_id} not found for run {run_id}.")
        
        # Prepare payload for the RunExecutor
        payload = {
            "session_id": session_id,
            "prompt": request.prompt,
            "runtime_config": request.runtime_config
        }
        debug("Prepared manual turn payload", prompt_length=len(request.prompt))
        
        # Resume the run with the new manual input (creates an async task)
        run_response = await run_manager.start_run(run_id, input_payload=payload)
        step("Manual turn submitted", run_id=run_id)
        # The turn_id is generated inside the async task (ManualDatabaseMiddleware.before_run)
        # which hasn't run yet at this point. The authoritative turn_id arrives via the
        # manual_turn_completed WebSocket event. Return "pending" here as a placeholder.
        return SubmitManualTurnResponse(
            run_id=run_id,
            session_id=session_id,
            turn_id="pending",
            status=run_response.get("status", "running")
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        err(f"Failed to submit manual turn: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to submit manual turn: {str(e)}")

@router.get("/runs/{run_id}/sessions/{session_id}", response_model=ManualSessionResponse)
async def get_manual_session_details(
    run_id: str,
    session_id: str,
    db_ops: Any = Depends(_get_db_ops_dependency)
):
    """
    Retrieve details of a specific manual session.
    """
    debug("Getting manual session details", run_id=run_id, session_id=session_id)
    try:
        session = await db_ops.get_session(session_id)
        if not session or session.run_id != run_id:
            warn("Manual session not found", session_id=session_id, run_id=run_id)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Manual session {session_id} not found for run {run_id}.")
        checkpoint("Manual session details retrieved", session_id=session_id)
        return ManualSessionResponse(**session.dict())
    except HTTPException as e:
        raise e
    except Exception as e:
        err(f"Failed to get manual session details: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get manual session details: {str(e)}")

@router.get("/runs/{run_id}/sessions/{session_id}/history", response_model=ManualTurnHistoryResponse)
async def get_manual_turn_history(
    run_id: str,
    session_id: str,
    db_ops: Any = Depends(_get_db_ops_dependency)
):
    """
    Retrieve the complete history of turns for a manual session, including detailed attack/defence/evaluation data.
    """
    tracer("Getting manual turn history", run_id=run_id, session_id=session_id)
    try:
        session = await db_ops.get_session(session_id)
        if not session or session.run_id != run_id:
            warn("Manual session not found", session_id=session_id, run_id=run_id)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Manual session {session_id} not found for run {run_id}.")
        
        turns = await db_ops.get_turns_for_session(session_id)
        debug(f"Found {len(turns)} turns", session_id=session_id)
        
        detailed_turns = []
        for turn in turns:
            attack_data = None
            if turn.attack_data_id:
                attack_data = await db_ops.get_attack_by_id(turn.attack_data_id)
            
            defence_data = None
            if turn.defence_data_id:
                defence_data = await db_ops.get_defence_by_id(turn.defence_data_id)
            
            evaluation_data = None
            if turn.evaluation_data_id:
                evaluation_data = await db_ops.get_evaluation_by_id(turn.evaluation_data_id)

            detailed_turns.append(ManualTurnResponse(
                **turn.dict(),
                attack_data=attack_data,
                defence_data=defence_data,
                evaluation_data=evaluation_data
            ))
        
        checkpoint("Manual turn history built", session_id=session_id, turn_count=len(detailed_turns))
        return ManualTurnHistoryResponse(session=session, turns=detailed_turns)
    except HTTPException as e:
        raise e
    except Exception as e:
        err(f"Failed to get manual turn history: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get manual turn history: {str(e)}")



@router.get("/runs/{run_id}/sessions")
async def list_manual_sessions(
    run_id: str,
    db_ops: Any = Depends(_get_db_ops_dependency)
):
    """List all manual sessions for a run."""
    tracer("Listing manual sessions", run_id=run_id)
    try:
        run = await db_ops.get_run(run_id)
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found.")
        sessions = await db_ops.get_sessions_for_run(run_id)
        return {"sessions": [s.dict() for s in sessions]}
    except HTTPException as e:
        raise e
    except Exception as e:
        err(f"Failed to list manual sessions: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/runs/{run_id}/sessions/{session_id}")
async def delete_manual_session(
    run_id: str,
    session_id: str,
    db_ops: Any = Depends(_get_db_ops_dependency)
):
    """Delete a manual session and its turns."""
    tracer("Deleting manual session", run_id=run_id, session_id=session_id)
    try:
        session = await db_ops.get_session(session_id)
        if not session or session.run_id != run_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found.")
        await db_ops.sessions.delete_one({"session_id": session_id, "run_id": run_id})
        await db_ops.turns.delete_many({"session_id": session_id})
        step("Manual session deleted", session_id=session_id)
        return {"message": f"Session {session_id} deleted successfully"}
    except HTTPException as e:
        raise e
    except Exception as e:
        err(f"Failed to delete manual session: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
