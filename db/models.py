from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from typing_extensions import TypedDict
from bson import ObjectId

# --- Application-level Data Models ---

from typing import Optional, List, Dict, Any
from datetime import datetime
from typing_extensions import TypedDict
from bson import ObjectId

# --- Data Models ---

class AttackData(BaseModel):
    id: Optional[str] = Field(alias="_id") # MongoDB's _id
    index: int
    prompt: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class DefenseData(BaseModel):
    id: Optional[str] = Field(alias="_id") # MongoDB's _id
    index: int
    response: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class EvaluationData(BaseModel):
    id: Optional[str] = Field(alias="_id") # MongoDB's _id
    index: int
    score: float
    feedback: Optional[str] = None

class RunConfig(BaseModel):
    global_config: Dict[str, Any] = Field(default_factory=dict)
    attack_config: Dict[str, Any] = Field(default_factory=dict)
    defense_config: Dict[str, Any] = Field(default_factory=dict)
    evaluation_config: Dict[str, Any] = Field(default_factory=dict)

class Run(BaseModel):
    description: str = Field(default="", description="Run description")
    components: Dict[str, Any] = Field(default_factory=dict, description="Run components")
    run_id: str = Field(default_factory=lambda: str(ObjectId())) # Custom run ID
    name: str
    status: str
    config: RunConfig = Field(default_factory=RunConfig)
    attack_data: List[AttackData] = Field(default_factory=list)
    defense_data: List[DefenseData] = Field(default_factory=list)
    evaluation_data: List[EvaluationData] = Field(default_factory=list)

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
    run_id: str
    name: str
    status: str
    config: RunConfig
    attack_store_ref: Optional[str] = None # Reference to attack data collection/document
    defense_store_ref: Optional[str] = None # Reference to defense data collection/document
    evaluation_store_ref: Optional[str] = None # Reference to evaluation data collection/document
    created_at: datetime
    updated_at: Optional[datetime] = None

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