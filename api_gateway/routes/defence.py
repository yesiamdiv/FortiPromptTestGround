# api_gateway/routes/defence.py
from fastapi import APIRouter, HTTPException, status
from api_gateway.schemas import DefenseConfig  # Assuming this schema exists

router = APIRouter()

@router.get("/api/runs/{runId}/defense/config", response_model=DefenseConfig)
async def get_defense_config(runId: str):
    """Retrieves the defense configuration for a specific run."""
    pass

@router.put("/api/runs/{runId}/defense/config", response_model=DefenseConfig)
async def update_defense_config(runId: str, config: DefenseConfig):
    """Creates or updates the defense configuration for a specific run."""
    pass

@router.get("/api/runs/{runId}/defense/responses")
async def get_defense_responses(runId: str):
    """Retrieves all defense responses generated for a run."""
    pass

@router.get("/api/runs/{runId}/defense/stats")
async def get_defense_stats(runId: str):
    """Retrieves statistics about the defense phase of a run."""
    pass