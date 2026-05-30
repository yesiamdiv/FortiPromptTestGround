# Adding a New Strategy

A strategy owns two things: **generation** (how attacks are crafted) and **routing** (when to loop, when to stop). Everything else — node execution, middleware, DB writes — is handled by the engine.

---

## Step 1 — Create the strategy file

Create `strategies/my_strategy.py`:

```python
from typing import Dict, Any
from strategies.base import AttackStrategy
from engine.state import SystemState, RoutingSignals, create_turn_data, update_turn_data
from core.models import create_simple_attack
from core.logging import step, warn


class MyStrategy(AttackStrategy):
    """
    One-line summary of what this strategy does.

    strategy_params:
        max_iterations: int  — number of attacks to run (default: 5)
    """

    def initialize(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Set up strategy memory in strategy_context."""
        params = self.config.get("strategy_params", {})
        return {
            "strategy_context": {
                "max_iterations": params.get("max_iterations", 5),
                "iteration": 0,
            }
        }

    async def execute_generation(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Generate the next attack payload and advance the iteration counter."""
        ctx = state.get("strategy_context", {})
        iteration = ctx.get("iteration", 0)

        # Build your attack here
        attack = create_simple_attack(
            f"Attack number {iteration}",
            strategy="my_strategy",
            iteration=iteration,
        )

        turn = update_turn_data(
            state.get("current_turn", {}),
            attack=attack,
        )

        step("Attack generated", iteration=iteration)
        return {
            "current_turn": turn,
            "strategy_context": {**ctx, "iteration": iteration + 1},
        }

    def route(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> str:
        """Return ATTACK to loop, END when done."""
        ctx = state.get("strategy_context", {})
        if ctx.get("iteration", 0) < ctx.get("max_iterations", 5):
            return RoutingSignals.ATTACK
        return RoutingSignals.END

    @classmethod
    def get_dependency_schema(cls) -> Dict[str, Any]:
        """JSON schema for strategy_params — used by the frontend config UI."""
        return {
            "type": "object",
            "properties": {
                "max_iterations": {
                    "type": "integer",
                    "default": 5,
                    "description": "Number of attacks to run"
                }
            }
        }
```

---

## Step 2 — Register the strategy

Open `engine/registry.py` and add two things:

**Import:**
```python
from strategies.my_strategy import MyStrategy
```

**Registration** (inside `register_all_components()`):
```python
_strategy_registry.register("my_strategy", MyStrategy)
```

---

## Step 3 — Add to `GraphConfig` literal (if using a new graph type)

If your strategy requires a new graph topology, add it to the `graph_type` literal in `core/config.py`:

```python
graph_type: Literal["manual", "automatic", "default", "batch", "my_type"]
```

If it works with an existing graph type (e.g. `"automatic"`), skip this step.

---

## Step 4 — Use it in a run

```json
{
  "graph_type": "automatic",
  "attack_node_config": { "node_type": "default_attack" },
  "defense_node_config": { "node_type": "http_defence", "node_params": { "target_url": "http://..." } },
  "evaluation_node_config": { "node_type": "llm_eval" },
  "strategy_config": {
    "strategy_name": "my_strategy",
    "strategy_params": { "max_iterations": 10 }
  }
}
```

---

## Key Rules

- **Route via `RoutingSignals` only.** Return `RoutingSignals.ATTACK` to loop, `RoutingSignals.END` to finish. Never hardcode `"attack"` or `"__end__"` strings.
- **All strategy state goes in `strategy_context`.** Do not use instance variables for per-run state — LangGraph may call your strategy methods from different contexts.
- **Return state deltas, not full state.** `execute_generation` should return only the keys it changes (`current_turn`, `strategy_context`).
- **`initialize` is called once per run**, before the first attack node execution.
- **`route` is called once per cycle**, after the evaluation node.
