
"""
Universal Graph Builder - Refactored for Dynamic Construction"""

from typing import Dict, Any, Callable, List, Optional
from langgraph.graph import StateGraph, END

# Import necessary components
from engine.state_schema import SystemState, RoutingSignals, TurnData, create_initial_state, update_turn_data
from engine.registry import get_node_registry, get_strategy_registry
from server.config.models import GraphConfig, AttackNodeConfig, DefenseNodeConfig, EvaluationNodeConfig, StrategyConfig, BaseNodeConfig # Import Pydantic models
from nodes.base import BaseAdversarialNode # For type hinting


class ConfigurableGraphBuilder:
    """Constructs the LangGraph topology dynamically based on GraphConfig."""
    
    def __init__(self, graph_config: GraphConfig):
        self.graph_config = graph_config
        self.node_registry = get_node_registry()
        self.strategy_registry = get_strategy_registry()
        
        # Retrieve strategy instance during initialization
        self.strategy = self.strategy_registry.get(
            name=graph_config.strategy_config.strategy_name,
            config=graph_config.strategy_config.strategy_params,
            # Assuming provider is available here or passed via config
            # provider=get_llm_provider() # Example if provider is needed
        )

        self.graph = StateGraph(SystemState)
        self._build_graph_from_config()

    def _build_graph_from_config(self):
        """Builds the graph nodes and edges based on the provided GraphConfig."""
        
        # --- Node Instantiation ---
        try:
            # Instantiate Attack Node
            attack_node_instance = self.node_registry.get(
                self.graph_config.attack_node_config.node_type,
                config=self.graph_config.attack_node_config.dict() # Pass node config
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
            # Simplify config passed to node: directly include strategy, strategy_config, graph_type
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

        # --- Edge Configuration ---
        self.graph.set_entry_point("init") 
        self.graph.add_node("init", self._initialization_node)

        # Automatic or default flow: init -> router -> [attack/continue] -> defence -> eval -> router
        self.graph.add_edge("init", "router")
        
        # Edges from router:
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
        """Initialization node: sets up initial state and calls strategy initialization."""
        print("Running Initialization Node...")
        
        # Ensure current_turn is initialized if not present
        if 'current_turn' not in state or state['current_turn'] is None:
            initial_state_temp = create_initial_state(state.get('run_id', 'unknown_run'), state.get('initial_payload', {}), state.get('config', {}))
            state['current_turn'] = initial_state_temp.get('current_turn')
        
        # Initialize strategy context if not already present, and call strategy's init
        if 'strategy_context' not in state or not state['strategy_context']:
            if not hasattr(self.strategy, 'initialize'):
                raise AttributeError("Strategy object does not have an 'initialize' method.")
            
            # Call strategy's initialize method, passing the current state
            initialized_state = self.strategy.initialize(state)
            
            # Update state with context and routing signal from initialization
            state.update(initialized_state)
            
            # Ensure strategy_context is properly set, if initialize modified it
            if 'strategy_context' not in state or not state['strategy_context']:
                 state['strategy_context'] = {
                    "strategy_params": self.graph_config.strategy_config.strategy_params,
                    "memory": {},
                    "strategy_name": self.graph_config.strategy_config.strategy_name
                }
            else:
                # If strategy.initialize returned context, use it and ensure strategy name is present
                state['strategy_context']['strategy_name'] = self.graph_config.strategy_config.strategy_name

        return state

    def router_routing_logic(self, state: SystemState) -> str:
        """Routing logic for the unified router node."""
        # The router node should use the strategy's route method to determine the next step
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
    # Hardcoded example configuration for the default graph
    # In a real scenario, this would come from a config file or DB
    default_config = GraphConfig(
        graph_type="automatic",
        attack_node_config=AttackNodeConfig(node_type="attack"), # Use generic node names
        defense_node_config=DefenseNodeConfig(node_type="defence"),
        evaluation_node_config=EvaluationNodeConfig(node_type="eval"),
        strategy_config=StrategyConfig(strategy_name="default", strategy_params={})
    )
    print(f"Building default graph with config type: {default_config.graph_type}")
    builder = ConfigurableGraphBuilder(default_config)
    return builder.compile()

