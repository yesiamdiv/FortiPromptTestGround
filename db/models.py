from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from typing_extensions import TypedDict

# --- Application-level Data Models ---

class AttackData(BaseModel):
    index: int
    prompt: str
    response: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class DefenseData(BaseModel):
    index: int
    input_text: str
    response: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class EvaluationData(BaseModel):
    index: int
    score: float
    feedback: Optional[str] = None

class Progress(BaseModel):
    # Placeholder for progress tracking. Add fields as needed.
    # Example: current_turn: int = 0
    # Example: status: str = "not_started"
    pass

class RunConfig(BaseModel):
    global_config: Dict[str, Any] = Field(default_factory=dict)
    attack_config: Dict[str, Any] = Field(default_factory=dict)
    defense_config: Dict[str, Any] = Field(default_factory=dict)
    evaluation_config: Dict[str, Any] = Field(default_factory=dict)

class Run(BaseModel):
    name: str
    status: str
    progress: Progress = Field(default_factory=Progress)
    config: RunConfig = Field(default_factory=RunConfig)
    attack_data: List[AttackData] = Field(default_factory=list)
    defense_data: List[DefenseData] = Field(default_factory=list)
    evaluation_data: List[EvaluationData] = Field(default_factory=list)

# --- Database-level Model ---

class RunInDB(BaseModel):
    id: Optional[str] = Field(alias="_id") # Maps to MongoDB's _id
    name: str
    status: str
    progress: Progress
    config: RunConfig
    attack_store_ref: Optional[str] = None
    defense_store_ref: Optional[str] = None
    evaluation_store_ref: Optional[str] = None
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

# Note: The ArenaState model from previous discussion is now implicitly handled within Run.attack_data, Run.defense_data, and Run.evaluation_data.
# If a separate 'arena_states' collection is still desired for detailed turn-by-turn history, a dedicated model for it would be needed.
# For now, we are consolidating turn-level data within the Run model as per the provided document.
