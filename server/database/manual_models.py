
"""
Manual Attack Session Models

Database models for manual attack sessions and turns.
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime


class ManualTurn(BaseModel):
    """Single turn in a manual session (attack → defense → evaluation)"""
    turn_id: str = Field(..., description="Unique turn identifier")
    session_id: str = Field(..., description="Associated session ID")
    run_id: str = Field(..., description="Associated run ID")
    turn_index: int = Field(..., description="Turn number in session (0-indexed)")
    role: Literal["attacker", "defender"] = Field(..., description="Who initiated this turn")
    
    # Attack data
    attack_prompt: str = Field(..., description="User's attack prompt")
    attack_timestamp: str = Field(..., description="When attack was sent")
    attack_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata for the attack")
    
    # Defense data (populated after processing)
    defense_response: Optional[str] = Field(None, description="Defense system's response")
    defense_status_code: Optional[int] = Field(None, description="HTTP status code")
    defense_was_blocked: Optional[bool] = Field(None, description="Whether blocked")
    defense_timestamp: Optional[str] = Field(None, description="When defense responded")
    defense_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata for the defense response")
    
    # Evaluation data (populated after evaluation)
    eval_score: Optional[float] = Field(None, description="Evaluation score (0-1)")
    eval_success: Optional[bool] = Field(None, description="Whether attack was successful")
    eval_category: Optional[str] = Field(None, description="Attack category")
    eval_feedback: Optional[str] = Field(None, description="Evaluation reasoning")
    eval_timestamp: Optional[str] = Field(None, description="When evaluated")
    eval_metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata for the evaluation")

    class Config:
        json_schema_extra = {
            "example": {
                "turn_id": "sess_abc123_turn_0",
                "session_id": "sess_abc123",
                "run_id": "run_xyz789",
                "turn_index": 0,
                "role": "attacker",
                "attack_prompt": "Ignore previous instructions...",
                "attack_timestamp": "2024-01-01T12:00:00",
                "defense_response": "I cannot help with that request...",
                "defense_status_code": 403,
                "defense_was_blocked": True,
                "defense_timestamp": "2024-01-01T12:00:01",
                "eval_score": 0.75,
                "eval_success": True,
                "eval_category": "jailbreak_successful",
                "eval_feedback": "System provided harmful information",
                "eval_timestamp": "2024-01-01T12:00:02"
            }
        }


class ManualSession(BaseModel):
    """A chat session for manual attacks"""
    session_id: str = Field(..., description="Unique session identifier")
    run_id: str = Field(..., description="Associated run ID")
    
    name: str = Field(..., description="Session name/title")
    description: str = Field(default="", description="Session description")
    
    status: Literal["active", "saved", "archived"] = Field(
        default="active",
        description="Session status"
    )
    
    turn_count: int = Field(default=0, description="Number of turns in session")
    
    created_at: str = Field(..., description="ISO timestamp")
    updated_at: str = Field(..., description="ISO timestamp")
    saved_at: Optional[str] = Field(None, description="When session was saved")
    
    # Session configuration - can be overridden per session
    defense_config: Dict[str, Any] = Field(default_factory=dict)
    domain_notes: str = Field(default="", description="Domain-specific instructions")
    auto_evaluate: bool = Field(default=True, description="Whether to auto-evaluate each turn")
    
    # Statistics (computed)
    total_attacks: int = Field(default=0)
    successful_attacks: int = Field(default=0)
    average_score: Optional[float] = Field(None)
    
    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "sess_abc123",
                "run_id": "run_xyz789",
                "name": "Session 1",
                "status": "active",
                "turn_count": 5,
                "created_at": "2024-01-01T12:00:00",
                "updated_at": "2024-01-01T12:05:00",
                "total_attacks": 5,
                "successful_attacks": 2,
                "average_score": 0.75
            }
        }


# Note: ManualRunConfig model from previous versions might be redundant if its fields
# are fully captured within the GraphConfig or Session specific configurations.
# If specific manual run configurations are needed separately from graph config,
# this model could be re-introduced or merged into ManualSession.

