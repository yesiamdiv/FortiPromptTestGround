"""State Schema for Adversarial Testing Engine"""

from typing import TypedDict, Optional, Dict, Any
from datetime import datetime
from engine.debug_utils import debug


class TurnData(TypedDict, total=False):
    """Transient data for the current execution loop"""
    turn_id: str
    attack: Optional[Any]  # AttackPayload
    defence: Optional[Any]  # DefencePayload  
    evaluation: Optional[Any]  # EvalResult
    timestamp: str
    node_name: Optional[str]


class SystemState(TypedDict, total=False):
    """Complete state flowing through LangGraph"""
    current_turn: TurnData
    strategy_context: Dict[str, Any]
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
        payload=payload,
        config=config,
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
    """Update specific fields in TurnData"""
    updated = current.copy()
    updated.update(updates)
    updated["timestamp"] = datetime.utcnow().isoformat()
    return updated
