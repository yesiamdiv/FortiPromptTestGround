"""
API Routes

FastAPI routes for the adversarial testing engine.
"""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from typing import List
from datetime import datetime

from server.api.schemas import (
    CreateRunRequest,
    CreateRunResponse,
    RunResponse,
    StepResponse,
    HealthResponse,
    ListStrategiesResponse,
    StrategyInfo,
    ErrorResponse
)
from server.database.connection import get_db
from server.websocket.manager import get_ws_manager
from engine.workflow_engine import WorkflowEngine
from strategies.default_strategy import DefaultStrategy


router = APIRouter()


# Global engine instance (will be injected on startup)
_engine: WorkflowEngine = None


def set_engine(engine: WorkflowEngine):
    """Set the global engine instance"""
    global _engine
    _engine = engine


def get_engine() -> WorkflowEngine:
    """Get the global engine instance"""
    if _engine is None:
        raise HTTPException(status_code=500, detail="Engine not initialized")
    return _engine


# ============================================================================
# Run Management Routes
# ============================================================================

@router.post("/runs/create", response_model=CreateRunResponse)
async def create_run(request: CreateRunRequest, background_tasks: BackgroundTasks):
    """
    Create and start a new adversarial run.
    
    The run executes in the background, and updates are sent via WebSocket.
    """
    try:
        engine = get_engine()
        
        # Create strategy instance
        # TODO: Support multiple strategies via registry
        if request.strategy == "default":
            strategy = DefaultStrategy(request.strategy_config)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown strategy: {request.strategy}"
            )
        
        # Prepare initial payload
        initial_payload = {
            "intent": request.intent,
            "target": request.target,
            "user_id": request.user_id,
            "session_id": request.session_id,
            "tags": request.tags,
            "description": request.description
        }
        
        # Generate run ID
        import uuid
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        
        # Start run in background
        async def run_in_background():
            try:
                await engine.execute_run(
                    initial_payload=initial_payload,
                    strategy=strategy,
                    run_id=run_id
                )
            except Exception as e:
                print(f"Background run error: {e}")
        
        background_tasks.add_task(run_in_background)
        
        return CreateRunResponse(
            run_id=run_id,
            status="running",
            message="Run started successfully",
            websocket_url=f"/ws/{run_id}"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    """Get details of a specific run"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    run = await db.runs.find_one({"run_id": run_id})
    
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Remove MongoDB _id field
    run.pop("_id", None)
    
    return RunResponse(**run)


@router.get("/runs/{run_id}/steps", response_model=List[StepResponse])
async def get_run_steps(run_id: str):
    """Get all steps for a run"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    # Verify run exists
    run = await db.runs.find_one({"run_id": run_id})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Get steps
    steps_cursor = db.steps.find({"run_id": run_id}).sort("timestamp", 1)
    steps = await steps_cursor.to_list(length=None)
    
    # Remove MongoDB _id fields
    for step in steps:
        step.pop("_id", None)
    
    return [StepResponse(**step) for step in steps]


@router.get("/runs", response_model=List[RunResponse])
async def list_runs(
    status: str = None,
    limit: int = 100,
    offset: int = 0
):
    """List all runs with optional filtering"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    # Build query
    query = {}
    if status:
        query["status"] = status
    
    # Get runs
    runs_cursor = db.runs.find(query).sort("started_at", -1).skip(offset).limit(limit)
    runs = await runs_cursor.to_list(length=limit)
    
    # Remove MongoDB _id fields
    for run in runs:
        run.pop("_id", None)
    
    return [RunResponse(**run) for run in runs]


# ============================================================================
# Strategy Management Routes
# ============================================================================

@router.get("/strategies", response_model=ListStrategiesResponse)
async def list_strategies():
    """List all available strategies"""
    # TODO: Implement strategy registry
    strategies = [
        StrategyInfo(
            name="default",
            description="Default testing strategy with random attacks",
            config_schema={
                "max_attempts": "int - Maximum number of attack attempts",
                "attack_prefix": "str - Prefix for generated attacks"
            }
        )
    ]
    
    return ListStrategiesResponse(strategies=strategies)


# ============================================================================
# Health & Status Routes
# ============================================================================

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    db = get_db()
    engine = get_engine()
    
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0",
        database_connected=db is not None,
        active_runs=len(engine.list_active_runs()) if engine else 0
    )


# ============================================================================
# WebSocket Route
# ============================================================================

@router.websocket("/ws/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint for real-time run updates.
    
    Clients connect to this endpoint to receive live updates as a run progresses.
    """
    ws_manager = get_ws_manager()
    
    await ws_manager.connect(websocket, run_id)
    
    try:
        # Keep connection alive and handle client messages
        while True:
            data = await websocket.receive_text()
            
            # Echo back for debugging (can be removed)
            await websocket.send_json({
                "type": "echo",
                "data": data
            })
            
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
