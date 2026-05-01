"""
Attack Configuration Routes

Endpoints for managing attack configuration per run.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from pydantic import BaseModel

from server.database.connection import get_db


router = APIRouter()


class AttackConfig(BaseModel):
    """Attack configuration schema"""
    model: Optional[str] = None
    attack_strategy: Optional[str] = None
    domain: Optional[str] = None
    model_url: Optional[str] = None
    iterations: Optional[int] = None
    parameters: Dict[str, Any] = {}


# ============================================================================
# Attack Configuration
# ============================================================================

@router.get("/runs/{run_id}/attack/config")
async def get_attack_config(run_id: str):
    """Get attack configuration for a run"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    run = await db.runs.find_one({"run_id": run_id})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    attack_config = run.get("config", {}).get("attack_config", {})
    return attack_config


@router.put("/runs/{run_id}/attack/config")
async def update_attack_config(run_id: str, config: AttackConfig):
    """Update attack configuration for a run"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    # Verify run exists
    run = await db.runs.find_one({"run_id": run_id})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Update config
    result = await db.runs.update_one(
        {"run_id": run_id},
        {"$set": {"config.attack_config": config.dict(exclude_none=True)}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update config")
    
    return config


# ============================================================================
# Attack Prompts
# ============================================================================

@router.get("/runs/{run_id}/attack/prompts")
async def get_attack_prompts(run_id: str):
    """Get all attack prompts for a run"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    from server.database.operations import get_db_ops
    db_ops = get_db_ops(db)
    
    # Verify run exists
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Get attacks
    attacks = await db_ops.get_attacks(run_id)
    
    # Format as prompts with status
    prompts = []
    for attack in attacks:
        prompts.append({
            "promptId": f"prompt-{attack['index']:03d}",
            "content": attack["prompt"],
            "status": attack.get("metadata", {}).get("status", "generated"),
            "timestamp": attack["timestamp"]
        })
    
    return prompts


# ============================================================================
# Attack Statistics
# ============================================================================

@router.get("/runs/{run_id}/attack/stats")
async def get_attack_stats(run_id: str):
    """Get attack statistics for a run"""
    db = get_db()
    if not db:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    from server.database.operations import get_db_ops
    db_ops = get_db_ops(db)
    
    # Get run
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Get attacks and evaluations
    attacks = await db_ops.get_attacks(run_id)
    evaluations = await db_ops.get_evaluations(run_id)
    
    # Calculate stats
    total_prompts = len(attacks)
    
    # Determine pending attacks (attacks without evaluations)
    evaluated_indices = {e["index"] for e in evaluations}
    attack_indices = {a["index"] for a in attacks}
    pending_indices = attack_indices - evaluated_indices
    
    pending_attacks = len(pending_indices)
    attacks_generated = total_prompts
    
    # Count by status if available
    status_counts = {}
    for attack in attacks:
        status = attack.get("metadata", {}).get("status", "generated")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    return {
        "totalPrompts": total_prompts,
        "pendingAttacks": pending_attacks,
        "attacksGenerated": attacks_generated,
        "statusBreakdown": status_counts
    }