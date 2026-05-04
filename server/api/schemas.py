"""
API Request and Response Schemas
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal
from server.config.models import GraphConfig
from server.database.models_v2 import RunModel, ManualSession, ManualTurn, AttackData, DefenceData, EvaluationData


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

class RunResponse(BaseModel):
    run_id: str
    status: Literal["idle", "running", "completed", "failed", "stopped"] = Field(..., description="Current status of the run.")
    message: Optional[str] = Field(None, description="Additional message about the run status.")

class RunDetailsResponse(RunModel):
    """Extends RunModel to include more runtime details if needed by API"""
    pass

class ListRunsResponse(BaseModel):
    runs: List[RunModel]

# --- Manual Session & Turn Schemas ---

class CreateManualSessionRequest(BaseModel):
    run_id: str = Field(..., description="The ID of the parent run.")
    name: str = Field(..., description="A human-readable name for the manual session.")
    description: Optional[str] = Field(None, description="Optional description for the session.")
    initial_payload: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Initial payload for the first turn (e.g., user's first prompt). Can contain runtime_config.")

class ManualSessionResponse(ManualSession):
    pass

class SubmitManualTurnRequest(BaseModel):
    prompt: str = Field(..., description="The user's input/prompt for this manual turn.")
    runtime_config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Runtime overrides for this specific turn.")

class ManualTurnResponse(ManualTurn):
    """Extends ManualTurn to include actual attack/defence/eval data for API response"""
    attack_data: Optional[AttackData] = Field(None)
    defence_data: Optional[DefenceData] = Field(None)
    evaluation_data: Optional[EvaluationData] = Field(None)

class ManualTurnHistoryResponse(BaseModel):
    session: ManualSession
    turns: List[ManualTurnResponse] # Returns detailed turns

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
