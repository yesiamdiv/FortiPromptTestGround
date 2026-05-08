# ⚙️ Engine Module

The core execution infrastructure and orchestration layer of the Agentic LLM Adversarial Testbed.

The `engine` directory is the beating heart of the system. It is responsible for state management, dynamic graph compilation, component registration, and execution orchestration.

It acts as the strict, type-safe bridge between database configurations and the live LangGraph execution loop.

---

# 🏛️ Core Architectural Philosophy

The engine is built on three foundational principles:

1. **Strict Type Safety (Domain Models)**  
   Raw dictionaries and primitive values should never be passed between nodes. All core execution data is wrapped in structured domain models such as `AttackPayload`, `DefencePayload`, and `EvalResult`.

   This provides:
   - Predictable property access
   - Centralized formatting and serialization
   - Strong runtime consistency
   - Safer extensibility

2. **Immutable State (State Deltas)**  
   The LangGraph `SystemState` is treated as immutable.

   Nodes and strategies must never directly mutate nested state structures (for example, using `.append()` on lists stored in state). Instead, they return **state deltas** containing only updated keys, which are safely merged by the engine.

3. **Dynamic Composition (Registries)**  
   The engine is completely decoupled from concrete attack, defence, or evaluation implementations.

   Using registry-based lookup tables, the `GraphBuilder` dynamically composes execution graphs at runtime based on database configurations.

---

# 📂 Architecture Breakdown

## 1. Data Contracts

### `domain_models.py`

Rich wrapper classes that provide unified interfaces for complex execution data.

### Classes

- `AttackPayload` — Encapsulates generated attacks
- `DefencePayload` — Encapsulates target responses
- `EvalResult` — Encapsulates evaluation outputs

Every model includes a `metadata` dictionary for safely storing node-specific contextual data without breaking the schema.

### Usage

```python
from engine.domain_models import create_simple_attack

attack = create_simple_attack(
    "Test prompt",
    metadata={"type": "jailbreak"}
)

print(attack.to_string())   # For display
data = attack.to_dict()     # For persistence

---

### `state_schema.py`

Typed state definitions for data flowing through LangGraph.

### Key Types

* `SystemState` — Complete execution state
* `TurnData` — Current loop transient data
* `RoutingSignals` — Flow-control constants

### The Three State Zones

1. `current_turn`

   * Transient execution data
   * Overwritten every loop iteration

2. `strategy_context`

   * Persistent scratchpad memory for strategies

3. `routing_signal`

   * Controls graph routing and conditional execution

### Common Usage

```python
from engine.state_schema import create_initial_state

state = create_initial_state(
    run_id="run_123",
    payload={"intent": "test"},
    config={}
)
```

```python
from engine.state_schema import update_turn_data

updated = update_turn_data(
    current_turn,
    attack=attack_payload,
    node_name="attack"
)
```

---

## 2. Orchestrators

### `workflow_engine.py`

The main execution orchestrator responsible for running compiled LangGraph workflows.

### Key Features

* Async execution using `.astream()`
* Middleware lifecycle injection
* Parallel run management
* Graceful error handling
* Safe state delta merging

### Usage

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

---

### `graph_builder.py`

The dynamic compiler responsible for constructing executable LangGraph topologies.

It reads graph configurations, fetches node and strategy blueprints from registries, injects runtime configuration, and wires together graph edges and routing logic.

### Universal Topology

```text
Init → Attack → Defence → Eval → Router → [Conditional]
                                            ├─> Attack (loop)
                                            └─> END
```

### Default Graph Usage

```python
from engine.graph_builder import build_default_graph

graph = build_default_graph()
```

### Custom Graph Usage

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

---

## 3. Lookup Tables

### `registry.py`

The central registry for nodes and strategies.

It maps string identifiers (such as `"http_defence"`) to uninstantiated Python class blueprints.

This allows the engine to dynamically construct execution graphs at runtime.

---

### `provider_registry.py`

Maps provider identifiers to LLM provider implementations.

Examples:

* `"ollama"`
* `"openai"`

This enables nodes and strategies to dynamically resolve the models they require.

---

## 4. Utilities

### `debug_utils.py`

Unified tracing and logging utilities that provide:

* Timestamped execution traces
* Structured debug output
* Graph execution visibility
* Easier runtime diagnostics

---

# 📜 Gold Standard Rules for Engine Interaction

If you are modifying the engine or building systems that interact with it, these rules are mandatory.

---

## 1. Fail-Fast State Access

Never use permissive root-level access patterns such as:

```python
state.get("current_turn", {})
```

Instead, use strict access:

```python
state["current_turn"]
```

If a required key is missing, raise an error immediately.

This prevents silent corruption and invalid execution states.

---

## 2. Deep Copy Nested Contexts

When working with nested mutable structures from state (especially `strategy_context`), always use `copy.deepcopy()` before modification.

This prevents accidental reference mutation across execution cycles.

---

## 3. No Singleton Registrations

Always register **class blueprints**, never instantiated objects.

Correct:

```python
registry.register("name", MyClass)
```

Incorrect:

```python
registry.register("name", MyClass())
```

Instantiation is solely the responsibility of the `GraphBuilder`.

---

# 🧩 Design Principles

1. **Domain Models Over Primitives**

   * Avoid raw strings and dictionaries in execution flows

2. **Dependency Injection**

   * No hidden global state

3. **Async-First Architecture**

   * All I/O operations should remain non-blocking

4. **Separation of Concerns**

   * The engine handles orchestration and execution
   * Business logic belongs inside nodes and strategies

---

# 🔌 Extension Points

The engine is intentionally designed for modular extension.

You can provide custom implementations for:

* Attack nodes
* Defence nodes
* Evaluation nodes
* Routers
* Strategies
* Providers
* Middleware

All integrations should follow the registry-driven architecture.

---

# 📚 See Also

* `ARCHITECTURE.md` — Complete system architecture
* `strategies/README.md` — Strategy development
* `nodes/README.md` — Node implementation

