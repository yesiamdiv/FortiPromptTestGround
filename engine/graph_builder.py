"""Universal Graph Builder"""

from typing import Dict, Any
from langgraph.graph import StateGraph, START, END
from engine.state_schema import SystemState, RoutingSignals


class UniversalGraphBuilder:
    """Constructs the universal LangGraph topology"""
    
    def __init__(self, init_node, attack_node, defence_node, eval_node, router_node):
        self.nodes = {
            "init": init_node,
            "attack": attack_node,
            "defence": defence_node,
            "eval": eval_node,
            "strategy_router": router_node
        }
        self.graph = StateGraph(SystemState)
        self._build_nodes()
        self._build_standard_edges()
        self._build_conditional_edges()
    
    def _build_nodes(self):
        for name, node in self.nodes.items():
            self.graph.add_node(name, node.execute)
    
    def _build_standard_edges(self):
        self.graph.add_edge(START, "init")
        self.graph.add_edge("init", "attack")
        self.graph.add_edge("attack", "defence")
        self.graph.add_edge("defence", "eval")
        self.graph.add_edge("eval", "strategy_router")
    
    def _build_conditional_edges(self):
        self.graph.add_conditional_edges(
            "strategy_router",
            self._routing_logic,
            {
                RoutingSignals.ATTACK: "attack",
                RoutingSignals.CONTINUE: "attack",
                RoutingSignals.END: END,
                "__end__": END
            }
        )
    
    def _routing_logic(self, state: Dict[str, Any]) -> str:
        signal = state.get("routing_signal", RoutingSignals.END)
        if signal in [RoutingSignals.ATTACK, RoutingSignals.CONTINUE]:
            return "attack"
        return "__end__"
    
    def compile(self):
        return self.graph.compile()


def build_default_graph():
    """Build and compile a default graph"""
    from nodes.default_nodes import create_default_nodes
    nodes = create_default_nodes()
    builder = UniversalGraphBuilder(
        init_node=nodes["init"],
        attack_node=nodes["attack"],
        defence_node=nodes["defence"],
        eval_node=nodes["eval"],
        router_node=nodes["router"]
    )
    return builder.compile()
