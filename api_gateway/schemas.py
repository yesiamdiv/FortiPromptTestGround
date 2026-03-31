# api_gateway/schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class RunCreateRequest(BaseModel):
    """Request body for creating a new run"""
    name: str
    description: Optional[str] = Field(default="", description="Run description")
    components: List[str] = Field(default_factory=list, description="List of component types: 'attack', 'defense'")

class RunUpdateRequest(BaseModel):
    """Request body for updating a run"""
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class RunResponse(BaseModel):
    """Response model for run data - matches API spec exactly"""
    run_id: str
    name: str
    status: str
    description: Optional[str] = ""
    components: List[str]
    config: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    class Config:
        # Allow both naming conventions for compatibility during transition
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "runid": "run-abc-123",
                "name": "Initial Security Scan",
                "status": "idle",
                "description": "Testing RAG system defenses",
                "components": ["attack", "defense"],
                "config": {},
                "createdAt": "2026-03-25T10:00:00Z",
                "updatedAt": "2026-03-25T10:00:00Z"
            }
        }

class AttackConfig(BaseModel):
    """Attack configuration model"""
    model: str
    attackStrategy: str
    domain: str
    modelUrl: str
    iterations: int
    parameters: Dict[str, Any]

    class Config:
        json_schema_extra = {
            "example": {
                "model": "dolphine",
                "attackStrategy": "jailbreak",
                "domain": "harassment",
                "modelUrl": "https://api.example.com/target",
                "iterations": 100,
                "parameters": {
                    "temperature": 0.7,
                    "engine":'ollama'
                }
            }
        }

class DefenseConfig(BaseModel):
    """Defense configuration model"""
    filters: List[Dict[str, Any]]
    model: str

    class Config:
        json_schema_extra = {
            "example": {
                "filters": [
                    {"name": "regex_filter", "enabled": True},
                    {"name": "semantic_filter", "enabled": False}
                ],
                "model": "defender-model-v2"
            }
        }

class AttackPrompt(BaseModel):
    """Individual attack prompt"""
    promptId: str
    content: str
    status: str  # "generated", "sent", "failed", "breached", "blocked"
    timestamp: str

class AttackStats(BaseModel):
    """Attack statistics"""
    totalPrompts: int
    pendingAttacks: int
    attacksGenerated: int

class StartAttackRequest(BaseModel):
    """Request to start attack generation"""
    resumeFromLastSaved: bool = False

class StartAttackResponse(BaseModel):
    """Response from starting attack"""
    message: str
    runId: str
    status: str

class StopAttackResponse(BaseModel):
    """Response from stopping attack"""
    message: str
    runId: str
    status: str

class DefenseResponse(BaseModel):
    """Defense response to an attack"""
    promptId: str
    defenseResponse: str
    evaluation: str  # "blocked", "passed", "failed_filter"
    blockedAt: Optional[str] = None
    timestamp: str

class FilterPerformance(BaseModel):
    """Performance metrics for a single filter"""
    blocked: int
    falsePositives: int

class DefenseStats(BaseModel):
    """Defense statistics"""
    totalResponses: int
    blockedCount: int
    passedCount: int
    overallDefenseScore: int  # 0-100
    filterPerformance: Optional[Dict[str, FilterPerformance]] = None