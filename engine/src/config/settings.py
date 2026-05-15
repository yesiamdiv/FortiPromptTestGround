# Configuration classes for FortiPrompt runs

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AttackerSettings:
    """Settings for the attacker component."""
    model_name: str
    strategy: str
    max_turns: int
    # Add any other attacker-specific settings here
    strategy_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DefenderSettings:
    """Settings for the defender component."""
    model_name: str
    # Add any other defender-specific settings here
    filters: List[str] = field(default_factory=list)


@dataclass
class EvaluatorSettings:
    """Settings for the evaluator component."""
    model_name: str
    # Add any other evaluator-specific settings here
    evaluation_criteria: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunConfig:
    """Overall configuration for a single run."""
    run_id: str
    goal: str
    attacker_settings: AttackerSettings
    defender_settings: DefenderSettings
    evaluator_settings: EvaluatorSettings
