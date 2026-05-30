"""
class ConfigurableGraphBuilder:
    \"\"\"
    Dynamically constructs a state graph topology based on a provided configuration.

    This builder is responsible for mapping configuration schemas to actual executable 
    nodes, resolving strategies from the registry, and wiring the conditional routing 
    edges. It acts as the bridge between static configuration and executable LangGraph components.

    Attributes:
        graph_config (GraphConfig): The configuration schema defining the nodes and strategy.
        node_registry (NodeRegistry): The registry used to instantiate node classes.
        strategy_registry (StrategyRegistry): The registry used to instantiate the active strategy.
        graph (StateGraph): The underlying LangGraph state machine being constructed.
        strategy (AttackStrategy): The active strategy instance driving the generation and routing.
    \"\"\"
"""

from typing import Dict, Any, Callable, List, Optional
from langgraph.graph import StateGraph, END
from langgraph.graph.state import CompiledStateGraph

from engine.state import SystemState, RoutingSignals, TurnData, create_initial_state, update_turn_data
from engine.registry import get_node_registry, get_strategy_registry, get_provider_registry
from core.config import GraphConfig, AttackNodeConfig, DefenseNodeConfig, EvaluationNodeConfig, StrategyConfig, BaseNodeConfig
from nodes.base import BaseAdversarialNode
from nodes.batch_wrapper_node import BatchWrapperNode
from core.logging import debug, tracer, step, checkpoint, warn, err
from core.constants import NodeName
from strategies.base import AttackStrategy


class ConfigurableGraphBuilder:
    """Constructs the LangGraph topology dynamically based on GraphConfig."""
    
    def __init__(self, graph_config: GraphConfig):
        tracer("ConfigurableGraphBuilder.__init__", graph_type=graph_config.graph_type)
        self.graph_config = graph_config
        self.node_registry = get_node_registry()
        self.strategy_registry = get_strategy_registry()
        
        self.strategy:AttackStrategy = self.strategy_registry.get(
            name=graph_config.strategy_config.strategy_name,
            config=graph_config.strategy_config.strategy_params
        )
        step("Strategy instance retrieved", strategy_name=graph_config.strategy_config.strategy_name)

        self.graph = StateGraph(SystemState)
        self._build_graph_from_config()

    def _build_graph_from_config(self):
        """Builds the graph nodes and edges based on the provided GraphConfig."""
        tracer("_build_graph_from_config", graph_type=self.graph_config.graph_type)
        
        try:
            # Instantiate Attack Node
            attack_config = self.graph_config.attack_node_config.dict()
            attack_config["strategy"] = self.strategy
            # Pass node_params up to self.config directly
            if "node_params" in attack_config:
                attack_config.update({"node_params": attack_config.pop("node_params")})
                
            attack_node_instance = self.node_registry.get(
                self.graph_config.attack_node_config.node_type,
                config=attack_config 
            )
            
            # [FIXED]: Extract runtime_config and pass it down
            async def attack_wrapper(state: SystemState, config: Dict[str, Any] = None) -> Dict[str, Any]:
                runtime_cfg = config.get("configurable", {}) if config else {}
                return await attack_node_instance.execute(state, runtime_cfg)
            self.graph.add_node("attack", attack_wrapper)
            step("Added attack node", node_type=self.graph_config.attack_node_config.node_type)
            
            # Instantiate Defense Node
            defense_config = self.graph_config.defense_node_config.dict()
            if "node_params" in defense_config:
                defense_config.update({"node_params": defense_config.pop("node_params")})
                
            defense_node_instance = self.node_registry.get(
                self.graph_config.defense_node_config.node_type,
                config=defense_config
            )
            
            # For batch graph_type: wrap the single-item node in BatchWrapperNode
            if self.graph_config.graph_type == "batch":
                defense_node_instance = BatchWrapperNode(config={
                    "single_node": defense_node_instance,
                    "role": "defence",
                })
                step("Wrapped defence node in BatchWrapperNode")
            
            # [FIXED]: Capture node instance in default arg to avoid late-binding closure bug
            async def defense_wrapper(state: SystemState, config: Dict[str, Any] = None, _node=defense_node_instance) -> Dict[str, Any]:
                runtime_cfg = config.get("configurable", {}) if config else {}
                return await _node.execute(state, runtime_cfg)
            self.graph.add_node("defence", defense_wrapper)
            step("Added defence node", node_type=self.graph_config.defense_node_config.node_type)

            # Instantiate Evaluation Node
            eval_config = self.graph_config.evaluation_node_config.dict()
            if "node_params" in eval_config:
                eval_config.update({"node_params": eval_config.pop("node_params")})
                
            eval_node_instance = self.node_registry.get(
                self.graph_config.evaluation_node_config.node_type,
                config=eval_config
            )
            
            # For batch graph_type: wrap the single-item node in BatchWrapperNode
            if self.graph_config.graph_type == "batch":
                eval_node_instance = BatchWrapperNode(config={
                    "single_node": eval_node_instance,
                    "role": "eval",
                })
                step("Wrapped eval node in BatchWrapperNode")
            
            # [FIXED]: Capture node instance in default arg to avoid late-binding closure bug
            async def eval_wrapper(state: SystemState, config: Dict[str, Any] = None, _node=eval_node_instance) -> Dict[str, Any]:
                runtime_cfg = config.get("configurable", {}) if config else {}
                return await _node.execute(state, runtime_cfg)
            self.graph.add_node("eval", eval_wrapper)
            step("Added eval node", node_type=self.graph_config.evaluation_node_config.node_type)
            
            # Instantiate Router Node
            router_node_instance = self.node_registry.get(
                "router", 
                config={
                    "strategy": self.strategy, 
                    "strategy_config": self.graph_config.strategy_config,
                    "graph_type": self.graph_config.graph_type
                }
            )
            
            # [FIXED]: Extract runtime_config and pass it down
            async def router_wrapper(state: SystemState, config: Dict[str, Any] = None) -> Dict[str, Any]:
                runtime_cfg = config.get("configurable", {}) if config else {}
                return await router_node_instance.execute(state, runtime_cfg)
            self.graph.add_node("router", router_wrapper)
            step("Added router node")
            
        except ValueError as e:
            raise ValueError(f"Error instantiating graph nodes: {e}") from e

        self.graph.set_entry_point("init") 
        self.graph.add_node("init", self._initialization_node)

        self.graph.add_edge("init", "router")
        
        self.graph.add_conditional_edges(
            "router",
            self.router_routing_logic, 
            {
                RoutingSignals.ATTACK: RoutingSignals.ATTACK,
                RoutingSignals.CONTINUE: RoutingSignals.ATTACK, 
                RoutingSignals.END: END
            }
        )
        self.graph.add_edge("attack", "defence")
        self.graph.add_edge("defence", "eval")
        self.graph.add_edge("eval", "router")
        checkpoint("Graph edges configured")

    def _initialization_node(self, state: SystemState, config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Runs strategy initialization. Now correctly returns state deltas."""
        tracer("_initialization_node", run_id=state.get('run_id', 'unknown'))
        runtime_cfg = config.get("configurable", {}) if config else {}
        
        updates = {}
        
        # Ensure a TurnData object exists in the delta if it's missing
        if 'current_turn' not in state or state['current_turn'] is None:
            initial_state_temp = create_initial_state(state.get('run_id', 'unknown_run'), state.get('payload', {}), state.get('config', {}))
            updates['current_turn'] = initial_state_temp.get('current_turn')
            step("Created current_turn")
        
        if 'strategy_context' not in state or not state['strategy_context']:
            if not hasattr(self.strategy, 'initialize'):
                err("Strategy missing initialize method", strategy=type(self.strategy).__name__)
                raise AttributeError("Strategy object does not have an 'initialize' method.")
            
            # Get deltas from strategy
            init_updates = self.strategy.initialize(state, runtime_cfg)
            updates.update(init_updates)
            
            # Ensure strategy_context is fully formed in the updates
            strat_context = updates.get('strategy_context', {})
            if not strat_context:
                 strat_context = {
                    "strategy_params": self.graph_config.strategy_config.strategy_params,
                    "memory": {},
                    "strategy_name": self.graph_config.strategy_config.strategy_name
                }
            else:
                strat_context['strategy_name'] = self.graph_config.strategy_config.strategy_name
            
            updates['strategy_context'] = strat_context
            
        checkpoint("Strategy initialized", strategy_name=updates.get('strategy_context', {}).get('strategy_name'))

        # [FIXED]: Return only the delta dictionary
        return updates

    def router_routing_logic(self, state: SystemState) -> str:
        """Routing logic for the unified router node."""
        tracer("router_routing_logic")
        
        # Look inside the state dictionary for the routing signal left by the RouterNode
        signal = state.get("routing_signal")
        
        if not signal:
             err("No routing signal found in state")
             return RoutingSignals.END
             
        debug("Router Signal extracted", signal=signal)
        return signal
            
    def compile(self, recursion_limit: int = 0) -> CompiledStateGraph:
        """
        Compiles the graph.

        Args:
            recursion_limit: LangGraph step ceiling. Each run iteration uses
                             ~6 steps (router + attack + defence + eval + router).
                             Pass 0 (default) to auto-calculate from the
                             strategy's max_iterations, or pass an explicit value.
        """
        checkpoint("Compiling graph")
        compiled = self.graph.compile()

        # Calculate a safe recursion limit so LangGraph never chokes on long runs.
        # Formula: (max_iterations * 6 steps) + 20 buffer.
        # 6 = init + router + attack + defence + eval + router (per iteration).
        if recursion_limit <= 0:
            max_iters = (
                self.graph_config.strategy_config.strategy_params.get("max_iterations", 10)
                if self.graph_config.strategy_config.strategy_params
                else 10
            )
            recursion_limit = max(max_iters * 6 + 20, 50)

        self._recursion_limit = recursion_limit
        step("Graph compiled successfully", recursion_limit=recursion_limit)
        return compiled

def build_default_graph()->CompiledStateGraph:
    """Builds and compiles the default graph"""
    tracer("build_default_graph")
    default_config = GraphConfig(
        graph_type="automatic",
        attack_node_config=AttackNodeConfig(node_type="strategy_attack"),
        defense_node_config=DefenseNodeConfig(node_type="default_defense"),
        evaluation_node_config=EvaluationNodeConfig(node_type="default_eval"),
        strategy_config=StrategyConfig(strategy_name="default", strategy_params={})
    )
    debug("Building default graph", graph_type=default_config.graph_type)
    builder = ConfigurableGraphBuilder(default_config)
    return builder.compile()  # uses auto-calculated recursion_limit