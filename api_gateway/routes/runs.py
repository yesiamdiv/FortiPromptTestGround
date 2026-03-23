from fastapi import APIRouter, HTTPException, status, Depends
from typing import List

from db.db_client import DatabaseClient

from ..schemas import AttackRequest, Run, RunInDB
from api_gateway.main import get_db_client

router = APIRouter()


@router.post("/runs", status_code=status.HTTP_201_CREATED, response_model=Run)
async def create_run(attack_request: AttackRequest, db_client: DatabaseClient = Depends(get_db_client)):
    # Placeholder for run creation logic
    # This will likely involve creating a new Run object,
    # storing it in the database, and returning it.
    try:
        # Example: Create a Run object from the request
        new_run = Run(name=attack_request.run_id, status="created")
        # Store the run in the database using db_client
        db_client.create_run(new_run)
        return new_run
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/runs/{run_id}/start")
async def start_run(run_id: str):
    # Placeholder for starting a run
    # This will likely involve fetching the run from the database,
    # and then starting the attack process in the engine.
    return {"message": f"Starting run {run_id}"}


@router.put("/runs/{run_id}")
async def update_run(run_id: str):
    # Placeholder for updating a run's configuration
    return {"message": f"Updating run {run_id}"}


@router.get("/runs", response_model=List[Run])
async def get_runs(db_client: DatabaseClient = Depends(get_db_client)):
    # Placeholder for fetching all runs
    try:
        runs = db_client.get_all_runs()
        return runs
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/runs/{run_id}", response_model=Run)
async def get_run(run_id: str, db_client: DatabaseClient = Depends(get_db_client)):
    # Placeholder for fetching a specific run
    try:
        run = db_client.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        return run
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/runs/{run_id}/stop")
async def stop_run(run_id: str):
    # Placeholder for stopping a run
    return {"message": f"Stopping run {run_id}"}
