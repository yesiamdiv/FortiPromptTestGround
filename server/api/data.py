"""
Run data endpoints: retrieve attacks, defences, evaluations, and statistics for a run.

These endpoints will be extended significantly in Phase 2 to support the
unified Session/Turn data model. The flat collection endpoints are kept as-is
for backwards compatibility.
"""

import csv
import io

from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.responses import StreamingResponse
from typing import Any, Dict, List

from server.database.connection import get_db
from server.database.operations import DatabaseOperations, get_db_ops
from core.logging import tracer


router = APIRouter()


async def _get_db_ops_dependency():
    db = get_db()
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database not connected.")
    return get_db_ops(db)


async def _build_turn_session_map(db_ops: DatabaseOperations, run_id: str) -> dict:
    """Build {turn_id: session_id} map for all turns in a run."""
    turns = await db_ops.get_turns_for_run(run_id)
    return {t.turn_id: t.session_id for t in turns}


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
    turn_map = await _build_turn_session_map(db_ops, run_id)
    result = []
    for a in attacks:
        d = a.dict()
        d["session_id"] = turn_map.get(a.turn_id)
        result.append(d)
    return {"attacks": result}


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
    turn_map = await _build_turn_session_map(db_ops, run_id)
    result = []
    for d in defences:
        entry = d.dict()
        entry["session_id"] = turn_map.get(d.turn_id)
        result.append(entry)
    return {"defences": result}


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
    turn_map = await _build_turn_session_map(db_ops, run_id)
    result = []
    for e in evaluations:
        entry = e.dict()
        entry["session_id"] = turn_map.get(e.turn_id)
        result.append(entry)
    return {"evaluations": result}


@router.get("/runs/{run_id}/stats")
async def get_run_stats(
    run_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """Get basic aggregate statistics for a run."""
    tracer("Getting run stats", run_id=run_id)
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found.")

    attacks = await db_ops.get_attacks(run_id)
    defences = await db_ops.get_defences(run_id)
    evaluations = await db_ops.get_evaluations(run_id)

    blocked = sum(1 for d in defences if d.was_blocked)
    breaches = sum(1 for e in evaluations if e.success)
    total_eval = len(evaluations)

    return {
        "total_attacks": len(attacks),
        "total_defences": len(defences),
        "blocked_defences": blocked,
        "passed_defences": len(defences) - blocked,
        "total_evaluations": total_eval,
        "breaches": breaches,
        "defended": total_eval - breaches,
        "breach_rate": breaches / total_eval if total_eval else 0.0,
    }


@router.get("/runs/{run_id}/stats/charts")
async def get_run_charts(
    run_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """Get dynamic chart data for a run (defence layer breakdown, eval categories, etc.)."""
    tracer("Getting run charts", run_id=run_id)
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found.")

    defences = await db_ops.get_defences(run_id)
    evaluations = await db_ops.get_evaluations(run_id)

    charts = []

    # ── Defence layer breakdown (pie chart) ──
    layer_counts: dict = {}
    for d in defences:
        if d.was_blocked and d.metadata:
            layer = d.metadata.get("blocked_by")
            if layer:
                layer_counts[layer] = layer_counts.get(layer, 0) + 1

    if layer_counts:
        colours = ["#EF4444", "#F59E0B", "#3B82F6", "#8B5CF6", "#EC4899", "#14B8A6", "#84CC16"]
        charts.append({
            "id": "defence-layer-breakdown",
            "title": "Blocks by Defence Layer",
            "type": "pie",
            "data": [
                {"label": layer, "value": count, "color": colours[i % len(colours)]}
                for i, (layer, count) in enumerate(sorted(layer_counts.items(), key=lambda x: -x[1]))
            ],
        })

    # ── Evaluation category breakdown (pie chart) ──
    category_counts: dict = {}
    for e in evaluations:
        cat = e.category or "unknown"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    if category_counts:
        colours = ["#DC2626", "#F59E0B", "#6366F1", "#22C55E", "#EC4899", "#14B8A6", "#84CC16"]
        charts.append({
            "id": "eval-category-breakdown",
            "title": "Evaluations by Category",
            "type": "pie",
            "data": [
                {"label": cat, "value": count, "color": colours[i % len(colours)]}
                for i, (cat, count) in enumerate(sorted(category_counts.items(), key=lambda x: -x[1]))
            ],
        })

    return {"charts": charts}


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


# ============================================================================
# Export
# ============================================================================

def _clean_turn(row: dict) -> dict:
    """Extract only research-relevant fields from a raw turn tuple."""
    atk = row.get("attack") or {}
    dfn = row.get("defence") or {}
    evl = row.get("evaluation") or {}
    return {
        "turn_index": row.get("index"),
        "session_id": row.get("session_id"),
        "attack_prompt": atk.get("prompt"),
        "attack_metadata": atk.get("metadata"),
        "defence_response": dfn.get("response"),
        "defence_was_blocked": dfn.get("was_blocked"),
        "defence_status_code": dfn.get("status_code"),
        "defence_blocked_by": (dfn.get("metadata") or {}).get("blocked_by"),
        "eval_score": evl.get("score"),
        "eval_success": evl.get("success"),
        "eval_category": evl.get("category"),
        "eval_feedback": evl.get("feedback"),
    }


@router.get("/runs/{run_id}/export")
async def export_run(
    run_id: str,
    format: str = Query("json", regex="^(json|csv)$"),
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency),
):
    """Export run data as clean research-ready tuples (attack/defence/eval per turn).

    Supports ?format=json (default) and ?format=csv.
    """
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found.")

    graph_type = run.graph_config.graph_type
    rows: List[Dict] = []

    if graph_type == "manual":
        sessions = await db_ops.get_sessions_for_run(run_id)
        for sess in sessions:
            turns = await db_ops.get_turns_for_session(sess.session_id)
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
                rows.append(_clean_turn(entry))
    else:
        attacks = await db_ops.get_attacks(run_id)
        defences = await db_ops.get_defences(run_id)
        evaluations = await db_ops.get_evaluations(run_id)

        atk_by_idx = {a.index: a for a in attacks}
        dfn_by_idx = {d.index: d for d in defences}
        evl_by_idx = {e.index: e for e in evaluations}

        all_indices = sorted(set(atk_by_idx) | set(dfn_by_idx) | set(evl_by_idx))
        for idx in all_indices:
            a = atk_by_idx.get(idx)
            d = dfn_by_idx.get(idx)
            e = evl_by_idx.get(idx)
            rows.append(_clean_turn({
                "index": idx,
                "session_id": None,
                "attack": a.dict() if a else None,
                "defence": d.dict() if d else None,
                "evaluation": e.dict() if e else None,
            }))

    if format == "csv":
        if not rows:
            return StreamingResponse(iter(["turn_index,session_id,attack_prompt,defence_response,defence_was_blocked,defence_status_code,defence_blocked_by,eval_score,eval_success,eval_category,eval_feedback\n"]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=run_{run_id}.csv"})
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
        buf.seek(0)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=run_{run_id}.csv"})

    return {"run_id": run_id, "graph_type": graph_type, "turns": rows}
