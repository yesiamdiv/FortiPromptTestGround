"""
Updated Database Models - Separate Collections

Attacks, defences, and evaluations are stored in separate collections
for easier querying and better data organization.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime


# ============================================================================
# Individual Data Models
# ============================================================================

class AttackData(BaseModel):
    """Single attack in a run"""
    run_id: str = Field(..., description="Associated run ID")
    index: int = Field(..., description="Attack index/iteration number")
    turn_id: str = Field(..., description="Turn identifier")
    prompt: str = Field(..., description="Attack prompt text")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    timestamp: str = Field(..., description="ISO timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run_abc123",
                "index": 1,
                "turn_id": "turn_1",
                "prompt": "Ignore previous instructions...",
                "metadata": {"strategy": "iterative", "llm_model": "llama3"},
                "timestamp": "2024-01-01T12:00:00"
            }
        }


class DefenceData(BaseModel):
    """Single defence response in a run"""
    run_id: str = Field(..., description="Associated run ID")
    index: int = Field(..., description="Defence index/iteration number")
    turn_id: str = Field(..., description="Turn identifier")
    response: str = Field(..., description="Defence response text")
    status_code: int = Field(default=200, description="HTTP status code if applicable")
    was_blocked: bool = Field(..., description="Whether request was blocked")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    timestamp: str = Field(..., description="ISO timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run_abc123",
                "index": 1,
                "turn_id": "turn_1",
                "response": "I cannot help with that request...",
                "status_code": 403,
                "was_blocked": True,
                "metadata": {"latency_ms": 150},
                "timestamp": "2024-01-01T12:00:01"
            }
        }


class EvaluationData(BaseModel):
    """Single evaluation in a run"""
    run_id: str = Field(..., description="Associated run ID")
    index: int = Field(..., description="Evaluation index/iteration number")
    turn_id: str = Field(..., description="Turn identifier")
    score: float = Field(..., ge=0.0, le=1.0, description="Evaluation score (0-1)")
    success: bool = Field(..., description="Whether attack was successful")
    category: str = Field(..., description="Classification category")
    feedback: Optional[str] = Field(None, description="Evaluation reasoning/feedback")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    timestamp: str = Field(..., description="ISO timestamp")
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run_abc123",
                "index": 1,
                "turn_id": "turn_1",
                "score": 0.75,
                "success": True,
                "category": "jailbreak_successful",
                "feedback": "System provided harmful information",
                "metadata": {"evaluator": "gpt-4"},
                "timestamp": "2024-01-01T12:00:02"
            }
        }


# ============================================================================
# Configuration Models
# ============================================================================

class RunConfig(BaseModel):
    """Configuration for a run"""
    global_config: Dict[str, Any] = Field(default_factory=dict)
    attack_config: Dict[str, Any] = Field(default_factory=dict)
    defence_config: Dict[str, Any] = Field(default_factory=dict)
    evaluation_config: Dict[str, Any] = Field(default_factory=dict)


# ============================================================================
# Run Model (Updated)
# ============================================================================

class RunModel(BaseModel):
    """
    Run model with references to separate collections.
    
    Attacks, defences, and evaluations are stored in separate collections
    and linked by run_id.
    """
    
    run_id: str = Field(..., description="Unique run identifier")
    name: str = Field(..., description="Human-readable run name")
    status: str = Field(..., description="Run status: running, completed, failed, stopped")
    description: str = Field(default="", description="Run description")
    
    # Strategy info
    strategy: str = Field(..., description="Strategy name")
    components: List[str] = Field(default_factory=list, description="Component names used")
    
    # Configuration
    config: RunConfig = Field(default_factory=RunConfig, description="Run configuration")
    
    # Timestamps
    created_at: str = Field(..., description="ISO timestamp when created")
    started_at: Optional[str] = Field(None, description="ISO timestamp when started")
    completed_at: Optional[str] = Field(None, description="ISO timestamp when completed")
    
    # Statistics (computed from separate collections)
    total_iterations: int = Field(default=0, description="Total attack iterations")
    successful_iterations: int = Field(default=0, description="Successful attack count")
    final_score: Optional[float] = Field(None, description="Final evaluation score")
    best_score: Optional[float] = Field(None, description="Best score achieved")
    
    # Metadata
    intent: str = Field(..., description="User's stated intent")
    target: Optional[str] = Field(None, description="Target system name")
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    
    # Error tracking
    error: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run_abc123",
                "name": "Jailbreak Test 1",
                "status": "completed",
                "description": "Testing jailbreak resistance",
                "strategy": "iterative_improvement",
                "components": ["ollama", "http_defence", "llm_eval"],
                "config": {"global_config": {}},
                "created_at": "2024-01-01T12:00:00",
                "started_at": "2024-01-01T12:00:01",
                "completed_at": "2024-01-01T12:05:00",
                "total_iterations": 5,
                "successful_iterations": 2,
                "final_score": 0.85,
                "best_score": 0.85,
                "intent": "Test jailbreak resistance",
                "target": "production-model"
            }
        }


# ============================================================================
# Response Models for API
# ============================================================================

class RunWithData(BaseModel):
    """Run model with embedded attack/defence/evaluation data"""
    run: RunModel
    attacks: List[AttackData] = Field(default_factory=list)
    defences: List[DefenceData] = Field(default_factory=list)
    evaluations: List[EvaluationData] = Field(default_factory=list)


class RunSummary(BaseModel):
    """Lightweight run summary for list views"""
    run_id: str
    name: str
    status: str
    strategy: str
    created_at: str
    total_iterations: int
    best_score: Optional[float]
    intent: str


# ============================================================================
# Statistics Models
# ============================================================================

class RunStatistics(BaseModel):
    """Aggregated statistics for a run"""
    run_id: str
    total_attacks: int
    total_defences: int
    total_evaluations: int
    
    success_rate: float
    average_score: float
    best_score: float
    worst_score: float
    
    blocked_count: int
    blocked_rate: float
    
    categories: Dict[str, int] = Field(default_factory=dict)


class GlobalStatistics(BaseModel):
    """Global statistics across all runs"""
    total_runs: int
    completed_runs: int
    running_runs: int
    failed_runs: int
    
    total_attacks: int
    total_successful: int
    global_success_rate: float
    
    by_strategy: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    by_category: Dict[str, int] = Field(default_factory=dict)