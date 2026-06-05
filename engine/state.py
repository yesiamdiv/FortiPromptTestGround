"""
Runtime state definitions for the LangGraph execution engine.

SystemState flows through every node and middleware. LangGraph calls the
Annotated reducers (merge_turn_data, merge_context) automatically when
multiple nodes write to the same key — this is why we use deepcopy rather
than mutating in place.
"""

from typing import Annotated, TypedDict, Optional, Dict, Any
from datetime import datetime
import copy
from core.logging import debug
from core.models import AttackPayload, DefencePayload, EvalResult


def merge_turn_data(left: 'TurnData', right: 'TurnData') -> 'TurnData':
    """LangGraph reducer: merges new node outputs into the existing turn."""
    if not left: return right
    if not right: return left
    merged = copy.deepcopy(left)
    merged.update(right)
    merged["timestamp"] = datetime.utcnow().isoformat()
    return merged


def merge_context(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph reducer: merges strategy memory across turns."""
    if not left: return right
    if not right: return left
    merged = copy.deepcopy(left)
    merged.update(right)
    return merged


class TurnData(TypedDict, total=False):
    """Transient data for a single attack/defence/eval cycle."""
    turn_id: str
    attack: Optional[AttackPayload]
    defence: Optional[DefencePayload]
    evaluation: Optional[EvalResult]
    timestamp: str
    node_name: Optional[str]


class SystemState(TypedDict, total=False):
    """Complete state flowing through LangGraph nodes and middlewares."""
    current_turn: Annotated[TurnData, merge_turn_data]
    strategy_context: Annotated[Dict[str, Any], merge_context]
    routing_signal: str
    run_id: str
    session_id: str        # set at run start; updated per-session for multi-turn
    turn_index: int        # current turn's position within the active session
    payload: Dict[str, Any]
    config: Dict[str, Any]
    start_time: str


class RoutingSignals:
    """
    Routing signal constants returned by strategy.route() and consumed by
    LangGraph conditional edges. END maps to LangGraph's built-in terminator.

    PROCEED and CONTINUE_CONVERSATION are used by the intermediate
    PostAttackRouter and PostDefenceRouter nodes added in Phase 2.
    """
    CONTINUE = "continue"              # kept for backward compat
    ATTACK = "attack"
    END = "__end__"
    PROCEED = "proceed"                # pass-through for intermediate routers
    CONTINUE_CONVERSATION = "continue_conversation"  # loop within session


def create_initial_state(
    run_id: str,
    payload: Dict[str, Any],
    config: Dict[str, Any],
    session_id: str = "",
) -> SystemState:
    """Create a fresh SystemState for a new execution run."""
    debug("Creating initial state", run_id=run_id, payload_keys=list(payload.keys()))
    return SystemState(
        run_id=run_id,
        session_id=session_id,
        turn_index=0,
        # Deep-copy prevents callers from mutating state through their original references
        payload=copy.deepcopy(payload),
        config=copy.deepcopy(config),
        start_time=datetime.utcnow().isoformat(),
        current_turn=TurnData(
            turn_id="init",
            attack=None,
            defence=None,
            evaluation=None,
            timestamp=datetime.utcnow().isoformat(),
            node_name="init"
        ),
        strategy_context={},
        routing_signal=RoutingSignals.CONTINUE
    )


def create_turn_data(turn_id: str, node_name: str) -> TurnData:
    """Create a blank TurnData for the start of a new cycle."""
    return TurnData(
        turn_id=turn_id,
        attack=None,
        defence=None,
        evaluation=None,
        timestamp=datetime.utcnow().isoformat(),
        node_name=node_name
    )


def update_turn_data(current: TurnData, **updates) -> TurnData:
    """Return a new TurnData with the given fields updated.

    Deep-copy prevents nested mutable objects (e.g. metadata dicts inside
    AttackPayload) from being shared between the old and new state snapshots.
    """
    updated = copy.deepcopy(current)
    updated.update(updates)
    updated["timestamp"] = datetime.utcnow().isoformat()
    return updated
