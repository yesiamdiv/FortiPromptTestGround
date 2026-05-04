"""
Defense Configuration Routes

Endpoints for managing defense configuration per run.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

from server.database.connection import get_db


router = APIRouter()


class FilterConfig(BaseModel):
    """Filter configuration"""
    name: str
    enabled: bool


class DefenseConfig(BaseModel):
    """Defense configuration schema"""
    filters: List[FilterConfig] = []
    model: Optional[str] = None
    parameters: Dict[str, Any] = {}


# ============================================================================
# Defense Configuration
# ============================================================================

@router.get("/runs/{run_id}/defense/config")
async def get_defense_config(run_id: str):
    """Get defense configuration for a run"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    run = await db.runs.find_one({"run_id": run_id})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    defense_config = run.get("config", {}).get("defence_config", {})
    return defense_config


@router.put("/runs/{run_id}/defense/config")
async def update_defense_config(run_id: str, config: DefenseConfig):
    """Update defense configuration for a run"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    # Verify run exists
    run = await db.runs.find_one({"run_id": run_id})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Update config
    result = await db.runs.update_one(
        {"run_id": run_id},
        {"$set": {"config.defence_config": config.dict(exclude_none=True)}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Failed to update config")
    
    return config


# ============================================================================
# Defense Responses
# ============================================================================

@router.get("/runs/{run_id}/defense/responses")
async def get_defense_responses(run_id: str):
    """Get all defense responses for a run"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    from server.database.operations import get_db_ops
    db_ops = get_db_ops(db)
    
    # Verify run exists
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Get defenses and evaluations
    defences = await db_ops.get_defences(run_id)
    evaluations = await db_ops.get_evaluations(run_id)
    
    # Create evaluation lookup
    eval_by_index = {e["index"]: e for e in evaluations}
    
    # Format responses
    responses = []
    for defence in defences:
        index = defence["index"]
        evaluation = eval_by_index.get(index)
        
        # Determine evaluation status
        if defence["was_blocked"]:
            eval_status = "blocked"
        elif evaluation and evaluation.get("success"):
            eval_status = "passed"
        else:
            eval_status = "failed_filter"
        
        responses.append({
            "promptId": f"prompt-{index:03d}",
            "defenseResponse": defence["response"],
            "evaluation": eval_status,
            "blockedAt": defence.get("metadata", {}).get("blocked_by"),
            "timestamp": defence["timestamp"],
            "wasBlocked": defence["was_blocked"]
        })
    
    return responses


# ============================================================================
# Defense Statistics
# ============================================================================

@router.get("/runs/{run_id}/defense/stats")
async def get_defense_stats(run_id: str):
    """Get defense statistics for a run"""
    db = get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database not connected")
    
    from server.database.operations import get_db_ops
    db_ops = get_db_ops(db)
    
    # Get run
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    # Get defenses and evaluations
    defences = await db_ops.get_defences(run_id)
    evaluations = await db_ops.get_evaluations(run_id)
    
    if not defences:
        return {
            "totalResponses": 0,
            "blockedCount": 0,
            "passedCount": 0,
            "overallDefenseScore": 0,
            "filterPerformance": {}
        }
    
    # Calculate basic stats
    total_responses = len(defences)
    blocked_count = sum(1 for d in defences if d["was_blocked"])
    
    # Evaluate passed count (not blocked AND evaluation exists and failed)
    eval_by_index = {e["index"]: e for e in evaluations}
    passed_count = 0
    for defence in defences:
        if not defence["was_blocked"]:
            evaluation = eval_by_index.get(defence["index"])
            if evaluation and evaluation.get("success"):
                passed_count += 1
    
    # Calculate defense score (percentage blocked)
    overall_defense_score = (blocked_count / total_responses * 100) if total_responses > 0 else 0
    
    # Filter performance (if metadata available)
    filter_performance = {}
    for defence in defences:
        if defence["was_blocked"]:
            blocked_by = defence.get("metadata", {}).get("blocked_by", "unknown")
            if blocked_by not in filter_performance:
                filter_performance[blocked_by] = {
                    "blocked": 0,
                    "falsePositives": 0
                }
            filter_performance[blocked_by]["blocked"] += 1
    
    return {
        "totalResponses": total_responses,
        "blockedCount": blocked_count,
        "passedCount": passed_count,
        "overallDefenseScore": round(overall_defense_score, 2),
        "filterPerformance": filter_performance
    }