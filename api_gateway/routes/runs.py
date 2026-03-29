# api_gateway/routes/runs.py
from fastapi import APIRouter, HTTPException, status
from api_gateway.schemas import Run, RunInDB  # Assuming these schemas exist

router = APIRouter()

@router.get("/api/runs", response_model=list[Run])
async def list_runs():
    """Fetches a list of all test runs."""
    pass

@router.post("/api/runs", status_code=status.HTTP_201_CREATED, response_model=RunInDB)
async def create_run(run: Run):
    """Creates a new test run."""
    pass

@router.patch("/api/runs/{runId}", response_model=RunInDB)
async def update_run(runId: str, run: Run):
    """Updates an existing test run's metadata or status."""
    pass

@router.delete("/api/runs/{runId}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(runId: str):
    """Deletes a test run."""
    pass