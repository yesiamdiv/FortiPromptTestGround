"""
Run lifecycle endpoints: create, start, stop, delete, list, get detail.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from typing import Dict, Any
import uuid

from server.api.schemas import (
    CreateRunRequest, UpdateRunRequest, RunResponse, RunDetailsResponse, ListRunsResponse,
)
from server.run_manager import get_run_manager, RunManager, RunStatus
from server.database.connection import get_db
from server.database.operations import DatabaseOperations, get_db_ops
from core.logging import checkpoint, debug, err, tracer, step, warn
from datetime import datetime
from strategies.batch_data_manager import delete_prompts_for_run


router = APIRouter()


async def _get_db_ops_dependency():
    db = get_db()
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database not connected.")
    return get_db_ops(db)


@router.post("/runs", response_model=RunDetailsResponse, status_code=status.HTTP_201_CREATED)
async def create_new_run(
    request: CreateRunRequest,
    run_manager: RunManager = Depends(get_run_manager),
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """
    Create a new adversarial run.

    Initialises a run record in the database but does not start execution.
    """
    tracer("Creating new run", name=request.name)
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    try:
        run_data = {
            "run_id": run_id,
            "name": request.name,
            "description": request.description,
            "graph_config": {
                **request.config.model_dump(exclude_unset=True),
                "strategy_config": {
                    "strategy_name": request.config.strategy_config.strategy_name,
                    "strategy_params": request.config.strategy_config.strategy_params or {}
                }
            },
            "created_at": datetime.utcnow().isoformat(),
            "status": RunStatus.IDLE.value
        }

        await db_ops.create_run(run_data)
        step("Run created", run_id=run_id)

        created_run = await db_ops.get_run(run_id)
        return RunDetailsResponse(**created_run.dict())
    except Exception as e:
        err(f"Failed to create run: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create run: {str(e)}")


@router.patch("/runs/{run_id}", response_model=RunDetailsResponse)
async def update_run_config(
    run_id: str,
    request: UpdateRunRequest,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """Update configuration for an existing run before or during idle state."""
    debug("Updating run config", run_id=run_id)
    try:
        run = await db_ops.get_run(run_id)
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run with ID {run_id} not found.")

        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.description is not None:
            updates["description"] = request.description
        if request.strategy_params is not None:
            updates["graph_config.strategy_config.strategy_params"] = request.strategy_params
        if request.attack_node_params is not None:
            updates["graph_config.attack_node_config.node_params"] = request.attack_node_params
        if request.defense_node_params is not None:
            updates["graph_config.defense_node_config.node_params"] = request.defense_node_params
        if request.evaluation_node_params is not None:
            updates["graph_config.evaluation_node_config.node_params"] = request.evaluation_node_params

        if updates:
            updates["updated_at"] = datetime.utcnow().isoformat()
            await db_ops.update_run(run_id, updates)
            updated_run = await db_ops.get_run(run_id)
            if not updated_run:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve updated run.")
            step("Run config updated", run_id=run_id)
            return RunDetailsResponse(**updated_run.dict())
        else:
            return RunDetailsResponse(**run.dict())

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update run {run_id}: {str(e)}")


@router.delete("/runs/{run_id}")
async def delete_run(
    run_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """Delete a run record. Associated run data (attacks, defences, evaluations) is not deleted."""
    tracer("Deleting run", run_id=run_id)
    try:
        if await db_ops.delete_run(run_id):
            delete_prompts_for_run(run_id)
            step("Run deleted", run_id=run_id)
            return {"message": f"{run_id} is deleted"}
        else:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete run")
    except Exception as e:
        err(f"Failed to delete run: {e}")
        raise e


@router.post("/runs/{run_id}/start", response_model=RunResponse)
async def start_existing_run(
    run_id: str,
    payload: Dict[str, Any] = {},
    run_manager: RunManager = Depends(get_run_manager),
    db_ops: Any = Depends(_get_db_ops_dependency)
):
    """
    Start an existing adversarial run.

    For automatic runs, begins the attack/defence/eval loop.
    For manual runs, initiates the first turn or resumes from a waiting state.
    """
    tracer("start_existing_run", run_id=run_id)
    try:
        run_response = await run_manager.start_run(run_id, input_payload=payload)
        step("Run started", run_id=run_id, status=run_response.get("status") if isinstance(run_response, dict) else run_response.status)
        return RunResponse(**run_response)
    except ValueError as e:
        err("Run not found for start", run_id=run_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RuntimeError as e:
        err("Invalid run state for start", run_id=run_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        err("Failed to start run", run_id=run_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to start run: {str(e)}")


@router.post("/runs/{run_id}/stop", response_model=RunResponse)
async def stop_running_run(
    run_id: str,
    run_manager: RunManager = Depends(get_run_manager)
):
    """Stop a currently running adversarial run."""
    tracer("stop_running_run", run_id=run_id)
    try:
        response = await run_manager.stop_run(run_id)
        step("Run stopped", run_id=run_id)
        return RunResponse(**response)
    except ValueError as e:
        err("Run not found for stop", run_id=run_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        err("Failed to stop run", run_id=run_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to stop run: {str(e)}")


@router.get("/runs", response_model=ListRunsResponse)
async def list_all_runs(db_ops: Any = Depends(_get_db_ops_dependency)):
    """Retrieve a list of all adversarial runs."""
    tracer("list_all_runs")
    try:
        runs = await db_ops.list_runs()
        step("Runs listed", count=len(runs))
        return ListRunsResponse(runs=runs)
    except Exception as e:
        err("Failed to list runs", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list runs: {str(e)}")


@router.get("/runs/{run_id}", response_model=RunDetailsResponse)
async def get_run_details(
    run_id: str,
    db_ops: Any = Depends(_get_db_ops_dependency)
):
    """Retrieve detailed information about a specific adversarial run."""
    debug("Getting run details", run_id=run_id)
    try:
        run = await db_ops.get_run(run_id)
        if not run:
            warn(f"Run not found", run_id=run_id)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run with ID {run_id} not found.")
        checkpoint("Run details retrieved", run_id=run_id)
        return RunDetailsResponse(**run.dict())
    except HTTPException as e:
        raise e
    except Exception as e:
        err(f"Failed to get run details: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get run details: {str(e)}")
