
"""Universal Graph Builder - Refactored for Dynamic Construction"""

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
            
            # Instantiate Strategy Router Node
            # Strategy Router needs access to strategy registry, config, and potentially LLM provider
            # For now, we pass the strategy object directly which is obtained via registry.
            # The router node will get strategy instance from config.
            router_node_instance = self.node_registry.get(
                "strategy_router", # Assuming 'strategy_router' is registered
                config={
                    "strategy_config": self.graph_config.strategy_config, # Pass strategy config to router
                    "graph_type": self.graph_config.graph_type # Pass graph type for conditional routing
                }
            )
            self.graph.add_node("strategy_router", router_node_instance.execute)

        except ValueError as e:
            raise ValueError(f"Error instantiating graph nodes: {e}") from e

        # --- Edge Configuration ---
        # Standard edges and entry point
        self.graph.set_entry_point("init") 
        self.graph.add_node("init", self._initialization_node)

        # Determine the flow based on graph_type
        if self.graph_config.graph_type == "manual":
            # Manual flow: init -> strategy_router -> manual_attack -> wait_state_node -> defence -> eval -> strategy_router
            # We need a 'wait_state_node' or similar to handle the pause/resume logic.
            # For now, ManualAttackNode signals a wait state, and StrategyRouterNode maintains it.
            # The graph will need a way to transition OUT of this wait state upon external input.
            
            # Add nodes relevant to manual flow if not already added
            if "manual_attack" not in self.graph.nodes:
                # ManualAttackNode needs to be registered and added if not present
                manual_attack_node = self.node_registry.get(
                    "manual_attack",
                    config=self.graph_config.attack_node_config.dict()
                )
                self.graph.add_node("manual_attack", manual_attack_node.execute)
            
            # Let's add a conceptual 'wait_for_input' node. This node's execute method
            # would ideally block until an external signal is received.
            # For now, we'll simulate its effect through routing signals.
            # ManualAttackNode sets routing_signal to WAITING_FOR_MANUAL_INPUT.
            # StrategyRouterNode picks this up and maintains it.
            # The graph needs a path out of this wait state.
            
            # Edge: init -> strategy_router (initial decision)
            self.graph.add_edge("init", "strategy_router")
            
            # Edges from router:
            # If router signals ATTACK, go to manual_attack
            # If router signals CONTINUE, perhaps it means continue after manual input?
            # If router signals WAITING_FOR_MANUAL_INPUT, stay in a waiting state (handled by router itself)
            # If router signals END, go to END
            
            # The routing logic needs to be robust for manual flows.
            # Let's define the conditional edges from strategy_router for manual flow:
            self.graph.add_conditional_edges(
                "strategy_router",
                self.manual_routing_logic,
                {
                    RoutingSignals.ATTACK: "manual_attack",  # If strategy says attack, go to manual attack
                    "WAITING_FOR_MANUAL_INPUT": "strategy_router", # If manual node signaled wait, stay routing to router (which will maintain wait)
                    RoutingSignals.END: END
                }
            )
            # Edge from manual_attack to defence (after input is received and processed)
            # This transition needs to be managed - e.g., when input is provided, the state is updated,
            # and the router signals to proceed.
            # For now, let's assume manual_attack node somehow transitions state to allow proceeding.
            # A more robust solution would involve feedback loop or external trigger to change state.
            self.graph.add_edge("manual_attack", "defence") # Simplified: assumes manual attack completes and goes to defence
            self.graph.add_edge("defence", "eval")
            self.graph.add_edge("eval", "strategy_router") # After eval, strategy decides next step.

        else: # Automatic or default flow
            # init -> strategy_router -> attack -> defence -> eval -> strategy_router
            self.graph.add_edge("init", "strategy_router")
            
            # Edges from router:
            # If router signals ATTACK, go to attack node
            # If router signals CONTINUE, go to attack node again (for iterative strategies)
            # If router signals END, go to END
            self.graph.add_conditional_edges(
                "strategy_router",
                self.automatic_routing_logic,
                {
                    RoutingSignals.ATTACK: "attack",
                    RoutingSignals.CONTINUE: "attack", # Default to attack for continuous loops
                    RoutingSignals.END: END
                }
            )
            self.graph.add_edge("attack", "defence")
            self.graph.add_edge("defence", "eval")
            self.graph.add_edge("eval", "strategy_router")

        # Add edge from eval back to strategy_router for iterative strategies (handled by conditional edges above)

    def _initialization_node(self, state: SystemState) -> SystemState:
        """Conceptual initialization node: sets up initial state components."""
        print("Running Initialization Node...")
        
        # Ensure current_turn is initialized if not present
        if 'current_turn' not in state or state['current_turn'] is None:
            state['current_turn'] = create_turn_data(turn_id='init_turn', node_name='init')
        
        # Initialize strategy context if not already present
        if 'strategy_context' not in state or not state['strategy_context']:
            strategy_name = self.graph_config.strategy_config.strategy_name
            strategy_params = self.graph_config.strategy_config.strategy_params
            
            # Initialize context with strategy params and empty memory
            state['strategy_context'] = {
                "strategy_params": strategy_params,
                "memory": {{}}, # Placeholder for strategy-specific memory
                "strategy_name": strategy_name # Store strategy name for reference
            }
            
            # Potentially call strategy.setup() here if it needs to be done at graph init
            # However, it might be better handled by a dedicated 'init' node that calls strategy.setup
            # For now, we'll assume setup is handled by strategy.execute_generation on first call or by a dedicated init node.

        return state

    def automatic_routing_logic(self, state: SystemState) -> str:
        """Routing logic for automatic/default graph types."""
        signal = state.get('routing_signal', RoutingSignals.END)
        print(f"Automatic Router Signal: {signal}")

        if signal in [RoutingSignals.ATTACK, RoutingSignals.CONTINUE]:
            return "attack"
        elif signal == RoutingSignals.END:
            return END
        else:
            # Default to END if signal is unexpected
            return END
            
    def manual_routing_logic(self, state: SystemState) -> str:
        """Routing logic for manual attack graph type."""
        signal = state.get('routing_signal', RoutingSignals.END)
        print(f"Manual Router Signal: {signal}")

        if signal == "WAITING_FOR_MANUAL_INPUT":
            # If waiting, the router node itself stays in the loop, effectively pausing execution
            # until the state is updated externally to signal continuation.
            # For now, we loop back to strategy_router to re-evaluate the state.
            return "strategy_router"
        elif signal == RoutingSignals.ATTACK:
            # If the strategy (or a prior node) decides to proceed with an attack
            return "manual_attack"
        elif signal == RoutingSignals.END:
            return END
        else:
            # Default to END for any other unexpected signals
            return END

    def compile(self):
        """Compiles the graph."""
        return self.graph.compile()


def build_dynamic_graph(graph_config: GraphConfig) -> Any:
    """Builds and compiles a graph dynamically based on the provided GraphConfig."""
    print(f"Building graph with config: {graph_config.graph_type}")
    builder = ConfigurableGraphBuilder(graph_config)
    return builder.compile()

