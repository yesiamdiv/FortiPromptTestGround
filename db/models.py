from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from typing_extensions import TypedDict
from bson import ObjectId

# --- Application-level Data Models ---

class AttackData(BaseModel):
    index: int
    prompt: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class DefenseData(BaseModel):
    index: int
    response: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class EvaluationData(BaseModel):
    index: int
    score: float
    feedback: Optional[str] = None

class RunConfig(BaseModel):
    global_config: Dict[str, Any] = Field(default_factory=dict)
    attack_config: Dict[str, Any] = Field(default_factory=dict)
    defense_config: Dict[str, Any] = Field(default_factory=dict)
    evaluation_config: Dict[str, Any] = Field(default_factory=dict)

class Run(BaseModel):
    """
    Application-level run model.
    Uses snake_case internally but can serialize to camelCase for API.
    """
    run_id: str = Field(default_factory=lambda: str(ObjectId()), alias="runid")
    name: str
    status: str
    description: str = ""
    components: List[str] = Field(default_factory=list)  # ← FIXED: Changed from Dict
    config: RunConfig = Field(default_factory=RunConfig)
    attack_data: List[AttackData] = Field(default_factory=list)
    defense_data: List[DefenseData] = Field(default_factory=list)
    evaluation_data: List[EvaluationData] = Field(default_factory=list)

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True

# --- Database-level Model ---

class AttackDataInDB(BaseModel):
    run_id: str
    attack_prompts: List[AttackData]

class DefenceDataInDB(BaseModel):
    run_id: str
    defence_responses: List[DefenseData]

class EvaluationDataInDB(BaseModel):
    run_id: str
    evaluation_results: List[EvaluationData]

class RunInDB(BaseModel):
    """
    Database model for runs.
    Supports both snake_case (internal) and camelCase (API) via aliases.
    """
    run_id: str
    name: str
    status: str
    description: Optional[str] = ""
    components: List[str] = Field(default_factory=list)  
    config: RunConfig
    attack_store_ref: Optional[str] = None
    defense_store_ref: Optional[str] = None
    evaluation_store_ref: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        populate_by_name = True
        allow_population_by_field_name = True
        json_encoders = {
            datetime: lambda v: v.isoformat() + "Z"
        }

class ArenaState(TypedDict, total=False):
    """
    The payload that travels between every node in the graph.

    All fields are optional (total=False) so nodes can be written to
    return only the keys they actually update — LangGraph will merge
    the partial dict back into the full state automatically.
    """
    run_id: str
    goal: str
    strategy: str
    max_turns: int
    turn_count: int
    chat_history: list
    current_prompt: str
    current_response: str
    evaluation_result: str
    evaluation_reasoning: str
    strategy_metadata: dict
    final_outcome: str