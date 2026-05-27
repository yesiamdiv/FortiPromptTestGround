# Getting Started Guide

Complete guide to setting up and running the Adversarial Testing Engine.

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Running with Default Components](#running-with-default-components)
4. [Setting Up LLM Providers](#setting-up-llm-providers)
5. [Starting the Server](#starting-the-server)
6. [Using the API](#using-the-api)
7. [Creating Custom Strategies](#creating-custom-strategies)
8. [Troubleshooting](#troubleshooting)

---

## Installation

### Prerequisites

- Python 3.9+
- MongoDB (for persistence)
- Ollama (optional, for local LLM)

### Install Dependencies

```bash
cd adversarial-engine
pip install -r requirements.txt
```

---

## Quick Start

### 1. Test Without Any Setup

The engine works immediately with default components:

```bash
python test_engine.py
```

This demonstrates all features using mock data (no LLM or database required).

### 2. Start Infrastructure (Optional)

If you want persistence and real-time updates:

```bash
# Start MongoDB and Ollama
docker-compose up -d

# Verify services
docker-compose ps
```

---

## Running with Default Components

The default components let you test the entire system without external dependencies.

### Example: Basic Run

```python
import asyncio
from engine.workflow_engine import create_default_engine
from strategies.default_strategy import DefaultStrategy

async def main():
    # Create engine with logging
    engine = create_default_engine()
    
    # Create strategy
    strategy = DefaultStrategy({"max_attempts": 3})
    
    # Execute run
    result = await engine.execute_run(
        payload={
            "intent": "Test jailbreak resistance",
            "target": "my-ai-system"
        },
        strategy=strategy
    )
    
    # Check results
    print(f"Run ID: {result['run_id']}")
    print(f"Attempts: {result['strategy_context']['attempt_count']}")
    
    eval_result = result['current_turn']['evaluation']
    print(f"Success: {eval_result.is_success()}")
    print(f"Score: {eval_result.get_score():.2f}")

if __name__ == "__main__":
    asyncio.run(main())
```

Save as `quick_test.py` and run:
```bash
python quick_test.py
```

---

## Setting Up LLM Providers

### Ollama (Local)

1. **Install Ollama** (if not using Docker):
   ```bash
   # Visit https://ollama.ai for installation
   ```

2. **Pull a model**:
   ```bash
   ollama pull llama3
   ```

3. **Use in code**:
   ```python
   from providers.ollama_provider import OllamaProvider
   from nodes.llm_attack_node import LLMAttackNode
   from nodes.default_nodes import (
       DefaultInitNode, DefaultDefenceNode,
       DefaultEvalNode, DefaultRouterNode
   )
   from engine.graph_builder import UniversalGraphBuilder
   
   # Create provider
   provider = OllamaProvider({
       "model": "llama3",
       "base_url": "http://localhost:11434"
   })
   
   # Create nodes
   init_node = DefaultInitNode()
   attack_node = LLMAttackNode(provider)  # Uses LLM
   defence_node = DefaultDefenceNode()
   eval_node = DefaultEvalNode()
   router_node = DefaultRouterNode()
   
   # Build graph
   builder = UniversalGraphBuilder(
       init_node, attack_node, defence_node,
       eval_node, router_node
   )
   graph = builder.compile()
   ```

### Google Gemini

1. **Get API key**:
   - Visit https://makersuite.google.com/app/apikey
   - Create API key

2. **Set environment**:
   ```bash
   export GOOGLE_API_KEY="your-api-key-here"
   ```

3. **Use in code**:
   ```python
   from providers.gemini_provider import GeminiProvider
   
   provider = GeminiProvider({
       "api_key": os.getenv("GOOGLE_API_KEY"),
       "model": "gemini-pro"
   })
   ```

### OpenAI

1. **Get API key**:
   - Visit https://platform.openai.com/api-keys
   - Create API key

2. **Set environment**:
   ```bash
   export OPENAI_API_KEY="sk-your-key-here"
   ```

3. **Use in code**:
   ```python
   from providers.openai_provider import OpenAIProvider
   
   provider = OpenAIProvider({
       "api_key": os.getenv("OPENAI_API_KEY"),
       "model": "gpt-4"
   })
   ```

---

## Starting the Server

### 1. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env with your settings
nano .env
```

### 2. Start Services

```bash
# Start MongoDB (if not using Docker)
# Or use docker-compose:
docker-compose up -d mongodb

# Verify database is running
docker ps | grep mongo
```

### 3. Run Server

```bash
# Development mode (with auto-reload)
python server/main.py

# Or with uvicorn directly
uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Verify Server

Visit:
- http://localhost:8000 - Root endpoint
- http://localhost:8000/docs - Interactive API docs
- http://localhost:8000/api/v1/health - Health check

---

## Using the API

### Create a Run

```bash
curl -X POST http://localhost:8000/api/v1/runs/create \
  -H "Content-Type: application/json" \
  -d '{
    "intent": "Test jailbreak resistance",
    "target": "production-model",
    "strategy": "default",
    "strategy_config": {
      "max_attempts": 3
    }
  }'
```

Response:
```json
{
  "run_id": "run_abc123",
  "status": "running",
  "message": "Run started successfully",
  "websocket_url": "/ws/run_abc123"
}
```

### Get Run Status

```bash
curl http://localhost:8000/api/v1/runs/run_abc123
```

### Get Run Steps

```bash
curl http://localhost:8000/api/v1/runs/run_abc123/steps
```

### List All Runs

```bash
curl http://localhost:8000/api/v1/runs?status=completed&limit=10
```

### WebSocket Connection

```javascript
// JavaScript example
const ws = new WebSocket('ws://localhost:8000/api/v1/ws/run_abc123');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Update:', data);
  
  switch(data.type) {
    case 'run_started':
      console.log('Run started:', data.run_id);
      break;
    case 'attack_generated':
      console.log('Attack:', data.attack.preview);
      break;
    case 'evaluation_complete':
      console.log('Score:', data.evaluation.score);
      break;
    case 'run_completed':
      console.log('Run finished!');
      ws.close();
      break;
  }
};
```

---

## Creating Custom Strategies

### 1. Create Strategy File

Create `strategies/my_strategy.py`:

```python
from strategies.base import AttackStrategy
from engine.domain_models import create_simple_attack
from engine.state_schema import create_turn_data, RoutingSignals

class MyStrategy(AttackStrategy):
    def setup(self, payload):
        intent = payload.get("intent")
        
        return {
            "strategy_context": {
                "intent": intent,
                "attempt_count": 0,
                "max_attempts": self.config.get("max_attempts", 5)
            },
            "routing_signal": RoutingSignals.CONTINUE
        }
    
    def execute_generation(self, state):
        context = state["strategy_context"]
        
        # Your attack generation logic here
        attack_text = f"Custom attack #{context['attempt_count']}"
        attack = create_simple_attack(attack_text)
        
        turn = create_turn_data(
            f"turn_{context['attempt_count']}",
            "attack"
        )
        turn["attack"] = attack
        
        return {
            "current_turn": turn,
            "strategy_context": {
                **context,
                "attempt_count": context["attempt_count"] + 1
            }
        }
    
    def process_end_of_loop(self, state):
        context = state["strategy_context"]
        eval_result = state["current_turn"]["evaluation"]
        
        should_continue = (
            context["attempt_count"] < context["max_attempts"]
            and not eval_result.is_success()
        )
        
        return {
            "strategy_context": context,
            "routing_signal": RoutingSignals.ATTACK if should_continue else RoutingSignals.END
        }
```

### 2. Use Your Strategy

```python
from strategies.my_strategy import MyStrategy

strategy = MyStrategy({"max_attempts": 10})

result = await engine.execute_run(
    payload={"intent": "Custom test"},
    strategy=strategy
)
```

---

## Troubleshooting

### Database Connection Failed

```
⚠ Database connection failed: [Errno 61] Connection refused
```

**Solution**: Start MongoDB
```bash
docker-compose up -d mongodb
# Or install MongoDB locally
```

### Ollama Connection Failed

```
Ollama connection failed: Connection refused
```

**Solution**: Start Ollama
```bash
docker-compose up -d ollama
# Or run ollama serve
```

### Import Errors

```
ModuleNotFoundError: No module named 'langchain_ollama'
```

**Solution**: Install dependencies
```bash
pip install -r requirements.txt
```

### WebSocket Connection Refused

```
WebSocket connection refused
```

**Solution**: Ensure server is running and WebSocket endpoint matches:
```
ws://localhost:8000/api/v1/ws/{run_id}
```

### Strategy Not Found

```
Unknown strategy: my_strategy
```

**Solution**: Register your strategy in `server/api/routes.py`:
```python
# In create_run function
if request.strategy == "default":
    strategy = DefaultStrategy(request.strategy_config)
elif request.strategy == "my_strategy":
    from strategies.my_strategy import MyStrategy
    strategy = MyStrategy(request.strategy_config)
```

---

## Next Steps

1. ✅ Test with default components (`python test_engine.py`)
2. ✅ Start server (`python server/main.py`)
3. ✅ Try API endpoints (visit `/docs`)
4. 🔨 Create custom strategy
5. 🔨 Integrate LLM provider
6. 🔨 Build frontend UI
7. 🔨 Deploy to production

---

For more details, see:
- [ARCHITECTURE.md](ARCHITECTURE.md) - Complete system design
- [strategies/README.md](strategies/README.md) - Strategy development guide
- [server/README.md](server/README.md) - API documentation
