"""
db/models_manual.py
────────────────────
Database-level models for Manual Attack runs.
A ManualRun has its own separate document structure from automated runs.
Each chat exchange (one human message + one target response) is a ChatTurn.
A ChatSession groups multiple ChatTurns into one saved attack session.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from bson import ObjectId


# ─── Chat-level primitives ────────────────────────────────────────────────────

class ChatTurn(BaseModel):
    """A single exchange: one user message and one target (or defense) response."""
    turn_id: str = Field(default_factory=lambda: str(ObjectId()))
    role: str                          # "attacker" | "target" | "defense"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatSession(BaseModel):
    """
    One complete manual attack attempt.
    Multiple turns make up a session; the session is saved explicitly by the user.
    After saving, it moves to evaluation automatically.
    """
    session_id: str = Field(default_factory=lambda: str(ObjectId()))
    run_id: str
    label: Optional[str] = None        # user-friendly label e.g. "Attempt #1"
    turns: List[ChatTurn] = Field(default_factory=list)

    # Evaluation fields (populated after save)
    evaluation_score: Optional[float] = None          # 0.0 – 1.0
    evaluation_label: Optional[str] = None            # "breached" | "blocked" | "partial"
    evaluation_reasoning: Optional[str] = None
    defense_filter_used: Optional[str] = None         # which filter was active, or "none"

    status: str = "active"             # "active" | "saved" | "evaluated"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    saved_at: Optional[datetime] = None
    evaluated_at: Optional[datetime] = None


# ─── Manual Run Config ────────────────────────────────────────────────────────

class ManualDefenseConfig(BaseModel):
    """Configuration for the defense side of a manual run."""
    filter_mode: str = "none"          # "none" | "regex" | "semantic" | "llm_judge"
    model: Optional[str] = None        # model for llm_judge mode
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ManualRunConfig(BaseModel):
    """Top-level config stored inside a ManualRunInDB document."""
    defense_config: ManualDefenseConfig = Field(default_factory=ManualDefenseConfig)
    domain: Optional[str] = None       # optional tag for what the attacker targets
    notes: Optional[str] = None


# ─── DB document ─────────────────────────────────────────────────────────────

class ManualRunInDB(BaseModel):
    """
    Stored in the 'manual_runs' MongoDB collection.
    Parallel to RunInDB but scoped for manual testing.
    """
    run_id: str                        # same run_id as the parent Run document
    name: str
    description: Optional[str] = ""
    status: str = "initialized"        # "initialized" | "active" | "completed"
    config: ManualRunConfig = Field(default_factory=ManualRunConfig)
    sessions: List[str] = Field(default_factory=list)  # list of session_ids
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        json_encoders = {datetime: lambda v: v.isoformat() + "Z"}
