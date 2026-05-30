# Adding a New Node

Nodes are the execution units of the graph — each does one focused thing (generate an attack, call the target system, run an evaluator). They receive `SystemState`, do their work, and return a state delta.

---

## Step 1 — Create the node file

Create `nodes/my_node.py`:

```python
from typing import Dict, Any
from nodes.base import BaseAdversarialNode
from engine.state import SystemState, update_turn_data
from core.logging import step, warn, err


class MyNode(BaseAdversarialNode):
    """
    One-line summary of what this node does.

    node_params:
        some_param: str  — description of the parameter
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.some_param = self.config.get("some_param", "default_value")

    async def execute(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute node logic and return a state delta."""
        current_turn = state.get("current_turn", {})

        try:
            # ... your node logic here ...
            result = f"Processed: {self.some_param}"

            updated_turn = update_turn_data(current_turn, node_name="my_node")
            step("MyNode executed", result=result)
            return {"current_turn": updated_turn}

        except Exception as e:
            err(f"MyNode failed: {e}")
            raise

    @classmethod
    def get_node_schema(cls) -> Dict[str, Any]:
        """JSON schema for node_params — used by the discovery API and frontend."""
        return {
            "type": "object",
            "properties": {
                "some_param": {
                    "type": "string",
                    "default": "default_value",
                    "description": "Description of the parameter"
                }
            }
        }
```

---

## Step 2 — Register the node

Open `engine/registry.py` and add two things:

**Import:**
```python
from nodes.my_node import MyNode
```

**Factory registration** (inside `register_all_components()`):
```python
_node_registry.register("my_node", lambda config: MyNode(config))
```

The factory lambda is how the graph builder instantiates nodes with their per-run config. For simple cases `lambda config: MyNode(config)` is all you need. For nodes that need extra dependencies (e.g. an HTTP client), initialise them inside the lambda or inside `__init__`.

---

## Step 3 — Use the node in a run config

Depending on whether your node is an attack, defence, or evaluation node, set the corresponding config field:

```json
{
  "graph_type": "automatic",
  "attack_node_config": { "node_type": "my_node", "node_params": { "some_param": "hello" } },
  "defense_node_config": { "node_type": "http_defence" },
  "evaluation_node_config": { "node_type": "llm_eval" },
  "strategy_config": { "strategy_name": "default", "strategy_params": {} }
}
```

---

## Key Rules

- **Return state deltas only.** Return a dict containing only the keys your node changed. Do not return a full copy of `SystemState`.
- **Use `update_turn_data()` to produce turn updates.** It deep-copies the existing turn before applying changes, preventing shared mutable references.
- **Nodes are routing-agnostic.** Never set `routing_signal` from a node — that is the strategy's job via `RouterNode`.
- **Nodes do not know about middlewares.** If you need to persist data, the middleware layer handles that after `execute()` returns.
- **`get_node_schema()` is optional but recommended.** It powers the discovery API (`GET /nodes/{category}`) which the frontend uses to build configuration forms.

---

## Node Categories

The graph builder slots nodes into three positions based on `GraphConfig`:

| Config field | Graph position | Typical node types |
|---|---|---|
| `attack_node_config` | After router, before defence | `strategy_attack`, `batch_wrapper` |
| `defense_node_config` | After attack | `http_defence`, `ensemble_defense`, `multilayer_defense` |
| `evaluation_node_config` | After defence, before router | `llm_eval`, `server_eval` |

The `router` node is always fixed — you do not configure it.
