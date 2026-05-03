"""
Universal Graph Builder - Refactored for Dynamic Construction"""

from typing import Dict, Any, Callable, List, Optional
from langgraph.graph import StateGraph, END

# Import necessary components
from engine.state_schema import SystemState, RoutingSignals, TurnData, create_initial_state, update_turn_data
from engine.registry import get_node_registry, get_strategy_registry, get_provider_registry # Import ProviderRegistry
from server.config.models import GraphConfig, AttackNodeConfig, DefenseNodeConfig, EvaluationNodeConfig, StrategyConfig, BaseNodeConfig # Import Pydantic models
from nodes.base import BaseAdversarialNode # For type hinting


class ConfigurableGraphBuilder:
    """Constructs the LangGraph topology dynamically based on GraphConfig."""
    
    def __init__(self, graph_config: GraphConfig):
        self.graph_config = graph_config
        self.node_registry = get_node_registry()
        # Use get_strategy_registry() here
        self.strategy_registry = get_strategy_registry()
        
        # Retrieve strategy instance during initialization
        # Now correctly uses strategy_params to pass to the registry
        self.strategy = self.strategy_registry.get(
            name=graph_config.strategy_config.strategy_name,
            config=graph_config.strategy_config.strategy_params # Pass strategy params directly
        )

        self.graph = StateGraph(SystemState)
        self._build_graph_from_config()

    def _build_graph_from_config(self):
        """Builds the graph nodes and edges based on the provided GraphConfig."""
        
        try:
            # Instantiate Attack Node
            attack_config = self.graph_config.attack_node_config.dict()
            # Inject the strategy instance into the attack node's config
            attack_config["strategy"] = self.strategy 
            attack_node_instance = self.node_registry.get(
                self.graph_config.attack_node_config.node_type,
                config=attack_config 
            )
            self.graph.add_node("attack", attack_node_instance.execute)
            
            # Instantiate Defense Node
            defense_node_instance = self.node_registry.get(
                self.graph_config.defense_node_config.node_type,
                config=self.graph_config.defense_node_config.dict()
            )
            self.graph.add_node("defence", defense_node_instance.execute)

            # Instantiate Evaluation Node
            eval_node_instance = self.node_registry.get(
                self.graph_config.evaluation_node_config.node_type,
                config=self.graph_config.evaluation_node_config.dict()
            )
            self.graph.add_node("eval", eval_node_instance.execute)
            
            # Instantiate Router Node
            router_node_instance = self.node_registry.get(
                "router", 
                config={
                    "strategy": self.strategy, 
                    "strategy_config": self.graph_config.strategy_config,
                    "graph_type": self.graph_config.graph_type
                }
            )
            self.graph.add_node("router", router_node_instance.execute)
            
        except ValueError as e:
            raise ValueError(f"Error instantiating graph nodes: {e}") from e

        self.graph.set_entry_point("init") 
        self.graph.add_node("init", self._initialization_node)

        self.graph.add_edge("init", "router")
        
        self.graph.add_conditional_edges(
            "router",
            self.router_routing_logic, 
            {
                RoutingSignals.ATTACK: "attack",
                RoutingSignals.CONTINUE: "attack", 
                RoutingSignals.END: END
            }
        )
        self.graph.add_edge("attack", "defence")
        self.graph.add_edge("defence", "eval")
        self.graph.add_edge("eval", "router")

    def _initialization_node(self, state: SystemState) -> SystemState:
        print("Running Initialization Node...")
        
        if 'current_turn' not in state or state['current_turn'] is None:
            initial_state_temp = create_initial_state(state.get('run_id', 'unknown_run'), state.get('payload', {}), state.get('config', {}))
            state['current_turn'] = initial_state_temp.get('current_turn')
        
        if 'strategy_context' not in state or not state['strategy_context']:
            if not hasattr(self.strategy, 'initialize'):
                raise AttributeError("Strategy object does not have an 'initialize' method.")
            
            initialized_state = self.strategy.initialize(state)
            state.update(initialized_state)
            
            if 'strategy_context' not in state or not state['strategy_context']:
                 state['strategy_context'] = {
                    "strategy_params": self.graph_config.strategy_config.strategy_params,
                    "memory": {},
                    "strategy_name": self.graph_config.strategy_config.strategy_name
                }
            else:
                state['strategy_context']['strategy_name'] = self.graph_config.strategy_config.strategy_name

        return state

    def router_routing_logic(self, state: SystemState) -> str:
        """Routing logic for the unified router node."""
        if not hasattr(self.strategy, 'route'):
            raise AttributeError("Strategy object does not have a 'route' method.")
        
        signal = self.strategy.route(state)
        print(f"Router Signal: {signal}")
        return signal
            
    def compile(self):
        """Compiles the graph."""
        return self.graph.compile()

def build_default_graph():
    """Builds and compiles the default graph (no config needed, uses hardcoded defaults)"""
    default_config = GraphConfig(
        graph_type="automatic",
        attack_node_config=AttackNodeConfig(node_type="attack"),
        defense_node_config=DefenseNodeConfig(node_type="defence"),
        evaluation_node_config=EvaluationNodeConfig(node_type="eval"),
        strategy_config=StrategyConfig(strategy_name="default", strategy_params={})
    )
    print(f"Building default graph with config type: {default_config.graph_type}")
    builder = ConfigurableGraphBuilder(default_config)
    return builder.compile()
