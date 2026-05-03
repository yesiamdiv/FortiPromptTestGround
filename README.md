# Adversarial Testing Engine

A modular, production-ready framework for automated adversarial testing of AI systems using LangGraph.

## 🎯 Overview

This engine separates concerns between **execution infrastructure**, **business logic**, **operational code**, and **side-effects** to create a flexible, maintainable adversarial testing system.

### Key Features

- ✅ **Universal Graph Topology** - Single execution path handles all attack methodologies
- ✅ **Strategy Pattern** - Swap attack approaches without touching infrastructure
- ✅ **Middleware Injection** - Observe execution without polluting core logic
- ✅ **Dependency Injection** - Zero global state, fully parallelizable
- ✅ **Async-First** - Non-blocking I/O throughout
- ✅ **Default Implementation** - Works out of the box without external dependencies

## 🚀 Quick Start

### Installation

```bash
# Clone or copy the project
cd adversarial-engine

# Install dependencies
pip install -r requirements.txt
```

### Run Tests

```bash
# Run the complete test suite (no external dependencies needed)
python test_engine.py
```

This will demonstrate:
- Basic execution with default components
- Parallel execution of multiple runs
- Custom strategy configuration
- State structure inspection
- Error handling and recovery

### Basic Usage

```python
import asyncio
from engine.workflow_engine import create_default_engine
from strategies.default_strategy import DefaultStrategy

async def main():
    # Create engine (uses default graph + logging middleware)
    engine = create_default_engine()
    
    # Create strategy
    strategy = DefaultStrategy({"max_attempts": 3})
    
    # Execute adversarial run
    result = await engine.execute_run(
        payload={
            "intent": "Test jailbreak resistance",
            "target": "my-ai-system"
        },
        strategy=strategy
    )
    
    # Check results
    eval_result = result['current_turn']['evaluation']
    print(f"Result: {eval_result.to_summary()}")

if __name__ == "__main__":
    asyncio.run(main())
```

## 📁 Project Structure

```
adversarial-engine/
├── engine/              # Core execution engine
│   ├── domain_models.py      # AttackPayload, DefencePayload, EvalResult
│   ├── state_schema.py       # SystemState definitions
│   ├── graph_builder.py      # Universal graph topology
│   ├── workflow_engine.py    # Orchestrator with middleware injection
│   └── README.md
│
├── strategies/          # Attack strategies (the "brain")
│   ├── base.py               # Abstract strategy interface
│   ├── default_strategy.py   # Testing implementation
│   ├── data/                 # Templates, seeds, configs
│   │   ├── prompts/
│   │   ├── seeds/
│   │   └── configs/
│   └── README.md
│
├── nodes/               # Execution nodes (the "workers")
│   ├── base.py               # Abstract node interfaces
│   ├── default_nodes.py      # Testing implementations
│   └── README.md
│
├── middlewares/         # Observers (side-effects)
│   ├── base.py               # Abstract middleware interface
│   ├── logging_middleware.py # Console logging
│   └── README.md
│
├── providers/           # LLM provider integrations (to be implemented)
│   └── README.md
│
├── server/              # Backend server (to be implemented)
│   ├── api/                  # HTTP endpoints
│   ├── websocket/            # WebSocket management
│   ├── database/             # MongoDB layer
│   ├── config/               # Server configuration
│   └── README.md
│
├── tests/               # Test suite
│
├── ARCHITECTURE.md      # Comprehensive architectural documentation
├── requirements.txt     # Python dependencies
└── test_engine.py      # Complete test suite
```

## 🧠 Core Concepts

### The Universal Graph Topology

```
Init → Attack → Defence → Eval → Router → [Conditional]
                                            ├─> Attack (loop)
                                            └─> END
```

Every adversarial run follows this path. Complexity is managed by the **Strategy**, not by changing the graph structure.

### The State Contract

State flows through the graph in three zones:

```python
class SystemState:
    current_turn: TurnData        # TRANSIENT - Overwritten each loop
    strategy_context: Dict        # SCRATCHPAD - Strategy's memory
    routing_signal: str           # ROUTING - Flow control
```

### Domain Models

Never pass raw strings or dicts. Always wrap in domain objects:

```python
# ✅ GOOD
attack = create_simple_attack("Ignore your instructions", metadata={...})
defence = create_defence_response(text=response.text, status_code=200)
eval_result = create_eval_result(score=0.8, success=True, category="jailbreak")

# ❌ BAD
attack = "Ignore your instructions"
defence = {"text": response.text, "status": 200}
eval_result = {"score": 0.8, "success": True}
```

## 📚 Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Complete system architecture (MUST READ)
- **[engine/README.md](engine/README.md)** - Engine components
- **[strategies/README.md](strategies/README.md)** - Strategy development guide
- **[nodes/README.md](nodes/README.md)** - Node implementation guide
- **[middlewares/README.md](middlewares/README.md)** - Middleware development guide

## 🛠️ Development Guide

### Creating a Custom Strategy

```python
from strategies.base import AttackStrategy
from engine.domain_models import create_simple_attack
from engine.state_schema import create_turn_data

class MyStrategy(AttackStrategy):
    def setup(self, payload):
        return {
            "strategy_context": {
                "attempt_count": 0,
                "max_attempts": 5,
                # Your custom state here
            },
            "routing_signal": "continue"
        }
    
    def execute_generation(self, state):
        # Generate your attack here
        attack = create_simple_attack("Your attack text")
        turn = create_turn_data("turn_1", "attack")
        turn["attack"] = attack
        
        return {"current_turn": turn}
    
    def process_end_of_loop(self, state):
        # Decide whether to continue or end
        should_continue = # Your logic here
        
        return {
            "strategy_context": state["strategy_context"],
            "routing_signal": "attack" if should_continue else "__end__"
        }
```

### Creating a Custom Middleware

```python
from middlewares.base import BaseMiddleware

class MyMiddleware(BaseMiddleware):
    async def before_run(self, initial_state, config, run_id):
        """Called once before graph starts"""
        print(f"Starting run: {run_id}")
    
    async def after_step(self, step_data, run_id):
        """Called after every node execution"""
        # Self-filtering: only process relevant nodes
        if "eval_node" not in step_data:
            return
        
        # Your processing logic here
        eval_data = step_data["eval_node"]
        # ... handle the data
    
    async def after_run(self, final_state, run_id):
        """Called once when graph completes"""
        print(f"Completed run: {run_id}")
```

### Adding LLM Providers

```python
# providers/my_provider.py

class MyLLMProvider:
    def __init__(self, api_key):
        self.api_key = api_key
    
    async def generate(self, prompt, **kwargs):
        # Call your LLM API
        response = await your_llm_api.complete(prompt)
        return response.text
```

## 🎯 What's Implemented

### ✅ Core Engine (Fully Functional)
- Domain models with unified interfaces
- State schema with proper TypedDicts
- Universal graph builder
- Workflow engine with middleware injection
- Async execution and parallel runs

### ✅ Default Components (For Testing)
- Default strategy (no LLM required)
- Default nodes (mock responses)
- Logging middleware
- Complete test suite

### ⏳ To Be Implemented

#### Backend Server
- FastAPI application (`server/main.py`)
- HTTP API endpoints (`server/api/routes.py`)
- WebSocket manager (`server/websocket/manager.py`)
- Database layer (`server/database/`)
- Configuration management (`server/config/`)

#### LLM Providers
- Ollama provider (`providers/ollama_provider.py`)
- Gemini provider (`providers/gemini_provider.py`)
- OpenAI provider (`providers/openai_provider.py`)

#### Production Strategies
- Iterative improvement strategy
- Multi-seed parallel strategy
- Agentic JSON strategy
- Custom strategies as needed

#### Production Nodes
- LLM attack node (with actual provider calls)
- HTTP defence node (with real API requests)
- LLM eval node (with actual evaluator)

## 🧪 Testing

Run the included test suite:

```bash
python test_engine.py
```

This demonstrates:
1. ✅ Basic execution with default components
2. ✅ Parallel execution of multiple runs
3. ✅ Custom strategy configuration
4. ✅ State structure inspection
5. ✅ Error handling and recovery

All tests use **mock data** and require **no external dependencies**.

## 📋 Next Steps

### For Strategy Developers
1. Create strategy classes in `strategies/`
2. Store templates in `strategies/data/prompts/`
3. Store seeds in `strategies/data/seeds/`
4. Test with default engine

### For Infrastructure Developers
1. Implement LLM providers in `providers/`
2. Create production nodes in `nodes/`
3. Build FastAPI server in `server/`
4. Add database/WebSocket middlewares

### For Integration
1. Wire LLM providers into nodes
2. Configure server with engine
3. Add authentication and authorization
4. Deploy to production environment

## 🔒 Design Principles

1. **Separation of Concerns** - Strategies = logic, Nodes = I/O, Middlewares = side-effects
2. **Dependency Injection** - No global state, all dependencies explicit
3. **Async-First** - All I/O operations are non-blocking
4. **Fail-Safe** - Infrastructure failures don't crash AI execution
5. **Domain Models** - Rich objects over primitives
6. **Self-Filtering** - Middlewares decide relevance, not the engine

## 🤝 Contributing

When adding new components:

1. **Strategies**: Inherit from `AttackStrategy`, implement 3 methods
2. **Nodes**: Inherit from `BaseAdversarialNode`, keep async
3. **Middlewares**: Inherit from `BaseMiddleware`, wrap in try/except
4. **Providers**: Implement `generate()` method
5. **Documentation**: Update relevant README.md files

## 📄 License

[Your License Here]

## 🙋 Support

For detailed architecture documentation, see [ARCHITECTURE.md](ARCHITECTURE.md).

For module-specific guides, see README.md files in each directory:
- [engine/README.md](engine/README.md)
- [strategies/README.md](strategies/README.md)
- [nodes/README.md](nodes/README.md)
- [middlewares/README.md](middlewares/README.md)

---

**Built with ❤️ for the AI safety community**
