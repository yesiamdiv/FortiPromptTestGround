
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
    final_score: Optional[float] = Field(None, description="Score of the final iteration")
    best_score: Optional[float] = Field(None, description="Best score achieved across all iterations")
    
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
                "final_score": 0.85,
                "best_score": 0.85
            }
        }


# ============================================================================
# Manual Interaction Models (Consolidated & Normalized)
# ============================================================================

class ManualTurn(BaseModel):
    """Represents a single turn in a manual interaction session, referencing core data."""
    
    # Identifiers linking to core data and session
    session_id: str = Field(..., description="Unique identifier for the manual session")
    run_id: str = Field(..., description="Associated run ID (links to RunModel)")
    index: int = Field(..., description="Turn number within the session (0-indexed)") # Renamed from turn_index
    turn_id: str = Field(..., description="Unique identifier for this specific turn, linking to Attack/Defence/Evaluation data")

    # Reference IDs for core data models
    attack_data_id: Optional[str] = Field(None, description="Reference ID for AttackData")
    defence_data_id: Optional[str] = Field(None, description="Reference ID for DefenceData")
    evaluation_data_id: Optional[str] = Field(None, description="Reference ID for EvaluationData")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "sess_manual_xyz789",
                "run_id": "run_abc123",
                "index": 0,
                "turn_id": "turn_1",
                "attack_data_id": "attack_data_id_xyz", # Example reference ID
                "defence_data_id": "defence_data_id_abc", # Example reference ID
                "evaluation_data_id": "eval_data_id_def" # Example reference ID
            }
        }


class ManualSession(BaseModel):
    """Represents a manual interaction session, aggregating turn IDs and session metadata."""
    
    # Identifiers
    session_id: str = Field(..., description="Unique session identifier")
    run_id: str = Field(..., description="Associated run ID, linking this session to a specific run execution")
    
    # Session details
    name: str = Field(..., description="User-defined name or title for the session")
    description: Optional[str] = Field(default="", description="Optional description for the session")
    
    # Status and lifecycle
    status: Literal["active", "saved", "archived"] = Field(
        default="active",
        description="Current status of the session"
    )
    created_at: str = Field(..., description="ISO timestamp when the session was created")
    updated_at: str = Field(..., description="ISO timestamp when the session was last modified")
    saved_at: Optional[str] = Field(None, description="ISO timestamp when the session was explicitly saved")

    # List of turn IDs in this session, in order
    turn_ids: List[str] = Field(default_factory=list, description="Ordered list of turn IDs belonging to this session")

    # Aggregated statistics for the session (derived from referenced data)
    total_turns: int = Field(default=0, description="Total number of turns in the session")
    # Other statistics like total_attacks, successful_attacks, average_score would be computed dynamically from referenced data if needed.

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "sess_manual_xyz789",
                "run_id": "run_abc123",
                "name": "Manual Jailbreak Test",
                "description": "Testing manual jailbreak prompts",
                "status": "active",
                "created_at": "2024-01-01T11:55:00",
                "updated_at": "2024-01-01T12:05:00",
                "turn_ids": ["turn_1", "turn_2", "turn_3"],
                "total_turns": 3
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
    # Note: ManualTurn data is not directly embedded here to maintain normalization.
    # It should be fetched separately using session_id and run_id.


class RunSummary(BaseModel):
    """Lightweight run summary for list views"""
    run_id: str
    name: str
    status: str
    strategy: str
    created_at: str
    best_score: Optional[float]


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


# ============================================================================
# Validators (if any needed for consolidation)
# ============================================================================

# Example validator (can be added if complex cross-field validation is needed)
# @validator('field_name')
# def validate_field(cls, v):
#     # validation logic
#     return v


# ============================================================================
# Unified Session / Turn Models (Phase 2)
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
