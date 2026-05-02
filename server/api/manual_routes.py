"""
Manual Attack API Routes

Endpoints for managing manual attack sessions and turns.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import uuid

from server.database.connection import get_db
from server.database.manual_operations import get_manual_ops
from server.run_manager import get_run_manager
from server.websocket.socketio_manager import get_socketio_manager


router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class CreateSessionRequest(BaseModel):
    name: str
    description: str = ""
    defense_config: Dict[str, Any] = {}
    domain_notes: str = ""


class AddTurnRequest(BaseModel):
    prompt: str
    role: str = "attacker"
    metadata: Dict[str, Any] = {}


class ManualConfigRequest(BaseModel):
    defense_type: str = "default"
    defense_params: Dict[str, Any] = {}
    evaluation_type: str = "default"
    evaluation_params: Dict[str, Any] = {}
    domain: str = "general"
    domain_notes: str = ""
    auto_evaluate: bool = True


# ============================================================================
# Manual Config Endpoints
# ============================================================================

@router.get("/runs/{run_id}/manual/config")
async def get_manual_config(run_id: str):
    """Get manual run configuration"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    manual_ops = get_manual_ops(db)
    config = await manual_ops.get_manual_config(run_id)
    
    if config is None:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return config


@router.put("/runs/{run_id}/manual/config")
async def update_manual_config(run_id: str, config: ManualConfigRequest):
    """Update manual run configuration"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    manual_ops = get_manual_ops(db)
    success = await manual_ops.update_manual_config(run_id, config.dict())
    
    if not success:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return config


# ============================================================================
# Session Management Endpoints
# ============================================================================

@router.get("/runs/{run_id}/manual/sessions")
async def list_sessions(run_id: str, status: Optional[str] = None):
    """List all sessions for a run"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    manual_ops = get_manual_ops(db)
    sessions = await manual_ops.list_sessions(run_id, status=status)
    
    return sessions


@router.post("/runs/{run_id}/manual/sessions")
async def create_session(run_id: str, request: CreateSessionRequest):
    """Create a new interactive chat session"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    # Generate session ID
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    
    manual_ops = get_manual_ops(db)
    session = await manual_ops.create_session(
        run_id=run_id,
        session_id=session_id,
        name=request.name,
        description=request.description,
        defense_config=request.defense_config,
        domain_notes=request.domain_notes
    )
    
    # Broadcast session creation
    socketio_manager = get_socketio_manager()
    await socketio_manager.broadcast_to_room(
        run_id,
        'manual_session_created',
        {
            'session_id': session_id,
            'name': request.name,
            'status': 'active'
        }
    )
    
    return session


@router.get("/runs/{run_id}/manual/sessions/{session_id}")
async def get_session(run_id: str, session_id: str):
    """Get session details with full history"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    manual_ops = get_manual_ops(db)
    
    # Get session
    session = await manual_ops.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get all turns
    turns = await manual_ops.get_session_turns(session_id)
    
    return {
        "session": session,
        "turns": turns
    }


@router.post("/runs/{run_id}/manual/sessions/{session_id}/turns")
async def add_turn(run_id: str, session_id: str, request: AddTurnRequest):
    """
    Add a new turn to the session.
    
    If role is 'attacker', triggers async defense and evaluation.
    """
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    manual_ops = get_manual_ops(db)
    
    # Verify session exists
    session = await manual_ops.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get current turn count
    turn_index = session.get("turn_count", 0)
    turn_id = f"{session_id}_turn_{turn_index}"
    
    # Add turn
    turn = await manual_ops.add_turn(
        session_id=session_id,
        turn_id=turn_id,
        turn_index=turn_index,
        role=request.role,
        attack_prompt=request.prompt,
        metadata=request.metadata
    )
    
    # If attacker role, trigger async processing
    if request.role == "attacker":
        # Trigger defense and evaluation via run manager
        run_manager = get_run_manager()
        
        try:
            # This will trigger the manual attack node to process
            await run_manager.provide_manual_input(
                run_id,
                {
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "attack_prompt": request.prompt
                }
            )
        except Exception as e:
            print(f"Error processing turn: {e}")
            # Don't fail the request, turn is saved
    
    return turn


@router.post("/runs/{run_id}/manual/sessions/{session_id}/save")
async def save_session(run_id: str, session_id: str):
    """
    Save the session and trigger evaluation scoring.
    
    Marks session as 'saved' and calculates final statistics.
    """
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    manual_ops = get_manual_ops(db)
    
    # Save session
    success = await manual_ops.save_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get updated session with stats
    session = await manual_ops.get_session(session_id)
    
    # Broadcast save event
    socketio_manager = get_socketio_manager()
    await socketio_manager.broadcast_to_room(
        run_id,
        'manual_session_saved',
        {
            'session_id': session_id,
            'status': 'saved',
            'statistics': {
                'total_attacks': session.get('total_attacks', 0),
                'successful_attacks': session.get('successful_attacks', 0),
                'average_score': session.get('average_score')
            }
        }
    )
    
    return {
        "message": "Session saved successfully",
        "session": session
    }


@router.delete("/runs/{run_id}/manual/sessions/{session_id}")
async def delete_session(run_id: str, session_id: str):
    """Delete a session and all its turns"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    manual_ops = get_manual_ops(db)
    
    success = await manual_ops.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Broadcast deletion
    socketio_manager = get_socketio_manager()
    await socketio_manager.broadcast_to_room(
        run_id,
        'manual_session_deleted',
        {'session_id': session_id}
    )
    
    return {"message": "Session deleted successfully"}


# ============================================================================
# Statistics Endpoint
# ============================================================================

@router.get("/runs/{run_id}/manual/stats")
async def get_manual_stats(run_id: str):
    """Get statistics for the manual run"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    manual_ops = get_manual_ops(db)
    stats = await manual_ops.get_manual_stats(run_id)
    
    return stats
