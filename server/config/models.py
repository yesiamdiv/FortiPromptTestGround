
"""
Configuration Models for the Adversarial Testing Engine
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal


# Base model for node configuration
class BaseNodeConfig(BaseModel):
    node_type: str = Field(..., description="Type of the node (e.g., 'llm_attack', 'heuristic_defense')")
    # Other common parameters can be added here if needed

# Specific Node Configuration Models
class AttackNodeConfig(BaseNodeConfig):
    node_type: Literal["llm_attack", "heuristic_attack", "manual_attack", "default_attack"] = Field(..., description="Type of attack node")
    # Keep max_attempts_per_turn for attack node configuration
    # max_attempts_per_turn: Optional[int] = Field(None, description="Maximum attack attempts in a single turn/iteration")

class DefenseNodeConfig(BaseNodeConfig):
    node_type: Literal["llm_defense", "heuristic_defense", "default_defense"] = Field(..., description="Type of defense node")
    # Removed defense-specific templates and thresholds as requested

class EvaluationNodeConfig(BaseNodeConfig):
    node_type: Literal["llm_eval", "heuristic_eval", "default_eval"] = Field(..., description="Type of evaluation node")
    # Removed evaluation-specific criteria as requested

# Model for Strategy Configuration
class StrategyConfig(BaseModel):
    strategy_name: str = Field(..., description="Name of the strategy to use (e.g., 'default', 'iterative_improvement')")
    strategy_params: Dict[str, Any] = Field(default_factory=dict, description="Parameters specific to the chosen strategy. This can include strategy-specific memory or state.")

# Main Graph Configuration Model
class GraphConfig(BaseModel):
    graph_type: Literal["manual", "automatic", "default"] = Field(..., description="Type of graph topology to build")
    
    # Configurations for each node type in the graph
    attack_node_config: AttackNodeConfig = Field(..., description="Configuration for the attack node")
    defense_node_config: DefenseNodeConfig = Field(default_factory=lambda: DefenseNodeConfig(node_type="default_defense"), description="Configuration for the defense node. Defaults to 'default_defense'.")
    evaluation_node_config: EvaluationNodeConfig = Field(default_factory=lambda: EvaluationNodeConfig(node_type="default_eval"), description="Configuration for the evaluation node. Defaults to 'default_eval'.")
    
    # Strategy configuration
    strategy_config: StrategyConfig = Field(..., description="Configuration for the chosen strategy")
    
    # General graph parameters
    # max_total_iterations: Optional[int] = Field(None, description="Maximum iterations for the entire run")
    
    class Config:
        json_schema_extra = {
            "example": {
                "graph_type": "automatic",
                "attack_node_config": {
                    "node_type": "llm_attack",
                    "max_attempts_per_turn": 3
                },
                "defense_node_config": {
                    "node_type": "heuristic_defense"
                },
                "evaluation_node_config": {
                    "node_type": "llm_eval"
                },
                "strategy_config": {
                    "strategy_name": "iterative_improvement",
                    "strategy_params": {"learning_rate": 0.01, "temperature": 0.7}
                },
                "max_total_iterations": 100
            }
        }
