# Engine Module

The core execution infrastructure of the adversarial testing system.

## Components

### `domain_models.py`
Rich wrapper classes that provide unified interfaces for complex data.

**Classes:**
- `AttackPayload` - Encapsulates generated attacks
- `DefencePayload` - Encapsulates target responses
- `EvalResult` - Encapsulates evaluation outputs

**Usage:**
```python
from engine.domain_models import create_simple_attack

attack = create_simple_attack("Test prompt", metadata={"type": "jailbreak"})
print(attack.to_string())  # For display
data = attack.to_dict()     # For database
```

### `state_schema.py`
TypedDict definitions for state flowing through LangGraph.

**Key Types:**
- `SystemState` - Complete state with three zones
- `TurnData` - Current loop's transient data
- `RoutingSignals` - Constants for flow control

**The Three Zones:**
1. `current_turn` - Transient (overwritten each loop)
2. `strategy_context` - Scratchpad (strategy's memory)
3. `routing_signal` - Routing (flow control)

### `graph_builder.py`
Constructs the universal LangGraph topology.

**Universal Topology:**
```
Init → Attack → Defence → Eval → Router → [Conditional]
                                            ├─> Attack (loop)
                                            └─> END
```

**Usage:**
```python
from engine.graph_builder import build_default_graph

graph = build_default_graph()  # Uses default nodes
```

### `workflow_engine.py`
The orchestrator that executes graphs with middleware injection.

**Key Features:**
- Async execution with `.astream()`
- Middleware injection at lifecycle hooks
- Parallel run management
- Graceful error handling

**Usage:**
```python
from engine.workflow_engine import WorkflowEngine

engine = WorkflowEngine(
    compiled_graph=graph,
    middlewares=[logging_middleware, db_middleware]
)

result = await engine.execute_run(
    payload={"intent": "test"},
    strategy=my_strategy
)
```

## Design Principles

1. **Domain Models Over Primitives** - Never pass raw strings/dicts
2. **Dependency Injection** - Zero global state
3. **Async-First** - All I/O operations are non-blocking
4. **Separation of Concerns** - Engine handles execution, not logic

## Extension Points

To use custom nodes:
```python
from engine.graph_builder import UniversalGraphBuilder

builder = UniversalGraphBuilder(
    init_node=my_init_node,
    attack_node=my_attack_node,
    defence_node=my_defence_node,
    eval_node=my_eval_node,
    router_node=my_router_node
)

graph = builder.compile()
```

## Common Patterns

**Creating initial state:**
```python
from engine.state_schema import create_initial_state

state = create_initial_state(
    run_id="run_123",
    payload={"intent": "test"},
    config={}
)
```

**Updating turn data:**
```python
from engine.state_schema import update_turn_data

updated = update_turn_data(
    current_turn,
    attack=attack_payload,
    node_name="attack"
)
```

## See Also

- [ARCHITECTURE.md](../ARCHITECTURE.md) - Complete system architecture
- [../strategies/README.md](../strategies/README.md) - Strategy development
- [../nodes/README.md](../nodes/README.md) - Node implementation
