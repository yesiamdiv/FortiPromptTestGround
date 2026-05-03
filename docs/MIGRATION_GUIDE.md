# Migration Guide - Phase 3 Upgrade

Complete guide for upgrading from Phase 2 to Phase 3 of the adversarial testing engine.

## Overview of Changes

Phase 3 introduces breaking changes in three main areas:

1. **Strategy Interface** - Now async with config parameter
2. **Database Schema** - Separate collections for attacks/defences/evaluations
3. **WebSocket Communication** - Socket.IO instead of FastAPI WebSockets

## Migration Checklist

- [ ] Update custom strategies to async
- [ ] Migrate database schema
- [ ] Update WebSocket clients to Socket.IO
- [ ] Update middleware usage
- [ ] Test all components

---

## 1. Strategy Migration

### What Changed

**Old Interface**:
```python
class MyStrategy(AttackStrategy):
    def execute_generation(self, state: Dict) -> Dict:
        # Synchronous execution
        result = generate_attack(state)
        return {"current_turn": result}
```

**New Interface**:
```python
class MyStrategy(AttackStrategy):
    async def execute_generation(self, state: Dict, config: Dict) -> Dict:
        # Async execution with config access
        provider = config.get('provider')
        result = await provider.generate(prompt)
        return {"current_turn": result}
```

### Migration Steps

#### Step 1: Add `async` keyword

```python
# Before
def execute_generation(self, state):
    ...

# After
async def execute_generation(self, state, config):
    ...
```

#### Step 2: Add `config` parameter

The config parameter provides access to:
- LLM providers
- Runtime configuration
- Additional context

```python
async def execute_generation(self, state, config):
    # Access provider if needed
    provider = config.get('provider')
    
    # Or configurable values
    custom_value = config.get('custom_key', default_value)
```

#### Step 3: Make LLM calls async

```python
# Before
response = provider.generate(prompt)

# After
response = await provider.generate(prompt)
```

### Complete Example

**Before**:
```python
class OldStrategy(AttackStrategy):
    def setup(self, payload):
        return {
            "strategy_context": {"count": 0},
            "routing_signal": RoutingSignals.CONTINUE
        }
    
    def execute_generation(self, state):
        # Generate attack
        attack = create_simple_attack("Test attack")
        turn = create_turn_data("turn_1", "attack")
        turn["attack"] = attack
        
        return {"current_turn": turn}
    
    def process_end_of_loop(self, state):
        return {
            "strategy_context": state["strategy_context"],
            "routing_signal": RoutingSignals.END
        }
```

**After**:
```python
class NewStrategy(AttackStrategy):
    def __init__(self, provider, config: Dict = None):
        super().__init__(config or {})
        self.provider = provider  # Store provider if using LLM
    
    def setup(self, payload):
        return {
            "strategy_context": {"count": 0},
            "routing_signal": RoutingSignals.CONTINUE
        }
    
    async def execute_generation(self, state, config):
        # Can now make async LLM calls
        prompt = "Generate adversarial attack"
        llm_response = await self.provider.generate(prompt)
        
        attack = create_simple_attack(llm_response)
        turn = create_turn_data("turn_1", "attack")
        turn["attack"] = attack
        
        return {"current_turn": turn}
    
    def process_end_of_loop(self, state):
        return {
            "strategy_context": state["strategy_context"],
            "routing_signal": RoutingSignals.END
        }
```

---

## 2. Database Migration

### What Changed

**Old Schema**:
```
runs: {
  run_id, status, ...
  attack_data: [...]  // Embedded
  defense_data: [...]  // Embedded
  evaluation_data: [...]  // Embedded
}
```

**New Schema**:
```
runs: {run_id, status, ...}  // Metadata only
attacks: {run_id, index, prompt, ...}  // Separate
defences: {run_id, index, response, ...}  // Separate
evaluations: {run_id, index, score, ...}  // Separate
```

### Migration Steps

#### Step 1: Backup Database

```bash
# Backup entire database
mongodump --db adversarial_testing --out backup/

# Or export specific collections
mongoexport --db adversarial_testing --collection runs --out runs_backup.json
```

#### Step 2: Run Migration Script

```bash
# Dry run (see what would be migrated)
python tools/migrate_database.py --dry-run

# Actual migration
python tools/migrate_database.py

# With custom database
python tools/migrate_database.py \
  --mongo-url mongodb://localhost:27017 \
  --database my_database

# Create indexes
python tools/migrate_database.py --create-indexes
```

#### Step 3: Verify Migration

```python
from server.database.connection import init_db
from server.database.operations import get_db_ops

# Connect
db = await init_db()
db_ops = get_db_ops(db)

# Verify a run
data = await db_ops.get_run_with_data("run_abc123")

print(f"Run: {data['run']}")
print(f"Attacks: {len(data['attacks'])}")
print(f"Defences: {len(data['defences'])}")
print(f"Evaluations: {len(data['evaluations'])}")
```

#### Step 4: Update Code to Use New Operations

**Before**:
```python
# Direct database access
attacks = await db.runs.find_one({"run_id": run_id})["attack_data"]
```

**After**:
```python
# Use operations module
from server.database.operations import get_db_ops

db_ops = get_db_ops(db)
attacks = await db_ops.get_attacks(run_id)
```

---

## 3. WebSocket Client Migration

### What Changed

**Old**: FastAPI WebSockets at `/ws/{run_id}`
**New**: Socket.IO at `/socket.io`

### Migration Steps

#### JavaScript/TypeScript

**Before** (Native WebSocket):
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/run_abc123');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data);
};
```

**After** (Socket.IO):
```javascript
import io from 'socket.io-client';

const socket = io('http://localhost:8000', {
  path: '/socket.io'
});

socket.emit('join_run_room', {run_id: 'run_abc123'});

socket.on('attack_generated', (data) => {
  console.log('Attack:', data);
});
```

#### Python

**Before**:
```python
import websockets

async with websockets.connect('ws://localhost:8000/ws/run_abc123') as ws:
    async for message in ws:
        data = json.loads(message)
        print(data)
```

**After**:
```python
import socketio

sio = socketio.AsyncClient()

@sio.event
async def attack_generated(data):
    print('Attack:', data)

await sio.connect('http://localhost:8000', socketio_path='/socket.io')
await sio.emit('join_run_room', {'run_id': 'run_abc123'})
await sio.wait()
```

### NPM Package Update

```bash
# Remove old packages (if any)
npm uninstall ws

# Install Socket.IO client
npm install socket.io-client
```

### Python Package Update

```bash
pip uninstall websockets  # If using pure websockets
pip install python-socketio
```

---

## 4. Middleware Updates

### What Changed

Middlewares now use dedicated operations modules:
- Database operations in `server/database/operations.py`
- WebSocket operations in `server/websocket/operations.py`

### Update Custom Middlewares

**Before** (Direct database access):
```python
class MyMiddleware(BaseMiddleware):
    async def after_step(self, step_data, run_id):
        # Direct DB access
        db = get_db()
        await db.my_collection.insert_one(data)
```

**After** (Use operations):
```python
class MyMiddleware(BaseMiddleware):
    async def after_step(self, step_data, run_id):
        # Use operations module
        from server.database.operations import get_db_ops
        
        db = get_db()
        db_ops = get_db_ops(db)
        await db_ops.save_attack(run_id, ...)
```

---

## 5. Testing After Migration

### Test Strategy Execution

```python
import asyncio
from strategies.default_strategy import DefaultStrategy
from engine.workflow_engine import create_default_engine

async def test():
    engine = create_default_engine()
    strategy = DefaultStrategy({"max_attempts": 2})
    
    result = await engine.execute_run(
        payload={"intent": "Test"},
        strategy=strategy
    )
    
    assert result is not None
    print("✅ Strategy test passed")

asyncio.run(test())
```

### Test Database Operations

```python
from server.database.connection import init_db
from server.database.operations import get_db_ops

async def test_db():
    db = await init_db()
    db_ops = get_db_ops(db)
    
    # Test getting run with data
    data = await db_ops.get_run_with_data("test_run_id")
    print(f"✅ Database test passed: {len(data['attacks'])} attacks")

asyncio.run(test_db())
```

### Test Socket.IO Connection

```javascript
const io = require('socket.io-client');

const socket = io('http://localhost:8000', {
  path: '/socket.io'
});

socket.on('connect', () => {
  console.log('✅ Socket.IO connection successful');
  socket.disconnect();
});
```

---

## 6. Rollback Plan

If migration fails, you can rollback:

### Restore Database

```bash
# Restore from backup
mongorestore --db adversarial_testing backup/adversarial_testing/

# Or import specific collections
mongoimport --db adversarial_testing --collection runs runs_backup.json
```

### Revert Code

```bash
git checkout <previous-version-tag>
```

### Keep Both Schemas

You can run both schemas simultaneously:
- Old runs stay in old format
- New runs use new format
- Migration script is non-destructive

---

## 7. Common Issues

### "Strategy not async" Error

**Error**: `TypeError: object dict can't be used in 'await' expression`

**Solution**: Add `async` to strategy methods and `await` LLM calls

### Database Connection Issues

**Error**: `Database not connected`

**Solution**: 
```python
# Ensure database is initialized
await init_db("mongodb://localhost:27017", "adversarial_testing")
```

### Socket.IO Connection Refused

**Error**: `Connection refused to /socket.io`

**Solution**:
- Verify server is running
- Check Socket.IO is mounted: `app.mount("/socket.io", socket_app)`
- Correct client path: `{path: '/socket.io'}`

---

## 8. Deprecation Notices

### Deprecated (Still Works)

- Old `LLMAttackNode` - Use `StrategyDrivenAttackNode`
- Direct database access - Use `operations.py`
- FastAPI WebSocket endpoint `/ws/{run_id}` - Use Socket.IO

### Will Be Removed

- Old database schema support (after v2.0)
- Direct middleware database access (after v2.0)

---

## Summary

### Minimum Required Changes

1. ✅ Update strategies: Add `async` and `config` parameter
2. ✅ Run database migration script
3. ✅ Update WebSocket clients to Socket.IO
4. ✅ Test everything

### Optional Improvements

- Use new `IterativeImprovementStrategy`
- Implement `EnsembleDefenceNode`
- Use `ServerEvalNode` for external evaluation
- Optimize prompts with `weaponize_prompts.py`

### Support

- Documentation: `docs/` folder
- Examples: `tests/test_*.py`
- Issues: Create GitHub issue with "migration" label

---

**Estimated Migration Time**: 1-2 hours for typical installation

**Difficulty**: Moderate (mostly mechanical changes)

**Risk**: Low (migration is non-destructive, old data preserved)
