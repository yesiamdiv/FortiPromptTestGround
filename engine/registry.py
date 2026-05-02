
"""
Registry for Nodes and Strategies
"""

from typing import Dict, Any, Callable, Type

# Import base classes and specific node/strategy implementations
from nodes.base import BaseAdversarialNode, StrategyProxyNode
from nodes.default_nodes import create_default_nodes # Factory for default nodes
from nodes.strategy_attack_node import StrategyDrivenAttackNode
from nodes.manual_attack_node import ManualAttackNode
from nodes.ensemble_defence_node import EnsembleDefenceNode
from nodes.server_eval_node import ServerEvalNode
from nodes.llm_eval_node import LLMEvalNode
from nodes.strategy_router_node import StrategyRouterNode

# Import strategy classes
from strategies.default_strategy import DefaultStrategy
from strategies.iterative_improvement_strategy import IterativeImprovementStrategy


# --- Node Registry ---

NodeFactory = Callable[..., Any]

class NodeRegistry:
    """Manages a registry of node factories."""
    def __init__(self):
        self._registry: Dict[str, NodeFactory] = {}

    def register(self, name: str, factory: NodeFactory):
        """Register a node factory."""
        if name in self._registry:
            raise ValueError(f"Node '{name}' already registered.")
        self._registry[name] = factory

    def get(self, name: str, **kwargs: Any) -> Any:
        """Get and instantiate a node using its factory."""
        factory = self._registry.get(name)
        if not factory:
            raise ValueError(f"Node factory '{name}' not found.")
        return factory(**kwargs)

_node_registry = NodeRegistry()

def get_node_registry() -> NodeRegistry:
    return _node_registry

# --- Strategy Registry ---

StrategyClass = Type[Any]

class StrategyRegistry:
    """Manages a registry of strategy classes."""
    def __init__(self):
        self._registry: Dict[str, StrategyClass] = {}

    def register(self, name: str, strategy_class: StrategyClass):
        """Register a strategy class."""
        if name in self._registry:
            raise ValueError(f"Strategy '{name}' already registered.")
        self._registry[name] = strategy_class

    def get(self, name: str, config: Dict[str, Any], **kwargs: Any) -> Any:
        """
        Get and instantiate a strategy class.
        
        Args:
            name: The name of the strategy to retrieve.
            config: The configuration dictionary for the strategy.
            **kwargs: Additional arguments to pass to the strategy constructor (e.g., LLM provider).
        """
        strategy_class = self._registry.get(name)
        if not strategy_class:
            raise ValueError(f"Strategy class '{name}' not found.")
        # Instantiate the strategy with its configuration
        return strategy_class(config=config, **kwargs)

_strategy_registry = StrategyRegistry()

def get_strategy_registry() -> StrategyRegistry:
    return _strategy_registry

# --- Registration Functions ---

def register_all_components():
    """Registers all nodes and strategies.
    This function should be called during application startup.
    """
    
    # Register Nodes
    # Default nodes from default_nodes.py are instantiated once here
    default_nodes_instance = create_default_nodes()
    _node_registry.register("default_attack", lambda **k: default_nodes_instance["attack"])
    _node_registry.register("default_defense", lambda **k: default_nodes_instance["defence"])
    _node_registry.register("default_eval", lambda **k: default_nodes_instance["eval"])
    
    # Specific Nodes
    _node_registry.register("strategy_router", lambda **k: StrategyRouterNode(**k))
    _node_registry.register("strategy_attack", lambda **k: StrategyDrivenAttackNode(**k))
    _node_registry.register("manual_attack", lambda **k: ManualAttackNode(**k))
    _node_registry.register("ensemble_defense", lambda **k: EnsembleDefenceNode(**k))
    _node_registry.register("server_eval", lambda **k: ServerEvalNode(**k))
    _node_registry.register("llm_eval", lambda **k: LLMEvalNode(**k))

    # Register Strategies
    _strategy_registry.register("default", DefaultStrategy)
    _strategy_registry.register("iterative_improvement", IterativeImprovementStrategy)

# It's recommended to call register_all_components() during application startup.
# For example, in server/main.py's lifespan context:
# await register_all_components()

