"""
Shared string constants for node names and run statuses.

These values are used across middlewares, the graph builder, and run manager
to avoid scattered raw string literals that are hard to rename or audit.

RoutingSignals stays in engine/state.py because it is tightly coupled to
LangGraph's conditional edge API and the strategy routing contract.
"""


class NodeName:
    """Node name strings used as LangGraph node identifiers."""
    INIT    = "init"
    ROUTER  = "router"
    ATTACK  = "attack"
    DEFENCE = "defence"
    EVAL    = "eval"


class RunStatus:
    """Run lifecycle status strings persisted to the database."""
    IDLE      = "idle"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    STOPPED   = "stopped"
