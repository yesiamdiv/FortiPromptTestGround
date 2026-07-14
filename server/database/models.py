
"""
Updated Database Models - Consolidated and Normalized
"""

from pydantic import BaseModel, Field, validator
from typing import Dict, Any, List, Optional, Literal
from datetime import datetime

from core.config import GraphConfig # Assuming GraphConfig is correctly defined elsewhere and importable

# ============================================================================
# Core Data Models (Preserved)
# ============================================================================

class AttackData(BaseModel):
    """Single attack in a run"""
    run_id: str = Field(..., description="Associated run ID")
    index: int = Field(..., description="Attack index/iteration number within the run")
    turn_id: str = Field(..., description="Unique identifier for the turn this attack belongs to")
    prompt: str = Field(..., description="Attack prompt text")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata, e.g., LLM model used, strategy parameters")
    timestamp: str = Field(..., description="ISO timestamp when the attack was recorded")
    
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
    index: int = Field(..., description="Defence index/iteration number within the run")
    turn_id: str = Field(..., description="Unique identifier for the turn this defence belongs to")
    response: str = Field(..., description="Defence system's response text")
    status_code: int = Field(default=200, description="HTTP status code if applicable (e.g., 200, 403)")
    was_blocked: bool = Field(..., description="Whether the defence mechanism blocked the request")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata, e.g., latency, blocking reason")
    timestamp: str = Field(..., description="ISO timestamp when the defence response was recorded")
    
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
    index: int = Field(..., description="Evaluation index/iteration number within the run")
    turn_id: str = Field(..., description="Unique identifier for the turn this evaluation belongs to")
    score: float = Field(..., ge=0.0, le=1.0, description="Evaluation score (0 to 1)")
    success: bool = Field(..., description="Whether the attack was deemed successful based on this evaluation")
    category: str = Field(..., description="Classification category of the evaluation result (e.g., jailbreak_successful, policy_violation)")
    feedback: Optional[str] = Field(None, description="Detailed reasoning or feedback for the evaluation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata, e.g., evaluator model used")
    timestamp: str = Field(..., description="ISO timestamp when the evaluation was recorded")
    
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
# Run Model (Core)
# ============================================================================

class RunModel(BaseModel):
    """
    Represents a complete execution run, including configuration, status, and aggregated statistics.
    It references individual data points (attacks, defences, evaluations) via their IDs and session IDs.
    """
    
    run_id: str = Field(..., description="Unique run identifier")
    name: str = Field(..., description="Human-readable run name")
    status: Literal["idle", "running", "completed", "failed", "stopped"] = Field(default="idle", description="Current status of the run")
    description: str = Field(default="", description="Detailed description of the run's purpose")
    
    
    # Graph and overall execution configuration
    graph_config: GraphConfig = Field(..., description="Defines the graph topology, node types, and strategy-specific configurations")
    
    # Timestamps for lifecycle tracking
    created_at: str = Field(..., description="ISO timestamp when the run was created")
    started_at: Optional[str] = Field(None, description="ISO timestamp when the run execution began")
    completed_at: Optional[str] = Field(None, description="ISO timestamp when the run execution finished")
    
    # Additional fields expected by the frontend
    updated_at: Optional[str] = Field(None, description="ISO timestamp when the run was last updated")
    components: List[str] = Field(default_factory=list, description="Derived list of component types from graph_config")

    # Scores written once at run completion — kept because they require knowing iteration
    # order (final) or a MAX aggregation (best) and are cheap to store.
    # total_iterations and successful_iterations are intentionally NOT stored here;
    # they are computed at query time from the evaluations collection via /stats.
    # Removed optional metadata fields: intent, target, user_id, session_id, tags
    
    class Config:
        json_schema_extra = {
            "example": {
                "run_id": "run_abc123",
                "name": "Jailbreak Test 1",
                "status": "completed",
                "description": "Testing jailbreak resistance",
                "strategy": "iterative_improvement",
                "components": ["ollama", "http_defence", "llm_eval"],
                "graph_config": {
                    "graph_type": "automatic",
                    "attack_node_config": {"node_type": "llm_attack", "max_attempts_per_turn": 3},
                    "defense_node_config": {"node_type": "heuristic_defense"},
                    "evaluation_node_config": {"node_type": "llm_eval"},
                    "strategy_config": {
                        "strategy_name": "iterative_improvement",
                        "strategy_params": {"learning_rate": 0.01, "temperature": 0.7}
                    },
                    "max_total_iterations": 100
                },
                "created_at": "2024-01-01T12:00:00",
                "started_at": "2024-01-01T12:00:01",
                "completed_at": "2024-01-01T12:05:00",
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


# ============================================================================
# Unified Session / Turn Models
# ============================================================================

class Session(BaseModel):
    """A conversation-level container. One session = one coherent attack conversation."""
    session_id: str = Field(..., description="Unique session identifier")
    run_id: str = Field(..., description="Associated run ID")
    name: str = Field(..., description="Human-readable session name")
    description: str = Field(default="", description="Optional description")
    run_type: Literal["automatic", "batch", "manual", "multiturn"] = Field(
        ..., description="Run type that created this session"
    )
    status: Literal["active", "completed", "failed"] = Field(
        default="active", description="Current session status"
    )
    created_at: str = Field(..., description="ISO timestamp when session was created")
    updated_at: str = Field(..., description="ISO timestamp when session was last updated")
    turn_ids: List[str] = Field(default_factory=list, description="Ordered list of turn IDs")
    total_turns: int = Field(default=0, description="Total number of turns in the session")
    successful_turns: int = Field(default=0, description="Number of turns with a successful eval")


class Turn(BaseModel):
    """A single attack-defence-evaluation cycle within a session."""
    turn_id: str = Field(..., description="Unique turn identifier")
    session_id: str = Field(..., description="Parent session ID")
    run_id: str = Field(..., description="Associated run ID")
    index: int = Field(..., description="Position of this turn within its session (0-indexed)")
    attack_data_id: Optional[str] = Field(None, description="Reference to AttackData document")
    defence_data_id: Optional[str] = Field(None, description="Reference to DefenceData document")
    evaluation_data_id: Optional[str] = Field(None, description="Reference to EvaluationData document")
    created_at: str = Field(..., description="ISO timestamp when turn was created")
    updated_at: str = Field(..., description="ISO timestamp when turn was last updated")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional turn metadata")
