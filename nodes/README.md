# 🧩 Nodes Module

Execution nodes are the "physical actors" of the LangGraph execution loop. While Strategies act as the "Brains" (making decisions, writing prompts), Nodes act as the "Hands" (making HTTP requests, querying databases, and routing LangGraph edges).

## 🏛️ Overview

Nodes are strictly scoped objects that adhere to the following rules:
- **Single Responsibility:** They execute exactly one operation per call (e.g., hit an API, run a local ML model, or delegate to a strategy).
- **Strict Initialization:** They accept exactly one argument: `config: Dict[str, Any]`. They extract their specific dependencies from `self.config["node_params"]`.
- **Pure Functions (State Deltas):** They **never** mutate the incoming `state` object. They return dictionaries containing only the keys that need to be updated.
- **Domain Model Enforcement:** They strictly read and write using Pydantic/Dataclass Domain Models (`AttackPayload`, `DefencePayload`, `EvalResult`).

---

## 🛠️ The "Gold Standard" Interface

All nodes must inherit from `BaseAdversarialNode`. Here is the modern template for creating a node:

```python
from typing import Dict, Any
from nodes.base import BaseAdversarialNode
from engine.state_schema import SystemState
from engine.domain_models import create_defence_response

class MyCustomNode(BaseAdversarialNode):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        
        # 1. Extract parameters from config
        self.node_params = self.config["node_params"] if "node_params" in self.config else {}
        self.api_key = self.node_params.get("api_key")
        self.url = self.node_params.get("url", "[http://default.com](http://default.com)")
    
    async def execute(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        if runtime_config is None: runtime_config = {}
        
        # 2. STRICT State Access (Fail-fast, no .get() on root)
        if "current_turn" not in state:
            raise ValueError("Corrupted state: Missing 'current_turn'.")
            
        current_turn = state["current_turn"]
        attack = current_turn["attack"] if "attack" in current_turn else None
        
        # 3. Perform I/O or operation using Domain Models
        attack_string = attack.to_string() if attack else ""
        result_text = await self._do_external_work(attack_string)
        
        # 4. Wrap the result in a Domain Model
        defence = create_defence_response(text=result_text, status_code=200)
        
        # 5. Return Clean Deltas (LangGraph handles the merge)
        return {
            "current_turn": {
                "defence": defence,
                "node_name": self.name
            }
        }

```

---

## 🗂️ Node Archetypes

### 1. Environment / I/O Nodes

Nodes that interact with the outside world or heavy computational models. They are entirely agnostic to the testing strategy.

* `HTTPDefenceNode`: Blasts payloads at an external webhook URL and captures the HTTP response.
* `ServerEvalNode`: Sends the Attack and Defence payloads to an external LLM server for scoring.
* `MultilayerDefenseNode`: Passes the attack through an in-memory PyTorch/BERT Machine Learning pipeline.

### 2. Strategy-Delegation Nodes

Nodes that act as a bridge between LangGraph and the active `AttackStrategy`. They contain no logic of their own.

* `StrategyDrivenAttackNode`: Simply calls `await strategy.execute_generation(state, runtime_config)`.
* `RouterNode`: Simply calls `strategy.route(state, runtime_config)` and validates the returned LangGraph edge signal.

---

## 🚦 Node Rules

**DO:**

* ✅ **Use `node_params`:** Extract all API keys, URLs, and static configurations from `self.config["node_params"]`.
* ✅ **Use Domain Models:** Always expect `attack`, `defence`, and `evaluation` to be their respective dataclass objects. Use methods like `.to_string()` or property access like `.score`.
* ✅ **Fail Fast:** Use strict dictionary access (`state["key"]`) on the root state. If the engine passes a corrupted state, let it crash loudly with a `ValueError`.
* ✅ **Use `runtime_config`:** Allow dynamic overrides (e.g., `active_url = runtime_config.get("url", self.url)`).

**DON'T:**

* ❌ **No Custom `__init__` Signatures:** Never write `def __init__(self, api_key: str):`. The `GraphBuilder` only passes `config`.
* ❌ **No Root State Mutations:** Never do `state["current_turn"]["defence"] = my_defence`. Always return `{"current_turn": {"defence": my_defence}}`.
* ❌ **No `StrategyProxyNode`:** This base class is deprecated. Delegate explicitly inside the `execute` method.

---

## 🔌 Wiring Nodes into the Graph

You do not wire instances manually anymore. The engine uses a **Registry Pattern**.

1. **Register the Class:** (During server startup)

```python
from engine.registry import get_node_registry
from nodes.my_custom_node import MyCustomNode

registry = get_node_registry()
registry.register("my_custom", MyCustomNode) # Register the blueprint, NOT an instance!

```

2. **The GraphBuilder handles the rest:** (At runtime)
The database provides a configuration JSON. The `ConfigurableGraphBuilder` reads it, grabs the class blueprint from the registry, injects the config, and stitches the LangGraph topology together dynamically.

```json
{
  "defense_node_config": {
    "node_type": "my_custom",
    "node_params": { "url": "[https://api.target.com](https://api.target.com)", "api_key": "sk-123" }
  }
}

```
