"""State Schema for Adversarial Testing Engine"""

from typing import Annotated, TypedDict, Optional, Dict, Any
from datetime import datetime
import copy
from engine.debug_utils import debug

# Import our strict Domain Models!
from engine.domain_models import AttackPayload, DefencePayload, EvalResult


def merge_turn_data(left: 'TurnData', right: 'TurnData') -> 'TurnData':
    """LangGraph reducer: safely merges new node outputs into the existing turn."""
    if not left: return right
    if not right: return left
    
    merged = copy.deepcopy(left)
    merged.update(right)
    # Always keep the most recent timestamp
    merged["timestamp"] = datetime.utcnow().isoformat()
    return merged

def merge_context(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph reducer: safely merges strategy memory."""
    if not left: return right
    if not right: return left
    
    merged = copy.deepcopy(left)
    merged.update(right)
    return merged

class TurnData(TypedDict, total=False):
    """Transient data for the current execution loop"""
    turn_id: str
    attack: Optional[AttackPayload]    # Replaced Any with AttackPayload
    defence: Optional[DefencePayload]  # Replaced Any with DefencePayload
    evaluation: Optional[EvalResult]   # Replaced Any with EvalResult
    timestamp: str
    node_name: Optional[str]


class SystemState(TypedDict, total=False):
    """Complete state flowing through LangGraph"""
    current_turn: Annotated[TurnData, merge_turn_data]
    strategy_context: Annotated[Dict[str, Any], merge_context]
    routing_signal: str
    run_id: str
    payload: Dict[str, Any]
    config: Dict[str, Any]
    start_time: str


class RoutingSignals:
    """Standard routing signal constants"""
    CONTINUE = "continue"
    ATTACK = "attack"
    END = "__end__"


def create_initial_state(run_id: str, payload: Dict[str, Any], config: Dict[str, Any]) -> SystemState:
    """Create a fresh SystemState for a new execution run"""
    debug("Creating initial state", run_id=run_id, payload_keys=list(payload.keys()))
    return SystemState(
        run_id=run_id,
        payload=copy.deepcopy(payload), # Deep copy to prevent mutation
        config=copy.deepcopy(config),   # Deep copy to prevent mutation
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
    """Create a fresh TurnData structure"""
    return TurnData(
        turn_id=turn_id,
        attack=None,
        defence=None,
        evaluation=None,
        timestamp=datetime.utcnow().isoformat(),
        node_name=node_name
    )


def update_turn_data(current: TurnData, **updates) -> TurnData:
    """Update specific fields in TurnData securely"""
    # DEEPCOPY FIX: Prevents mutating nested lists/dicts inside the state
    updated = copy.deepcopy(current)
    updated.update(updates)
    updated["timestamp"] = datetime.utcnow().isoformat()
    return updated