# api_gateway/routes/attack.py
from fastapi import APIRouter, HTTPException, status
from api_gateway.schemas import AttackConfig  # Assuming this schema exists

router = APIRouter()

@router.get("/api/runs/{runId}/attack/config", response_model=AttackConfig)
async def get_attack_config(runId: str):
    """Retrieves the attack configuration for a specific run."""
    pass

@router.put("/api/runs/{runId}/attack/config", response_model=AttackConfig)
async def update_attack_config(runId: str, config: AttackConfig):
    """Creates or updates the attack configuration for a specific run."""
    pass

@router.get("/api/runs/{runId}/attack/prompts")
async def get_attack_prompts(runId: str):
    """Retrieves all generated attack prompts for a run."""
    pass

@router.get("/api/runs/{runId}/attack/stats")
async def get_attack_stats(runId: str):
    """Retrieves statistics about the attack phase of a run."""
    pass

@router.post("/api/runs/{runId}/attack/start")
async def start_attack(runId: str, resumeFromLastSaved: bool = False):
    """Starts or resumes the attack generation for a run."""
    pass

@router.post("/api/runs/{runId}/attack/stop")
async def stop_attack(runId: str):
    """Stops the ongoing attack generation for a run."""
    pass