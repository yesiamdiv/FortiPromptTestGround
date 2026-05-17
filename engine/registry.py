"""
Registry for Nodes and Strategies
"""

from typing import Dict, Any, Callable, Type

# Import base classes and specific node/strategy implementations
from nodes.base import BaseAdversarialNode
from nodes.default_nodes import DefaultAttackNode, DefaultDefenceNode, DefaultEvalNode
from nodes.multilayer_defense_node import MultilayerDefenseNode
from nodes.strategy_attack_node import StrategyDrivenAttackNode
from nodes.ensemble_defence_node import EnsembleDefenceNode
from nodes.server_eval_node import ServerEvalNode
from nodes.llm_eval_node import LLMEvalNode
from nodes.router_node import RouterNode

# Import strategy classes
from strategies.default_strategy import DefaultStrategy
from strategies.iterative_improvement_strategy import IterativeImprovementStrategy
from strategies.manual_strategy import ManualStrategy # Import ManualStrategy
from strategies.redgen_strategy import RedGenStrategy
from strategies.batch_strategy import BatchStrategy

# Import provider registry and registration function
from engine.provider_registry import get_provider_registry, register_all_providers
from engine.debug_utils import debug, tracer, step, checkpoint, warn, err


# --- Node Registry ---

NodeFactory = Callable[..., Any]

class NodeRegistry:
    """Manages a registry of node factories."""
    def __init__(self):
        self._registry: Dict[str, NodeFactory] = {}

    def register(self, name: str, factory: NodeFactory):
        """Register a node factory."""
        if name in self._registry:
            warn(f"Node '{name}' already registered, overwriting")
            raise ValueError(f"Node '{name}' already registered.")
        self._registry[name] = factory
        debug("Node registered", name=name)

    def get(self, name: str, **kwargs: Any) -> BaseAdversarialNode:
        """Get and instantiate a node using its factory."""
        factory = self._registry.get(name)
        if not factory:
            err(f"Node factory '{name}' not found", available=list(self._registry.keys()))
            raise ValueError(f"Node factory '{name}' not found.")
        debug("Node instantiated", name=name)
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
            warn(f"Strategy '{name}' already registered, overwriting")
            raise ValueError(f"Strategy '{name}' already registered.")
        self._registry[name] = strategy_class
        debug("Strategy registered", name=name)

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
            err(f"Strategy class '{name}' not found", available=list(self._registry.keys()))
            raise ValueError(f"Strategy class '{name}' not found.")
        debug("Strategy instantiated", name=name)
        return strategy_class(config=config, **kwargs)

_strategy_registry = StrategyRegistry()

def get_strategy_registry() -> StrategyRegistry:
    return _strategy_registry

# --- Registration Functions ---

def register_all_components():
    """Registers all nodes and strategies.
    This function should be called during application startup.
    """
    tracer("register_all_components")
    
    # 1. Direct Registration (No lambda wrappers, no factory functions!)
    _node_registry.register("default_attack", StrategyDrivenAttackNode)
    _node_registry.register("default_defense", DefaultDefenceNode)
    _node_registry.register("default_eval", DefaultEvalNode)
    step("Registered default nodes", nodes=["default_attack", "default_defense", "default_eval"])
    
    # 2. Clean Custom Nodes
    _node_registry.register("router", RouterNode)
    # _node_registry.register("strategy_attack", StrategyDrivenAttackNode)
    _node_registry.register("ensemble_defense", EnsembleDefenceNode)
    _node_registry.register("server_eval", ServerEvalNode)
    _node_registry.register("llm_eval", LLMEvalNode)
    _node_registry.register("multilayer_defense", MultilayerDefenseNode)
    step("Registered custom nodes", nodes=["router", "strategy_attack", "ensemble_defense", "server_eval", "llm_eval", "multilayer_defense"])

    # 3. Strategies were already doing it perfectly!
    _strategy_registry.register("default", DefaultStrategy)
    _strategy_registry.register("iterative_improvement", IterativeImprovementStrategy)
    _strategy_registry.register("redgen_attack", RedGenStrategy)
    _strategy_registry.register("manual", ManualStrategy)
    _strategy_registry.register("batch", BatchStrategy)
    step("Registered strategies", strategies=["default", "iterative_improvement", "manual", "batch"])
    
    register_all_providers()
    checkpoint("All components registered")

# It's recommended to call register_all_components() during application startup.
# For example, in server/main.py's lifespan context:
# await register_all_components()
