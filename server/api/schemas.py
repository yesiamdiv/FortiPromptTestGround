"""
API Schemas

Pydantic models for API requests and responses.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime


# ============================================================================
# Request Schemas
# ============================================================================

class CreateRunRequest(BaseModel):
    """Request to create a new adversarial run"""
    
    intent: str = Field(..., description="User's stated intent for the test")
    target: Optional[str] = Field(None, description="Target system name")
    strategy: str = Field(default="default", description="Strategy to use")
    strategy_config: Dict[str, Any] = Field(default_factory=dict, description="Strategy configuration")
    
    # Optional metadata
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "intent": "Test jailbreak resistance",
                "target": "production-model",
                "strategy": "default",
                "strategy_config": {"max_attempts": 3}
            }
        }


class StopRunRequest(BaseModel):
    """Request to stop a running adversarial test"""
    
    reason: Optional[str] = Field(None, description="Reason for stopping")
    
    class Config:
        json_schema_extra = {
            "example": {
                "reason": "User requested cancellation"
            }
        }


# ============================================================================
# Response Schemas
# ============================================================================

class RunResponse(BaseModel):
    """Response containing run information"""
    
    run_id: str
    status: str
    strategy: str
    started_at: str
    completed_at: Optional[str] = None
    intent: str
    target: Optional[str] = None
    
    total_attempts: int = 0
    successful_attempts: int = 0
    final_score: Optional[float] = None
    final_category: Optional[str] = None
    
    error: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run_abc123",
                "status": "completed",
                "strategy": "DefaultStrategy",
                "started_at": "2024-01-01T12:00:00",
                "completed_at": "2024-01-01T12:05:00",
                "intent": "Test jailbreak resistance",
                "total_attempts": 3,
                "final_score": 0.75
            }
        }


class StepResponse(BaseModel):
    """Response containing step information"""
    
    run_id: str
    turn_id: str
    node: str
    timestamp: str
    
    attack: Optional[Dict[str, Any]] = None
    defence: Optional[Dict[str, Any]] = None
    evaluation: Optional[Dict[str, Any]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run_abc123",
                "turn_id": "turn_1",
                "node": "attack",
                "timestamp": "2024-01-01T12:01:00",
                "attack": {
                    "data": "Test attack prompt",
                    "metadata": {}
                }
            }
        }


class CreateRunResponse(BaseModel):
    """Response after creating a run"""
    
    run_id: str
    status: str
    message: str
    websocket_url: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run_abc123",
                "status": "running",
                "message": "Run started successfully",
                "websocket_url": "ws://localhost:8000/ws/run_abc123"
            }
        }


class HealthResponse(BaseModel):
    """Health check response"""
    
    status: str = "healthy"
    timestamp: str
    version: str = "1.0.0"
    database_connected: bool
    active_runs: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "status": "healthy",
                "timestamp": "2024-01-01T12:00:00",
                "version": "1.0.0",
                "database_connected": True,
                "active_runs": 5
            }
        }


class StrategyInfo(BaseModel):
    """Information about an available strategy"""
    
    name: str
    description: str
    config_schema: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "default",
                "description": "Default testing strategy",
                "config_schema": {
                    "max_attempts": "int",
                    "attack_prefix": "str"
                }
            }
        }


class ListStrategiesResponse(BaseModel):
    """List of available strategies"""
    
    strategies: List[StrategyInfo]
    
    class Config:
        json_schema_extra = {
            "example": {
                "strategies": [
                    {
                        "name": "default",
                        "description": "Default testing strategy",
                        "config_schema": {}
                    }
                ]
            }
        }


class ErrorResponse(BaseModel):
    """Error response"""
    
    error: str
    details: Optional[Dict[str, Any]] = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    
    class Config:
        json_schema_extra = {
            "example": {
                "error": "Run not found",
                "details": {"run_id": "run_abc123"},
                "timestamp": "2024-01-01T12:00:00"
            }
        }
