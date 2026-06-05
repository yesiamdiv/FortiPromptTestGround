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


# ============================================================================
# Unified Session / Turn endpoints (Phase 2)
# The flat /attacks, /defences, /evaluations endpoints above are kept as
# compatibility shims and are deprecated in docs/api.md.
# ============================================================================

@router.get("/runs/{run_id}/sessions")
async def list_sessions(
    run_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency),
):
    """List all sessions for a run, ordered by creation time."""
    tracer("Listing sessions", run_id=run_id)
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found.")
    sessions = await db_ops.get_sessions_for_run(run_id)
    return {"sessions": [s.dict() for s in sessions]}


@router.get("/runs/{run_id}/sessions/{session_id}")
async def get_session(
    run_id: str,
    session_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency),
):
    """Get session detail plus computed stats."""
    tracer("Getting session", run_id=run_id, session_id=session_id)
    session = await db_ops.get_session(session_id)
    if not session or session.run_id != run_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found.")
    turns = await db_ops.get_turns_for_session(session_id)
    successful = sum(1 for t in turns if t.evaluation_data_id)
    return {
        "session": session.dict(),
        "stats": {
            "total_turns": len(turns),
            "turns_with_evaluation": successful,
        },
    }


@router.get("/runs/{run_id}/sessions/{session_id}/turns")
async def list_turns(
    run_id: str,
    session_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency),
):
    """List all turns for a session with their linked data resolved."""
    tracer("Listing turns", run_id=run_id, session_id=session_id)
    session = await db_ops.get_session(session_id)
    if not session or session.run_id != run_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session {session_id} not found.")
    turns = await db_ops.get_turns_for_session(session_id)

    resolved = []
    for turn in turns:
        entry = turn.dict()
        if turn.attack_data_id:
            atk = await db_ops.get_attack_by_id(turn.attack_data_id)
            entry["attack"] = atk.dict() if atk else None
        if turn.defence_data_id:
            dfn = await db_ops.get_defence_by_id(turn.defence_data_id)
            entry["defence"] = dfn.dict() if dfn else None
        if turn.evaluation_data_id:
            evl = await db_ops.get_evaluation_by_id(turn.evaluation_data_id)
            entry["evaluation"] = evl.dict() if evl else None
        resolved.append(entry)

    return {"turns": resolved}


@router.get("/runs/{run_id}/sessions/{session_id}/turns/{turn_id}")
async def get_turn(
    run_id: str,
    session_id: str,
    turn_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency),
):
    """Get a single turn with all linked data (attack, defence, evaluation) resolved."""
    tracer("Getting turn", run_id=run_id, session_id=session_id, turn_id=turn_id)
    turn = await db_ops.get_turn(turn_id)
    if not turn or turn.session_id != session_id or turn.run_id != run_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Turn {turn_id} not found.")

    entry = turn.dict()
    if turn.attack_data_id:
        atk = await db_ops.get_attack_by_id(turn.attack_data_id)
        entry["attack"] = atk.dict() if atk else None
    if turn.defence_data_id:
        dfn = await db_ops.get_defence_by_id(turn.defence_data_id)
        entry["defence"] = dfn.dict() if dfn else None
    if turn.evaluation_data_id:
        evl = await db_ops.get_evaluation_by_id(turn.evaluation_data_id)
        entry["evaluation"] = evl.dict() if evl else None

    return {"turn": entry}
