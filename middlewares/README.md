# Middlewares Module

Observer pattern implementation for handling infrastructure side-effects.

## Overview

Middlewares observe execution flow without mutating state. They handle:
- Database persistence
- WebSocket broadcasting
- Logging and metrics
- External notifications

## Base Interface

```python
from middlewares.base import BaseMiddleware

class MyMiddleware(BaseMiddleware):
    async def before_run(self, initial_state, config, run_id):
        """Called once before graph starts"""
        pass
    
    async def after_step(self, step_data, run_id):
        """Called after every node execution"""
        # Self-filtering pattern
        if "target_node" not in step_data:
            return  # Not interested
        
        # Process relevant data
        await self.handle_step(step_data)
    
    async def after_run(self, final_state, run_id):
        """Called once when graph completes"""
        pass
    
    async def on_error(self, error, run_id, step_data=None):
        """Called when errors occur"""
        pass
```

## Self-Filtering Pattern

Middlewares receive ALL step events. Use self-filtering to process only relevant ones:

```python
class AttackLoggerMiddleware(BaseMiddleware):
    async def after_step(self, step_data, run_id):
        # Only care about attack node
        if "attack_node" not in step_data:
            return
        
        attack_data = step_data["attack_node"]
        attack = attack_data["current_turn"]["attack"]
        
        print(f"Attack generated: {attack.to_string()}")
```

## Logging Middleware

`logging_middleware.py` provides console logging:

```python
from middlewares.logging_middleware import LoggingMiddleware

middleware = LoggingMiddleware({
    "verbose": True,      # Include detailed output
    "timestamps": True    # Add timestamps to logs
})
```

**Output:**
```
[12:34:56.789] ============================================================
[12:34:56.790] 🚀 RUN STARTED: run_abc123
[12:34:56.791]    Strategy: DefaultStrategy
[12:34:56.792]    Intent: test jailbreak
[12:34:56.793] ============================================================

[12:34:56.850] 📍 NODE: attack
[12:34:56.851]    ⚔️  Attack: Test attack: Ignore previous instructions...
[12:34:56.900] 📍 NODE: defence
[12:34:56.901]    🛡️  Defence: 🚫 BLOCKED
[12:34:56.950] 📍 NODE: eval
[12:34:56.951]    📊 Eval: ✗ Failure | Score: 0.32 | Category: blocked_appropriately
```

## Creating Custom Middlewares

### Database Persistence Middleware

```python
from middlewares.base import BaseMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

class DatabaseMiddleware(BaseMiddleware):
    def __init__(self, mongo_url, db_name="adversarial_testing"):
        super().__init__()
        self.client = AsyncIOMotorClient(mongo_url)
        self.db = self.client[db_name]
    
    async def before_run(self, initial_state, config, run_id):
        """Create run record"""
        await self.db.runs.insert_one({
            "run_id": run_id,
            "status": "running",
            "strategy": config["configurable"]["strategy"].name,
            "started_at": initial_state["start_time"],
            "intent": initial_state["payload"].get("intent")
        })
    
    async def after_step(self, step_data, run_id):
        """Save steps"""
        # Only save attack and eval nodes
        if "attack_node" not in step_data and "eval_node" not in step_data:
            return
        
        node_name = list(step_data.keys())[0]
        node_output = step_data[node_name]
        turn = node_output.get("current_turn", {})
        
        try:
            record = {
                "run_id": run_id,
                "node": node_name,
                "turn_id": turn.get("turn_id"),
                "timestamp": turn.get("timestamp")
            }
            
            # Add attack if present
            if turn.get("attack"):
                record["attack"] = turn["attack"].to_dict()
            
            # Add evaluation if present
            if turn.get("evaluation"):
                record["evaluation"] = turn["evaluation"].to_dict()
            
            await self.db.steps.insert_one(record)
            
        except Exception as e:
            # Fail-safe: log but don't crash
            print(f"DB error: {e}")
    
    async def after_run(self, final_state, run_id):
        """Mark run complete"""
        await self.db.runs.update_one(
            {"run_id": run_id},
            {"$set": {"status": "completed"}}
        )
```

### WebSocket Broadcasting Middleware

```python
from middlewares.base import BaseMiddleware
from typing import Set

class WebSocketMiddleware(BaseMiddleware):
    def __init__(self, connection_manager):
        super().__init__()
        self.manager = connection_manager
    
    async def before_run(self, initial_state, config, run_id):
        """Broadcast run start"""
        await self.manager.broadcast(run_id, {
            "type": "run_started",
            "run_id": run_id,
            "strategy": config["configurable"]["strategy"].name
        })
    
    async def after_step(self, step_data, run_id):
        """Broadcast step updates"""
        if not step_data:
            return
        
        node_name = list(step_data.keys())[0]
        node_output = step_data[node_name]
        turn = node_output.get("current_turn", {})
        
        # Format update message
        message = {
            "type": "step_update",
            "run_id": run_id,
            "node": node_name,
            "turn_id": turn.get("turn_id")
        }
        
        # Add relevant data
        if turn.get("attack"):
            message["attack"] = turn["attack"].to_dict()
        if turn.get("evaluation"):
            message["evaluation"] = turn["evaluation"].to_dict()
        
        await self.manager.broadcast(run_id, message)
    
    async def after_run(self, final_state, run_id):
        """Broadcast completion"""
        await self.manager.broadcast(run_id, {
            "type": "run_completed",
            "run_id": run_id
        })
```

### Metrics Collection Middleware

```python
from middlewares.base import BaseMiddleware
from collections import defaultdict

class MetricsMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.metrics = defaultdict(lambda: {
            "total_attempts": 0,
            "successful_attacks": 0,
            "blocked_attacks": 0,
            "avg_score": 0.0
        })
    
    async def after_step(self, step_data, run_id):
        """Collect metrics from evaluations"""
        if "eval_node" not in step_data:
            return
        
        eval_data = step_data["eval_node"]
        eval_result = eval_data["current_turn"]["evaluation"]
        
        # Update metrics
        m = self.metrics[run_id]
        m["total_attempts"] += 1
        
        if eval_result.is_success():
            m["successful_attacks"] += 1
        else:
            m["blocked_attacks"] += 1
        
        # Running average of score
        current_avg = m["avg_score"]
        n = m["total_attempts"]
        m["avg_score"] = ((current_avg * (n - 1)) + eval_result.get_score()) / n
    
    def get_metrics(self, run_id):
        """Get accumulated metrics"""
        return self.metrics[run_id]
```

## Middleware Rules

**DO:**
- ✅ Wrap operations in try/except (fail-safe)
- ✅ Use async for all I/O
- ✅ Implement self-filtering
- ✅ Log errors, don't raise

**DON'T:**
- ❌ Mutate `step_data` or `state`
- ❌ Block the execution thread
- ❌ Crash on infrastructure failures
- ❌ Assume specific node order

## Fail-Safe Pattern

```python
class SafeMiddleware(BaseMiddleware):
    async def after_step(self, step_data, run_id):
        try:
            # Your logic here
            await self.risky_operation(step_data)
        except Exception as e:
            # Log but don't crash
            print(f"Middleware error: {e}")
            # Optionally send alert
            await self.send_alert(e)
```

## Wiring Middlewares into Engine

```python
from engine.workflow_engine import WorkflowEngine
from middlewares.logging_middleware import LoggingMiddleware
from middlewares.database_middleware import DatabaseMiddleware
from middlewares.websocket_middleware import WebSocketMiddleware

# Create middlewares
logging_mw = LoggingMiddleware({"verbose": True})
db_mw = DatabaseMiddleware("mongodb://localhost:27017")
ws_mw = WebSocketMiddleware(connection_manager)

# Create engine with middlewares
engine = WorkflowEngine(
    compiled_graph=graph,
    middlewares=[logging_mw, db_mw, ws_mw]
)

# All middlewares will be called at each lifecycle hook
result = await engine.execute_run(...)
```

## Execution Order

Middlewares execute in **parallel** at each hook:

```python
# Engine triggers:
await asyncio.gather(
    logging_mw.after_step(step_data, run_id),
    db_mw.after_step(step_data, run_id),
    ws_mw.after_step(step_data, run_id),
    return_exceptions=True  # One failure doesn't crash others
)
```

## See Also

- [ARCHITECTURE.md](../ARCHITECTURE.md) - System architecture
- [../engine/README.md](../engine/README.md) - Engine components
- [../server/README.md](../server/README.md) - Backend server
