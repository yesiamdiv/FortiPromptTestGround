"""
Domain Models for Adversarial Testing Engine
"""

from typing import Any, Dict, List, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class AttackPayload:
    """Encapsulates a generated attack with multiple representation formats."""
    
    data: Union[str, List[Dict], Dict]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_string(self) -> str:
        if isinstance(self.data, str):
            return self.data
        elif isinstance(self.data, list):
            return "\n".join([f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" for msg in self.data])
        elif isinstance(self.data, dict):
            return json.dumps(self.data, indent=2)
        return str(self.data)
    
    def to_messages(self) -> List[Dict]:
        if isinstance(self.data, list):
            return self.data
        elif isinstance(self.data, str):
            return [{"role": "user", "content": self.data}]
        elif isinstance(self.data, dict):
            if "messages" in self.data:
                return self.data["messages"]
            return [{"role": "user", "content": json.dumps(self.data)}]
        return [{"role": "user", "content": str(self.data)}]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "data": self.data,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class DefencePayload:
    """Encapsulates the response from an external target system."""
    
    response_text: str
    status_code: int
    headers: Dict[str, str] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # Kept this because it contains actual logic/computation
    def was_blocked(self) -> bool:
        if self.status_code >= 400:
            return True
        blocking_patterns = ["blocked", "rejected", "denied", "forbidden", "policy"]
        return any(p in self.response_text.lower() for p in blocking_patterns)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "response_text": self.response_text,
            "status_code": self.status_code,
            "headers": self.headers,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "was_blocked": self.was_blocked()
        }


@dataclass
class EvalResult:
    """Encapsulates the output of an evaluator LLM."""
    
    score: float
    success: bool
    category: str
    reasoning: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score,
            "success": self.success,
            "category": self.category,
            "reasoning": self.reasoning,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }
    
    def to_summary(self) -> str:
        status = "✓ Success" if self.success else "✗ Failure"
        return f"{status} | Score: {self.score:.2f} | Category: {self.category}"


# Factory functions
def create_simple_attack(text: str, **metadata) -> AttackPayload:
    return AttackPayload(data=text, metadata=metadata)

def create_defence_response(text: str, status_code: int = 200, headers: Optional[Dict] = None, **metadata) -> DefencePayload:
    return DefencePayload(response_text=text, status_code=status_code, headers=headers or {}, metadata=metadata)

def create_eval_result(score: float, success: bool, category: str, reasoning: str, **metadata) -> EvalResult:
    return EvalResult(score=score, success=success, category=category, reasoning=reasoning, metadata=metadata)