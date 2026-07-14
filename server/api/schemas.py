"""
API Request and Response Schemas
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal
from core.config import GraphConfig
from server.database.models import RunModel, Session, Turn, AttackData, DefenceData, EvaluationData


# --- Run Management Schemas ---

class CreateRunRequest(BaseModel):
    name: str = Field(..., description="Human-readable name for the run.")
    description: Optional[str] = Field(None, description="Optional detailed description.")
    config: GraphConfig = Field(..., description="Configuration defining the graph topology and strategy.")
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Initial payload data for the run. Can contain runtime_config.")

class UpdateRunRequest(BaseModel):
    name: Optional[str] = Field(None, description="New human-readable name for the run.")
    description: Optional[str] = Field(None, description="New detailed description for the run.")
    strategy_params: Optional[Dict[str, Any]] = Field(None, description="Parameters to update for the run's strategy.")
    attack_node_params: Optional[Dict[str, Any]] = Field(None, description="Parameters to update for the attack node.")
    defense_node_params: Optional[Dict[str, Any]] = Field(None, description="Parameters to update for the defense node.")
    evaluation_node_params: Optional[Dict[str, Any]] = Field(None, description="Parameters to update for the evaluation node.")

class RunResponse(BaseModel):
    run_id: str
    status: Literal["idle", "running", "completed", "failed", "stopped"] = Field(..., description="Current status of the run.")
    message: Optional[str] = Field(None, description="Additional message about the run status.")

class RunDetailsResponse(RunModel):
    """Extends RunModel to include more runtime details if needed by API"""
    pass

class ListRunsResponse(BaseModel):
    runs: List[RunModel]

# --- Session & Turn Schemas ---

class CreateSessionRequest(BaseModel):
    # run_id comes from the URL path parameter, NOT the request body
    name: str = Field(default="Session", description="A human-readable name for the session.")
    description: Optional[str] = Field(None, description="Optional description for the session.")
    initial_payload: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Initial payload for the first turn (e.g., user's first prompt). Can contain runtime_config.")

class SubmitTurnRequest(BaseModel):
    prompt: str = Field(..., description="The user's input/prompt for this turn.")
    runtime_config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Runtime overrides for this specific turn.")

class TurnDetailResponse(Turn):
    """Extends Turn to include actual attack/defence/eval data for API response"""
    attack_data: Optional[AttackData] = Field(None)
    defence_data: Optional[DefenceData] = Field(None)
    evaluation_data: Optional[EvaluationData] = Field(None)

class SessionHistoryResponse(BaseModel):
    session: Session
    turns: List[TurnDetailResponse]

class SubmitTurnResponse(BaseModel):
    run_id: str
    session_id: str
    turn_id: str
    status: str

# --- Strategy Schemas ---

class StrategySchemaResponse(BaseModel):
    strategy_name: str = Field(..., description="The name of the strategy.")
    schema_definition: Dict[str, Any] = Field(..., description="JSON schema defining the strategy's configurable parameters.")

class ListStrategiesResponse(BaseModel):
    strategies: List[StrategySchemaResponse]

# --- Provider Schemas ---

class ProviderInfoResponse(BaseModel):
    name: str = Field(..., description="Name of the LLM provider.")

class ListProvidersResponse(BaseModel):
    providers: List[ProviderInfoResponse]

# --- Node Schemas ---

class NodeSchemaResponse(BaseModel):
    node_type: str = Field(..., description="The type of the node (e.g., 'attack', 'defence', 'eval').")
    node_name: str = Field(..., description="The specific name of the node implementation (e.g., 'llm_attack_node', 'heuristic_defense').")
    schema_definition: Dict[str, Any] = Field(..., description="JSON schema defining the node's configurable parameters.")

class ListNodeSchemasResponse(BaseModel):
    nodes: List[NodeSchemaResponse]

# --- General API Responses ---

class MessageResponse(BaseModel):
    message: str
    detail: Optional[str] = None

class ErrorResponse(BaseModel):
    detail: str
