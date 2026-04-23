# Nodes Module

Execution nodes - the "dumb workers" that perform I/O operations.

## Overview

Nodes are stateless objects that:
- Hold infrastructure dependencies (LLM clients, API keys)
- Execute exactly one operation per call
- Return only mutated portions of state
- Contain zero routing or business logic

## Base Interface

```python
from nodes.base import BaseAdversarialNode

class MyNode(BaseAdversarialNode):
    def __init__(self, api_key, config=None):
        super().__init__(config)
        self.api_key = api_key
    
    async def execute(self, state: dict, config: dict) -> dict:
        """
        Perform operation and return state updates.
        
        Args:
            state: Complete SystemState from graph
            config: Runtime config (contains strategy instance)
        
        Returns:
            Dictionary with ONLY mutated state fields
        """
        # Read from state
        current_turn = state["current_turn"]
        
        # Perform operation
        result = await self.do_work(current_turn)
        
        # Return updates
        return {"current_turn": {...}}
```

## Node Types

### Strategy Proxy Nodes

Nodes that delegate to strategy methods:

```python
from nodes.base import StrategyProxyNode

class MyProxyNode(StrategyProxyNode):
    def get_strategy_method(self) -> str:
        return "setup"  # or "execute_generation", etc.
```

Used for:
- `InitNode` → calls `strategy.setup()`
- `RouterNode` → calls `strategy.process_end_of_loop()`

### Operation Nodes

Nodes that perform actual I/O:

```python
from nodes.base import BaseAdversarialNode

class AttackNode(BaseAdversarialNode):
    def __init__(self, llm_provider, model, config=None):
        super().__init__(config)
        self.provider = llm_provider
        self.model = model
    
    async def execute(self, state, config):
        strategy = config["configurable"]["strategy"]
        
        # Delegate to strategy for attack generation
        attack_data = strategy.execute_generation(state)
        
        # Optionally use LLM if strategy provides a prompt
        if "prompt" in attack_data:
            llm_output = await self.provider.generate(
                attack_data["prompt"],
                model=self.model
            )
            # Wrap and return
        
        return attack_data
```

## Default Nodes

`default_nodes.py` provides testing implementations:

- **DefaultInitNode** - Calls strategy.setup()
- **DefaultAttackNode** - Calls strategy.execute_generation()
- **DefaultDefenceNode** - Returns mock HTTP responses
- **DefaultEvalNode** - Returns random scores
- **DefaultRouterNode** - Calls strategy.process_end_of_loop()

**Usage:**
```python
from nodes.default_nodes import create_default_nodes

nodes = create_default_nodes()
# Returns dict: {"init": ..., "attack": ..., "defence": ..., "eval": ..., "router": ...}
```

## Creating Custom Nodes

### LLM-Based Attack Node

```python
from nodes.base import BaseAdversarialNode
from engine.domain_models import create_simple_attack
from engine.state_schema import update_turn_data

class LLMAttackNode(BaseAdversarialNode):
    def __init__(self, llm_provider, model="gpt-4", config=None):
        super().__init__(config)
        self.provider = llm_provider
        self.model = model
    
    async def execute(self, state, config):
        strategy = config["configurable"]["strategy"]
        
        # Strategy generates the attack
        result = strategy.execute_generation(state)
        
        # If strategy wants LLM assistance, it puts a prompt in metadata
        attack = result["current_turn"]["attack"]
        if "llm_prompt" in attack.metadata:
            llm_output = await self.provider.generate(
                attack.metadata["llm_prompt"],
                model=self.model,
                temperature=0.9
            )
            
            # Replace attack data with LLM output
            attack = create_simple_attack(
                llm_output,
                metadata=attack.metadata
            )
            result["current_turn"]["attack"] = attack
        
        return result
```

### HTTP Defence Node

```python
import httpx
from nodes.base import BaseAdversarialNode
from engine.domain_models import create_defence_response
from engine.state_schema import update_turn_data

class HTTPDefenceNode(BaseAdversarialNode):
    def __init__(self, base_url, api_key, config=None):
        super().__init__(config)
        self.base_url = base_url
        self.api_key = api_key
        self.client = httpx.AsyncClient()
    
    async def execute(self, state, config):
        current_turn = state["current_turn"]
        attack = current_turn["attack"]
        
        # Make HTTP request
        response = await self.client.post(
            f"{self.base_url}/chat",
            json={"message": attack.to_string()},
            headers={"Authorization": f"Bearer {self.api_key}"}
        )
        
        # Wrap response
        defence = create_defence_response(
            text=response.text,
            status_code=response.status_code,
            headers=dict(response.headers),
            latency_ms=(response.elapsed.total_seconds() * 1000)
        )
        
        # Update turn
        updated_turn = update_turn_data(
            current_turn,
            defence=defence,
            node_name="defence"
        )
        
        return {"current_turn": updated_turn}
    
    async def cleanup(self):
        await self.client.aclose()
```

## Node Rules

**DO:**
- ✅ Inject all dependencies via `__init__`
- ✅ Keep `execute()` async
- ✅ Return only mutated state portions
- ✅ Handle errors gracefully

**DON'T:**
- ❌ Use global variables
- ❌ Make routing decisions (read/write `routing_signal`)
- ❌ Mutate input `state` directly
- ❌ Block on synchronous I/O

## Dependency Injection Pattern

```python
# ❌ BAD - Global state
api_key = os.getenv("API_KEY")

class MyNode(BaseAdversarialNode):
    async def execute(self, state, config):
        response = requests.post(url, headers={"Authorization": api_key})
        # Uses global variable!

# ✅ GOOD - Dependency injection
class MyNode(BaseAdversarialNode):
    def __init__(self, api_key, config=None):
        super().__init__(config)
        self.api_key = api_key  # Injected dependency
    
    async def execute(self, state, config):
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers={"Authorization": self.api_key}
            )
```

## Wiring Nodes into Graph

```python
from engine.graph_builder import UniversalGraphBuilder
from providers.openai_provider import OpenAIProvider

# Create providers
llm_provider = OpenAIProvider(api_key="sk-...")

# Create nodes with injected dependencies
init_node = DefaultInitNode()
attack_node = LLMAttackNode(llm_provider, model="gpt-4")
defence_node = HTTPDefenceNode("https://target.com", api_key="...")
eval_node = LLMEvalNode(llm_provider, model="gpt-3.5-turbo")
router_node = DefaultRouterNode()

# Build graph
builder = UniversalGraphBuilder(
    init_node=init_node,
    attack_node=attack_node,
    defence_node=defence_node,
    eval_node=eval_node,
    router_node=router_node
)

graph = builder.compile()
```

## See Also

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [../strategies/README.md](../strategies/README.md) - Strategy development
- [../providers/README.md](../providers/README.md) - LLM providers