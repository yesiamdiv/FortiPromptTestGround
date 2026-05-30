"""
Run data endpoints: retrieve attacks, defences, evaluations, and statistics for a run.

These endpoints will be extended significantly in Phase 2 to support the
unified Session/Turn data model. The flat collection endpoints are kept as-is
for backwards compatibility.
"""

from fastapi import APIRouter, HTTPException, Depends, status
from typing import Any

from server.database.connection import get_db
from server.database.operations import DatabaseOperations, get_db_ops
from core.logging import tracer


router = APIRouter()


async def _get_db_ops_dependency():
    db = get_db()
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database not connected.")
    return get_db_ops(db)


@router.get("/runs/{run_id}/attacks")
async def get_run_attacks(
    run_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """Get all attacks recorded for a run."""
    tracer("Getting run attacks", run_id=run_id)
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found.")
    attacks = await db_ops.get_attacks(run_id)
    return {"attacks": [a.dict() for a in attacks]}


@router.get("/runs/{run_id}/defences")
async def get_run_defences(
    run_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """Get all defences recorded for a run."""
    tracer("Getting run defences", run_id=run_id)
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found.")
    defences = await db_ops.get_defences(run_id)
    return {"defences": [d.dict() for d in defences]}


@router.get("/runs/{run_id}/evaluations")
async def get_run_evaluations(
    run_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """Get all evaluations recorded for a run."""
    tracer("Getting run evaluations", run_id=run_id)
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found.")
    evaluations = await db_ops.get_evaluations(run_id)
    return {"evaluations": [e.dict() for e in evaluations]}


@router.get("/runs/{run_id}/stats")
async def get_run_stats(
    run_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """Get computed statistics for a run."""
    tracer("Getting run stats", run_id=run_id)
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found.")

    attacks = await db_ops.get_attacks(run_id)
    defences = await db_ops.get_defences(run_id)
    evaluations = await db_ops.get_evaluations(run_id)

    total = len(evaluations)
    successes = sum(1 for e in evaluations if e.success)
    blocked = sum(1 for d in defences if d.was_blocked)
    scores = [e.score for e in evaluations]

    categories: dict = {}
    for e in evaluations:
        categories[e.category] = categories.get(e.category, 0) + 1

    return {
        "run_id": run_id,
        "total_attacks": len(attacks),
        "total_defences": len(defences),
        "total_evaluations": total,
        "success_rate": successes / total if total else 0.0,
        "blocked_rate": blocked / len(defences) if defences else 0.0,
        "average_score": sum(scores) / len(scores) if scores else 0.0,
        "best_score": max(scores) if scores else None,
        "categories": categories,
    }
