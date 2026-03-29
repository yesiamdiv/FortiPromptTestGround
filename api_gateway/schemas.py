# api_gateway/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime # Import datetime for createdAt and updatedAt

class RunCreateRequest(BaseModel): # Renamed from Run
    name: str
    description: str = Field(default="", description="Run description") # Added default and description
    components: Dict[str, Any] = Field(default_factory=dict, description="Run components") # Changed to Dict

class RunResponse(BaseModel): # Renamed from RunInDB
    run_id: str
    name: str
    status: str
    config: Dict[str, Any] # Config will be a dict for API response for now
    created_at: datetime # Changed from createdAt
    updated_at: datetime # Changed from updatedAt

class AttackConfig(BaseModel):
    model: str
    attackStrategy: str
    domain: str
    modelUrl: str
    iterations: int
    parameters: Dict[str, Any]

class DefenseConfig(BaseModel):
    filters: List[Dict[str, Any]]  # Assuming filters is a list of dictionaries
    model: str

class AttackPrompt(BaseModel):
    promptId: str
    content: str
    status: str
    timestamp: str

class AttackStats(BaseModel):
    totalPrompts: int
    pendingAttacks: int
    attacksGenerated: int
    # Add other stats as needed

class DefenseResponse(BaseModel):
    promptId: str
    defenseResponse: str
    evaluation: str
    blockedAt: str
    timestamp: str

class DefenseStats(BaseModel):
    totalResponses: int
    blockedCount: int
    passedCount: int
    overallDefenseScore: int
    filterPerformance: Optional[Dict[str, Dict[str, int]]] = None # Optional as it might not always be present
