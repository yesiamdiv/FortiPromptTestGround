from pydantic import BaseModel
from typing import Optional, List, Dict, Any

class AttackRequest(BaseModel):
    run_id: str
    goal: str
    strategy: str
    max_turns: int

class Run(BaseModel):
    name: str
    status: str
    created_at: Optional[str] = None

class RunInDB(Run):
    run_id: str
    goal: str
    strategy: str
    max_turns: int
    turn_count: int
    chat_history: List[Dict[str, Any]]
    current_prompt: Optional[str] = None
    current_response: Optional[str] = None
    evaluation_result: str
    evaluation_reasoning: Optional[str] = None
    strategy_metadata: Dict[str, Any]
    final_outcome: Optional[str] = None
