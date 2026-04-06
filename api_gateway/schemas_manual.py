"""
api_gateway/schemas_manual.py
──────────────────────────────
Pydantic schemas for all Manual Attack API request/response payloads.
These are kept separate from the main schemas.py to avoid polluting it.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ─── Config schemas ───────────────────────────────────────────────────────────

class ManualDefenseConfigPayload(BaseModel):
    """PUT /api/runs/{runId}/manual/config  — defense config portion"""
    filter_mode: str = "none"          # "none" | "regex" | "semantic" | "llm_judge"
    model: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class ManualRunConfigPayload(BaseModel):
    """Full config PUT body"""
    defense_config: ManualDefenseConfigPayload = Field(default_factory=ManualDefenseConfigPayload)
    domain: Optional[str] = None
    notes: Optional[str] = None


# ─── Chat turn / session schemas ──────────────────────────────────────────────

class ChatTurnPayload(BaseModel):
    """A single chat message sent from the frontend."""
    role: str                          # "attacker" | "target" | "defense"
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatTurnResponse(BaseModel):
    """A single chat turn returned to the frontend."""
    turn_id: str
    role: str
    content: str
    timestamp: str                     # ISO-8601
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AddTurnRequest(BaseModel):
    """POST /api/runs/{runId}/manual/sessions/{sessionId}/turns"""
    role: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AddTurnResponse(BaseModel):
    turn_id: str
    session_id: str
    run_id: str


# ─── Session schemas ──────────────────────────────────────────────────────────

class CreateSessionRequest(BaseModel):
    """POST /api/runs/{runId}/manual/sessions"""
    label: Optional[str] = None


class SessionResponse(BaseModel):
    """Full session returned by API"""
    session_id: str
    run_id: str
    label: Optional[str] = None
    turns: List[ChatTurnResponse] = Field(default_factory=list)
    status: str
    evaluation_score: Optional[float] = None
    evaluation_label: Optional[str] = None
    evaluation_reasoning: Optional[str] = None
    defense_filter_used: Optional[str] = None
    created_at: str
    saved_at: Optional[str] = None
    evaluated_at: Optional[str] = None


class SaveSessionRequest(BaseModel):
    """POST /api/runs/{runId}/manual/sessions/{sessionId}/save
    Optional label override at save time."""
    label: Optional[str] = None


class SaveSessionResponse(BaseModel):
    session_id: str
    run_id: str
    status: str                        # "evaluated"
    evaluation_score: float
    evaluation_label: str
    evaluation_reasoning: str


# ─── Stats schema ─────────────────────────────────────────────────────────────

class ManualRunStats(BaseModel):
    total_sessions: int
    saved_sessions: int
    active_sessions: int
    breach_count: int
    blocked_count: int
    partial_count: int
    average_score: Optional[float] = None


# ─── Manual Run response ──────────────────────────────────────────────────────

class ManualRunResponse(BaseModel):
    run_id: str
    name: str
    description: Optional[str] = ""
    status: str
    config: ManualRunConfigPayload
    session_ids: List[str] = Field(default_factory=list)
    created_at: str
    updated_at: Optional[str] = None
