"""
API Endpoints for Manual Run Sessions and Turns"""

from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Dict, Any, Optional
import uuid
from datetime import datetime

from server.api.schemas import (
    CreateManualSessionRequest, ManualSessionResponse, SubmitManualTurnRequest,
    ManualTurnResponse, ManualTurnHistoryResponse, RunResponse
)
from server.run_manager import get_run_manager, RunManager, RunStatus
from server.database.connection import get_db
from server.database.operations import get_db_ops
from server.database.models_v2 import ManualTurn, ManualSession, AttackData, DefenceData, EvaluationData # Import Pydantic models
from engine.state_schema import SystemState, RoutingSignals # For type hinting state_checkpoint
from server.websocket.socketio_manager import get_socketio_manager # Import for broadcasting


router = APIRouter()

async def _get_db_ops_dependency():
    db = get_db()
    if not db:
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
    try:
        run = await db_ops.get_run(run_id)
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run with ID {run_id} not found.")
        
        # Ensure the run is configured for manual sessions
        if run.graph_config.graph_type != "manual":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run is not configured for manual sessions.")
        
        session_id = await db_ops.create_manual_session(
            run_id=run_id,
            name=request.name,
            description=request.description
        )
        
        # If initial_payload is provided, process it as the first turn's input
        if request.initial_payload:
            run_manager = get_run_manager()
            # This initiates the first turn of the manual graph execution
            await run_manager.start_run(
                run_id=run_id,
                input_payload={**request.initial_payload, "session_id": session_id}
            )
            
        session = await db_ops.get_manual_session(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve created session.")
        return ManualSessionResponse(**session.dict())
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create manual session: {str(e)}")

@router.post("/runs/{run_id}/sessions/{session_id}/manual_turn", response_model=RunResponse)
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
    try:
        session = await db_ops.get_manual_session(session_id)
        if not session or session.run_id != run_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Manual session {session_id} not found for run {run_id}.")
        
        # Prepare payload for the RunExecutor
        payload = {
            "session_id": session_id,
            "prompt": request.prompt,
            "runtime_config": request.runtime_config
        }
        
        # Resume the run with the new manual input
        run_response = await run_manager.start_run(run_id, input_payload=payload)
        return RunResponse(**run_response)
    except HTTPException as e:
        raise e
    except Exception as e:
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
    try:
        session = await db_ops.get_manual_session(session_id)
        if not session or session.run_id != run_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Manual session {session_id} not found for run {run_id}.")
        return ManualSessionResponse(**session.dict())
    except HTTPException as e:
        raise e
    except Exception as e:
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
    try:
        session = await db_ops.get_manual_session(session_id)
        if not session or session.run_id != run_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Manual session {session_id} not found for run {run_id}.")
        
        turns = await db_ops.get_manual_turns_for_session(session_id)
        
        detailed_turns = []
        for turn in turns:
            attack_data = None
            # Use the correct fields from ManualTurn model for data retrieval
            if turn.attack_data_id:
                attack_data = await db_ops.get_attack(turn.attack_data_id) # Assuming get_attack exists and fetches by ID
            
            defence_data = None
            if turn.defence_data_id:
                defence_data = await db_ops.get_defence(turn.defence_data_id) # Assuming get_defence exists and fetches by ID
            
            evaluation_data = None
            if turn.evaluation_data_id:
                evaluation_data = await db_ops.get_evaluation(turn.evaluation_data_id) # Assuming get_evaluation exists and fetches by ID

            detailed_turns.append(ManualTurnResponse(
                **turn.dict(),
                attack_data=attack_data,
                defence_data=defence_data,
                evaluation_data=evaluation_data
            ))

        return ManualTurnHistoryResponse(session=session, turns=detailed_turns)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get manual turn history: {str(e)}")

