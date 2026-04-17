# Adversarial Testing Engine - Architectural Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Core Design Principles](#core-design-principles)
3. [Architecture Components](#architecture-components)
4. [Data Flow & Execution Lifecycle](#data-flow--execution-lifecycle)
5. [Extension Points](#extension-points)
6. [Best Practices](#best-practices)

---

## System Overview

The Adversarial Testing Engine is a modular, LangGraph-based system for automated adversarial testing of AI systems. It separates concerns between execution infrastructure (the engine), business logic (strategies), operational code (nodes), and side-effects (middlewares).

### Key Features

- **Universal Graph Topology**: Single, simple execution path that handles all attack methodologies
- **Strategy Pattern**: Swap entire attack approaches without changing infrastructure
- **Middleware Injection**: Observe execution without polluting core logic
- **Dependency Injection**: Zero global state, fully parallelizable
- **Async-First**: Non-blocking I/O throughout

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Server                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  HTTP API    │  │  WebSocket   │  │   Database   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Workflow Engine                           │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Middleware Layer (Observers)                      │    │
│  │  • Database Persistence                            │    │
│  │  • WebSocket Broadcasting                          │    │
│  │  • Logging & Metrics                               │    │
│  └────────────────────────────────────────────────────┘    │
│                           │                                 │
│                           ▼                                 │
│  ┌────────────────────────────────────────────────────┐    │
│  │         Universal LangGraph Topology               │    │
│  │                                                     │    │
│  │  Init → Attack → Defence → Eval → Router → Loop    │    │
│  │                                        │            │    │
│  │                                        └─► END      │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ Strategy │    │  Nodes   │    │ Providers│
    │  (Brain) │    │ (Workers)│    │  (LLMs)  │
    └──────────┘    └──────────┘    └──────────┘
```

---

## Core Design Principles

### 1. Separation of Concerns

**Strategies** = WHAT to attack and WHEN to stop
- Business logic lives here
- Prompt generation
- Multi-turn state management
- Success/failure criteria
- Routing decisions

**Nodes** = HOW to execute operations
- Infrastructure dependencies (API keys, LLM clients)
- Network I/O (LLM calls, HTTP requests)
- Zero routing logic
- Stateless execution

**Middlewares** = OBSERVE without mutating
- Database writes
- WebSocket broadcasts
- Logging and metrics
- Read-only access to state

**Graph Builder** = Physical topology
- Wires nodes together
- Defines execution sequence
- Blind to business logic

### 2. The State Contract

The `SystemState` flows through the entire graph and has three zones:

```python
class SystemState(TypedDict):
    # ZONE 1: TRANSIENT - Overwritten each loop
    current_turn: TurnData
    
    # ZONE 2: SCRATCHPAD - Strategy's private memory  
    strategy_context: Dict[str, Any]
    
    # ZONE 3: ROUTING - Flow control
    routing_signal: str
```

**Rules:**
- Strategies write to all three zones
- Nodes only update `current_turn`
- Middlewares read but never write
- Graph reads `routing_signal` for conditional edges

### 3. Domain Models Over Primitives

Never pass raw strings or dicts. Always wrap in domain objects:

- `AttackPayload` - Encapsulates generated attacks
- `DefencePayload` - Encapsulates target responses  
- `EvalResult` - Encapsulates evaluation outputs

Each provides a unified interface:
- `.to_string()` for logging
- `.to_dict()` for database
- `.to_messages()` for LLM providers
- `.to_api_format()` for external APIs

### 4. Async-First Execution

All I/O operations are async:
- Node execution: `async def execute(...)`
- Middleware hooks: `async def after_step(...)`
- Engine orchestration: `async def execute_run(...)`

This enables:
- Parallel execution of multiple runs
- Non-blocking middleware operations
- Efficient LLM batching

### 5. Fail-Safe Infrastructure

**Core Principle**: Infrastructure failures must never crash AI execution.

- Middlewares wrap operations in try/except
- Database errors → log and continue
- WebSocket disconnects → graceful degradation
- The graph execution survives all side-effect failures

---

## Architecture Components

### Engine Module (`engine/`)

The nervous system of the application.

#### `domain_models.py`
Rich wrapper classes that carry both data and behavior.

```python
from engine.domain_models import create_simple_attack

attack = create_simple_attack(
    "Ignore your instructions",
    metadata={"technique": "jailbreak"}
)

# Unified interface
text = attack.to_string()        # For display
messages = attack.to_messages()  # For LLM calls
data = attack.to_dict()          # For database
```

#### `state_schema.py`
TypedDict definitions for the state flowing through LangGraph.

```python
from engine.state_schema import create_initial_state, RoutingSignals

state = create_initial_state(
    run_id="run_123",
    initial_payload={"intent": "test jailbreak"},
    config={}
)
```

#### `graph_builder.py`
Constructs the universal topology using injected nodes.

```python
from engine.graph_builder import UniversalGraphBuilder

builder = UniversalGraphBuilder(
    init_node=init_node,
    attack_node=attack_node,
    defence_node=defence_node,
    eval_node=eval_node,
    router_node=router_node
)

compiled_graph = builder.compile()
```

#### `workflow_engine.py`
The orchestrator that executes the graph with middleware injection.

```python
from engine.workflow_engine import WorkflowEngine

engine = WorkflowEngine(
    compiled_graph=graph,
    middlewares=[db_middleware, ws_middleware]
)

final_state = await engine.execute_run(
    initial_payload={"intent": "test prompt injection"},
    strategy=my_strategy
)
```

### Strategies Module (`strategies/`)

The brain of the system - contains all business logic.

#### `base.py`
Abstract interface all strategies must implement.

```python
class AttackStrategy(ABC):
    @abstractmethod
    def setup(self, initial_payload) -> dict:
        """Initialize strategy state"""
        
    @abstractmethod
    def execute_generation(self, state) -> dict:
        """Generate next attack"""
        
    @abstractmethod
    def process_end_of_loop(self, state) -> dict:
        """Process evaluation and route"""
```

#### `default_strategy.py`
No-op implementation for testing without LLMs.

#### `data/`
Strategy-specific assets:
- `prompts/` - Template files
- `seeds/` - Initial attack vectors
- `configs/` - Strategy configurations

### Nodes Module (`nodes/`)

Dumb workers that execute operations.

#### `base.py`
Abstract interfaces for nodes.

```python
class BaseAdversarialNode(ABC):
    @abstractmethod
    async def execute(self, state, config) -> dict:
        """Perform operation and return state updates"""
```

#### `default_nodes.py`
Testing implementations that don't require external dependencies.

- `DefaultInitNode` - Calls strategy.setup()
- `DefaultAttackNode` - Calls strategy.execute_generation()
- `DefaultDefenceNode` - Returns mock HTTP responses
- `DefaultEvalNode` - Returns random scores
- `DefaultRouterNode` - Calls strategy.process_end_of_loop()

### Middlewares Module (`middlewares/`)

Observers that handle infrastructure side-effects.

#### `base.py`
Abstract interface for middlewares.

```python
class BaseMiddleware(ABC):
    async def before_run(self, initial_state, config, run_id):
        """Called once before graph starts"""
        
    async def after_step(self, step_data, run_id):
        """Called after every node execution"""
        
    async def after_run(self, final_state, run_id):
        """Called once when graph completes"""
```

#### `logging_middleware.py`
Console logging for development and debugging.

---

## Data Flow & Execution Lifecycle

### Complete Run Lifecycle

```
1. API receives request
   ├─> Generate run_id
   ├─> Instantiate strategy
   └─> Call engine.execute_run()

2. Engine: before_run hooks
   ├─> Database: Create run record
   ├─> WebSocket: Send "started" event
   └─> Logging: Print run header

3. Graph: InitNode
   ├─> Strategy.setup() generates initial context
   └─> Middlewares observe init completion

4. Graph: AttackNode  
   ├─> Strategy.execute_generation() creates payload
   ├─> Wrap in AttackPayload domain object
   └─> Middlewares save attack to database

5. Graph: DefenceNode
   ├─> Extract AttackPayload from current_turn
   ├─> Make HTTP request to target
   ├─> Wrap response in DefencePayload
   └─> Middlewares save response to database

6. Graph: EvalNode
   ├─> Call evaluator LLM with attack + defence
   ├─> Wrap result in EvalResult
   └─> Middlewares save evaluation to database

7. Graph: RouterNode
   ├─> Strategy.process_end_of_loop() analyzes result
   ├─> Update attempt counters
   ├─> Calculate routing_signal
   └─> Middlewares observe routing decision

8. Graph: Conditional Edge
   ├─> Read routing_signal from state
   ├─> If "attack" → return to step 4
   └─> If "__end__" → proceed to step 9

9. Engine: after_run hooks
   ├─> Database: Mark run complete
   ├─> WebSocket: Send "finished" event
   └─> Logging: Print summary

10. Return final_state to API
```

### State Mutations

**InitNode output:**
```python
{
    "strategy_context": {
        "intent": "test jailbreak",
        "attempt_count": 0,
        "max_attempts": 5
    },
    "routing_signal": "continue"
}
```

**AttackNode output:**
```python
{
    "current_turn": {
        "turn_id": "turn_1",
        "attack": AttackPayload(...),
        "timestamp": "2024-01-01T12:00:00"
    },
    "strategy_context": {
        "attempt_count": 1
    }
}
```

**DefenceNode output:**
```python
{
    "current_turn": {
        ...
        "defence": DefencePayload(...)
    }
}
```

**EvalNode output:**
```python
{
    "current_turn": {
        ...
        "evaluation": EvalResult(...)
    }
}
```

**RouterNode output:**
```python
{
    "strategy_context": {
        "attempt_count": 1,
        "best_score": 0.8
    },
    "routing_signal": "attack"  # or "__end__"
}
```

---

## Extension Points

### Creating a New Strategy

1. Inherit from `AttackStrategy`
2. Implement three required methods
3. Store data in `strategies/data/` as needed

```python
from strategies.base import AttackStrategy

class MyStrategy(AttackStrategy):
    def setup(self, initial_payload):
        # Initialize your scratchpad
        return {
            "strategy_context": {...},
            "routing_signal": "continue"
        }
    
    def execute_generation(self, state):
        # Generate attack using LLM or templates
        # Access self.config for strategy settings
        return {
            "current_turn": {...}
        }
    
    def process_end_of_loop(self, state):
        # Analyze evaluation and decide routing
        return {
            "strategy_context": {...},
            "routing_signal": "attack" or "__end__"
        }
```

### Creating a New Middleware

1. Inherit from `BaseMiddleware`
2. Implement relevant hooks
3. Use self-filtering for efficiency

```python
from middlewares.base import BaseMiddleware

class MyMiddleware(BaseMiddleware):
    async def after_step(self, step_data, run_id):
        # Self-filtering
        if "eval_node" not in step_data:
            return
        
        # Extract data
        eval_data = step_data["eval_node"]
        
        # Perform side-effect (DB, API, etc.)
        await self.send_alert(eval_data)
```

### Adding a New LLM Provider

1. Create provider class in `providers/`
2. Implement `generate()` method
3. Inject into attack/eval nodes

```python
from providers.base import BaseLLMProvider

class MyProvider(BaseLLMProvider):
    async def generate(self, prompt, **kwargs):
        # Call your LLM API
        response = await self.client.complete(prompt)
        return response.text
```

---

## Best Practices

### For Strategy Developers

**DO:**
- ✅ Store all state in `strategy_context`
- ✅ Always return domain objects (AttackPayload, etc.)
- ✅ Use helpers to load data from `strategies/data/`
- ✅ Document expected config parameters

**DON'T:**
- ❌ Access database or WebSockets directly
- ❌ Return raw strings as attacks
- ❌ Store state in instance variables
- ❌ Make assumptions about node implementations

### For Node Developers

**DO:**
- ✅ Inject all dependencies via `__init__`
- ✅ Keep `execute()` async
- ✅ Return only mutated state portions
- ✅ Handle errors gracefully

**DON'T:**
- ❌ Use global variables
- ❌ Make routing decisions
- ❌ Mutate input state directly
- ❌ Block on synchronous I/O

### For Middleware Developers

**DO:**
- ✅ Wrap logic in try/except
- ✅ Use async for all I/O
- ✅ Implement self-filtering
- ✅ Log errors, don't raise

**DON'T:**
- ❌ Mutate step_data or state
- ❌ Block the execution thread
- ❌ Crash on infrastructure failures
- ❌ Make assumptions about node order

---

## Quick Start Example

```python
import asyncio
from engine.workflow_engine import create_default_engine
from strategies.default_strategy import DefaultStrategy

async def main():
    # Create engine with default components
    engine = create_default_engine()
    
    # Create strategy
    strategy = DefaultStrategy({"max_attempts": 3})
    
    # Execute run
    result = await engine.execute_run(
        initial_payload={
            "intent": "Test adversarial robustness",
            "target": "example-ai-system"
        },
        strategy=strategy
    )
    
    print(f"Run completed: {result['run_id']}")
    print(f"Final evaluation: {result['current_turn']['evaluation'].to_summary()}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Troubleshooting

**Issue: "Strategy not found in config"**
- Ensure you're passing strategy in runtime config
- Check: `config["configurable"]["strategy"]`

**Issue: "AttributeError: has no attribute 'to_dict'"**
- You're returning a primitive instead of a domain object
- Wrap in `create_simple_attack()`, `create_defence_response()`, etc.

**Issue: "Middleware not being called"**
- Verify middleware is in engine's middleware list
- Check self-filtering logic isn't too restrictive

**Issue: "Graph stuck in loop"**
- Strategy not returning proper routing_signal
- Check `process_end_of_loop()` returns "__end__" eventually

---

## Future Enhancements

- [ ] Parallel seed execution
- [ ] Dynamic graph topology per strategy
- [ ] Checkpoint/resume support
- [ ] Distributed execution across workers
- [ ] Real-time strategy hot-swapping
- [ ] Built-in A/B testing framework

---

For module-specific documentation, see README.md in each directory.
