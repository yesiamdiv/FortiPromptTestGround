"""
Database Models

Pydantic models for database documents.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime


class RunModel(BaseModel):
    """Model for adversarial run documents"""
    
    run_id: str = Field(..., description="Unique run identifier")
    status: str = Field(..., description="Run status: running, completed, failed")
    strategy: str = Field(..., description="Strategy name")
    started_at: str = Field(..., description="ISO timestamp when run started")
    completed_at: Optional[str] = Field(None, description="ISO timestamp when run completed")
    intent: str = Field(..., description="User's stated intent")
    target: Optional[str] = Field(None, description="Target system name")
    
    # Optional metadata
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    
    # Results summary
    total_attempts: int = Field(default=0)
    successful_attempts: int = Field(default=0)
    final_score: Optional[float] = None
    final_category: Optional[str] = None
    
    # Error tracking
    error: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run_abc123",
                "status": "completed",
                "strategy": "DefaultStrategy",
                "started_at": "2024-01-01T12:00:00",
                "completed_at": "2024-01-01T12:05:00",
                "intent": "Test jailbreak resistance",
                "target": "production-model",
                "total_attempts": 3,
                "successful_attempts": 1,
                "final_score": 0.75
            }
        }


class StepModel(BaseModel):
    """Model for execution step documents"""
    
    run_id: str = Field(..., description="Associated run ID")
    turn_id: str = Field(..., description="Turn identifier")
    node: str = Field(..., description="Node that produced this step")
    timestamp: str = Field(..., description="ISO timestamp")
    
    # Attack data (if present)
    attack: Optional[Dict[str, Any]] = None
    
    # Defence data (if present)
    defence: Optional[Dict[str, Any]] = None
    
    # Evaluation data (if present)
    evaluation: Optional[Dict[str, Any]] = None
    
    # Routing data (if present)
    routing_signal: Optional[str] = None
    strategy_context: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run_abc123",
                "turn_id": "turn_1",
                "node": "attack",
                "timestamp": "2024-01-01T12:01:00",
                "attack": {
                    "data": "Test attack prompt",
                    "metadata": {"strategy": "default"}
                }
            }
        }


class EvaluationModel(BaseModel):
    """Model for evaluation result documents"""
    
    run_id: str = Field(..., description="Associated run ID")
    turn_id: str = Field(..., description="Turn identifier")
    timestamp: str = Field(..., description="ISO timestamp")
    
    # Evaluation results
    score: float = Field(..., ge=0.0, le=1.0, description="Score from 0 to 1")
    success: bool = Field(..., description="Whether attack was successful")
    category: str = Field(..., description="Classification category")
    reasoning: str = Field(..., description="Evaluation reasoning")
    
    # Metadata
    evaluator_model: Optional[str] = Field(None, description="Model used for evaluation")
    strictness: Optional[float] = Field(None, description="Strictness setting")
    confidence: Optional[float] = Field(None, description="Confidence score")
    
    # Related data
    attack_text: Optional[str] = Field(None, description="Attack that was evaluated")
    defence_text: Optional[str] = Field(None, description="Defence response")
    was_blocked: Optional[bool] = Field(None, description="Whether defence blocked")
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run_abc123",
                "turn_id": "turn_1",
                "timestamp": "2024-01-01T12:01:30",
                "score": 0.75,
                "success": True,
                "category": "jailbreak_successful",
                "reasoning": "System provided harmful information",
                "evaluator_model": "gpt-4"
            }
        }


class AggregateStatsModel(BaseModel):
    """Model for aggregated statistics"""
    
    total_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    running_runs: int = 0
    
    total_attempts: int = 0
    successful_attempts: int = 0
    
    average_score: float = 0.0
    success_rate: float = 0.0
    
    by_strategy: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    by_category: Dict[str, int] = Field(default_factory=dict)
    
    # Time-based stats
    runs_last_hour: int = 0
    runs_last_day: int = 0
    runs_last_week: int = 0
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_runs": 100,
                "completed_runs": 95,
                "failed_runs": 3,
                "running_runs": 2,
                "total_attempts": 250,
                "successful_attempts": 75,
                "average_score": 0.65,
                "success_rate": 0.30
            }
        }
