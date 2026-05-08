# 🧠 Strategies Module

The `strategies` directory contains the "Brains" of the adversarial testing engine. While Nodes act as the physical workers (executing API calls), Strategies contain all the business logic, prompt generation, memory management, and routing decisions.

## 🏛️ Overview

Strategies implement a highly structured pattern to encapsulate:
- **Attack Formulation:** Generating novel adversarial prompts or payloads.
- **Context Memory:** Managing multi-turn state (e.g., tracking previous attempts and feedback).
- **Intelligent Routing:** Deciding whether to loop for another attempt or end the graph based on evaluation scores.

---

## 🛠️ The Base Interface

All strategies must inherit from `AttackStrategy` and strictly implement these four methods:

```python
from typing import Dict, Any
from strategies.base import AttackStrategy
from engine.state_schema import SystemState, RoutingSignals

class MyStrategy(AttackStrategy):
    
    def initialize(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Called once at run start by the `init` node.
        Sets up the initial `strategy_context` (the sandbox).
        Returns: A state delta (dictionary) containing ONLY the updated strategy_context.
        """
        pass
        
    async def execute_generation(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Called by the `attack` node.
        Reads context, creates an `AttackPayload`, and updates internal counters.
        Returns: A state delta containing the `current_turn` and updated `strategy_context`.
        """
        pass
        
    def route(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> str:
        """
        Called by the `router` node after an evaluation.
        Analyzes the `EvalResult` and iteration counters.
        Returns: A raw string signal (`RoutingSignals.CONTINUE` or `RoutingSignals.END`).
        """
        pass

    @classmethod
    def get_dependency_schema(cls) -> Dict[str, Any]:
        """Returns JSON schema for static parameters required by this strategy."""
        return {"type": "object", "properties": {}}

```

---

## 🚦 The "Gold Standard" Rules

If you are writing a new strategy, you **must** adhere to these architectural laws:

1. **The Context Sandbox:** Strategies must never pollute the root `SystemState`. All internal memory (history, counters, previous best scores) must live exclusively inside the `strategy_context` dictionary.
2. **Deep Copy Contexts:** When reading `strategy_context` to modify nested lists or dictionaries (like appending to an attack history), you MUST use `copy.deepcopy(state["strategy_context"])` to prevent mutating LangGraph's immutable state history.
3. **Strict State Access (Fail-Fast):** Never use `.get()` with empty fallbacks on the root state. Use strict dictionary access:
* ❌ `context = state.get("strategy_context", {})`
* ✅ `if "strategy_context" not in state: raise ValueError(...)`


4. **Domain Model Property Access:** Never use old Java-style getters. Use strict Python properties:
* ❌ `eval_result.get_score()`
* ✅ `evaluation.score`


5. **Runtime Configurations:** Always accept and utilize `runtime_config`. This allows the frontend to override temperatures, strictness, or styles mid-execution without rebuilding the graph.

---

## 🏗️ Creating a Custom Strategy (Example)

Here is a compliant, minimal implementation of a custom strategy:

```python
import copy
from typing import Dict, Any
from strategies.base import AttackStrategy
from engine.domain_models import create_simple_attack
from engine.state_schema import create_turn_data, RoutingSignals, SystemState
from engine.debug_utils import tracer, step

class MyCustomStrategy(AttackStrategy):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config or {"max_attempts": 3})

    def initialize(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        tracer("MyCustomStrategy.initialize")
        
        # 1. Strict Access
        if "payload" not in state: raise ValueError("Missing payload")
        if "strategy_context" not in state: raise ValueError("Missing strategy_context")
        
        # 2. Deep Copy
        context = copy.deepcopy(state["strategy_context"])
        
        # 3. Setup Sandbox
        context.update({
            "attempt_count": 0,
            "max_attempts": self.config.get("max_attempts", 3),
            "history": []
        })
        
        # 4. Return Delta
        return {"strategy_context": context}

    async def execute_generation(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        if "strategy_context" not in state: raise ValueError("Missing strategy_context")
        
        context = copy.deepcopy(state["strategy_context"])
        current_attempt = context.get("attempt_count", 0) + 1
        
        # Generate Attack (Could use an LLM provider here!)
        attack_text = f"Custom Attack Attempt {current_attempt}"
        
        # Wrap in Domain Model
        attack = create_simple_attack(attack_text, strategy=self.name)
        
        turn = create_turn_data(f"turn_{current_attempt}", "attack")
        turn["attack"] = attack
        
        # Update Memory
        context["attempt_count"] = current_attempt
        context["history"].append(attack_text)
        
        return {
            "current_turn": turn,
            "strategy_context": context
        }

    def route(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> str:
        if "strategy_context" not in state: raise ValueError("Missing context")
        if "current_turn" not in state: raise ValueError("Missing turn data")
        
        context = state["strategy_context"]
        evaluation = state["current_turn"]["evaluation"] if "evaluation" in state["current_turn"] else None
        
        # Stop if successful
        if evaluation and evaluation.success:
            step("Target achieved! Ending.", score=evaluation.score)
            return RoutingSignals.END
            
        # Stop if out of attempts
        if context.get("attempt_count", 0) >= context.get("max_attempts", 3):
            return RoutingSignals.END
            
        # Otherwise, loop!
        return RoutingSignals.CONTINUE

```

## 🔌 Using External LLMs inside Strategies

Strategies do not have access to the `GraphBuilder`. If a strategy needs an LLM to generate intelligent attacks (like the `IterativeImprovementStrategy`), it must dynamically fetch the provider from the registry during `__init__`:

```python
from engine.provider_registry import get_provider_registry

class SmartStrategy(AttackStrategy):
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        
        # Fetch the LLM provider to use for generating attacks
        provider_name = self.config.get("llm_provider_name", "ollama")
        self.provider = get_provider_registry().get(provider_name, config=self.config)

```