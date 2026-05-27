# Architectural Refactoring: Fixing Leaky Abstractions in Run Execution Lifecycle

## Problem Statement

The original implementation had a "God Object" anti-pattern where `RunExecutor` was handling both:
1. Infrastructure management (async tasks, crash catching)
2. Business logic (deciding what database statuses like "completed" or "idle" mean)

This caused Manual runs to get stuck or mismanaged when they reached the end of a turn, because `RunExecutor` treated Manual and Automatic runs the same way.

## Solution: Separation of Concerns

We've redistributed responsibilities across core entities to enforce clear architectural boundaries:

### 1. SystemState (LangGraph Engine)
**Role**: Pure execution state
- Has NO concept of database strings like "idle", "running", or "completed"
- Only knows about `RoutingSignals` (`CONTINUE`, `ATTACK`, `END`)
- Remains completely decoupled from persistence concerns

### 2. Middlewares (The Business Logic)
**Role**: Observers that translate engine events to database states

#### AutomaticDatabaseMiddleware
- **Happy Path**: When LangGraph reaches `__end__`, the entire test is over
- Sets database status to `COMPLETED` in `after_run` hook
- Updates: `status="completed"`, `completed_at`, `final_score`, `best_score`

#### ManualDatabaseMiddleware
- **Happy Path**: When LangGraph reaches `__end__`, only the current turn is over
- Sets database status to `IDLE` with `manual_wait_active=True` in `after_run` hook
- This makes the run ready to accept the next user prompt
- Updates: `status="idle"`, `manual_wait_active=True`, session state checkpoint

### 3. RunExecutor (The Safety Net)
**Role**: Infrastructure management ONLY

**What it does**:
- Sets status to `RUNNING` when execution starts
- Manages the `asyncio.Task` lifecycle
- Only updates database in "Sad Path" scenarios:
  - `asyncio.CancelledError` → `STOPPED`
  - `Exception` → `FAILED`

**What it doesn't do anymore**:
- ❌ No longer decides if a run should be marked `COMPLETED`
- ❌ No longer knows about the difference between Manual and Automatic runs
- ❌ No longer sets `manual_wait_active`, `routing_signal`, or other business logic fields

### 4. RunManager (The Global Lifecycle)
**Role**: Manages global registry and handles server-level anomalies

**New Method**: `cleanup_zombie_runs()`
- Called on server startup to handle runs that died during a server crash/restart
- Differentiates by `graph_type`:
  - **Automatic runs**: Mark as `FAILED` (they were interrupted mid-loop)
  - **Manual runs**: Revert to `IDLE` with `manual_wait_active=True` (they were just waiting for user input)

## Files Modified

### 1. `middlewares/automatic_database_middleware.py`
```python
async def after_run(self, state: SystemState, run_id: str) -> None:
    """
    Mark automatic run as COMPLETED in database.
    
    ARCHITECTURAL BOUNDARY:
    For automatic runs, when LangGraph reaches __end__, the entire test is over.
    This middleware is responsible for the "Happy Path" status update to COMPLETED.
    """
    # Updates status to "completed" with completed_at timestamp
```

### 2. `middlewares/manual_database_middleware.py`
```python
async def after_run(self, state: SystemState, run_id: str) -> None:
    """
    Mark manual run as IDLE and save final state.
    
    ARCHITECTURAL BOUNDARY:
    For manual runs, when LangGraph reaches __end__, it only means the current turn is over.
    This middleware is responsible for the "Happy Path" status update to IDLE with manual_wait_active=True,
    so the run is ready to accept the next user prompt.
    """
    # Updates status to "idle" with manual_wait_active=True
```

### 3. `server/run_manager.py`

#### `RunExecutor.start()` - Stripped Down
```python
async def start(self, payload: Dict[str, Any]) -> SystemState:
    """
    ARCHITECTURAL BOUNDARY - THE SAFETY NET:
    RunExecutor is responsible ONLY for infrastructure management.
    It sets status to RUNNING at the start, then only updates the database
    in the "Sad Path" (crashes and cancellations).
    
    "Happy Path" status updates are handled by middlewares.
    """
    self.status = RunStatus.RUNNING
    await self._update_db_status(RunStatus.RUNNING)
    
    try:
        # Let the engine execute - middlewares handle success state
        final_state = await self._run_with_controls(payload)
        return final_state
        
    except asyncio.CancelledError:
        # Sad Path: User cancelled
        self.status = RunStatus.STOPPED
        await self._update_db_status(RunStatus.STOPPED)
        raise
    except Exception as e:
        # Sad Path: Catastrophic crash
        self.status = RunStatus.FAILED
        await self._update_db_status(RunStatus.FAILED, error=str(e))
        raise
```

#### `RunExecutor._update_db_status()` - Infrastructure Only
```python
async def _update_db_status(self, status: RunStatus, error: str = None):
    """
    Update run status in database (INFRASTRUCTURE ONLY).
    
    ARCHITECTURAL BOUNDARY:
    This method is ONLY called for infrastructure states:
    - RUNNING: Initial state when execution starts
    - STOPPED: User cancellation (asyncio.CancelledError)
    - FAILED: Catastrophic Python crash (Exception)
    
    Business logic states (COMPLETED, IDLE) are handled by middlewares.
    """
    # Only handles RUNNING, STOPPED, FAILED
    # No longer sets routing_signal, manual_wait_active for all states
```

#### `RunManager.cleanup_zombie_runs()` - New Method
```python
async def cleanup_zombie_runs(self) -> Dict[str, Any]:
    """
    Clean up "zombie" runs stuck in RUNNING during a server restart.
    
    ARCHITECTURAL BOUNDARY - GLOBAL LIFECYCLE:
    Called on server startup. Differentiates by graph_type:
    - Automatic runs: Mark as FAILED (interrupted mid-loop)
    - Manual runs: Revert to IDLE (just waiting for user)
    """
    # Finds all runs with status="running"
    # Checks graph_config.graph_type
    # Routes to appropriate recovery path
```

### 4. `server/main.py`
```python
# In lifespan startup:
if db is not None:
    try:
        run_manager = get_run_manager()
        cleanup_result = await run_manager.cleanup_zombie_runs()
        if cleanup_result["cleaned"] > 0:
            print(f"[OK] Cleaned up {cleanup_result['cleaned']} zombie run(s)")
        else:
            print("[OK] No zombie runs found")
    except Exception as e:
        print(f"[WARN] Zombie run cleanup failed: {e}")
```

## Execution Flow Comparison

### Before (God Object Anti-pattern)
```
User starts run
    ↓
RunExecutor.start()
    ↓
[Sets RUNNING in DB]
    ↓
WorkflowEngine.execute()
    ↓
Middlewares.after_run() [tries to update status but RunExecutor overrides]
    ↓
RunExecutor.start() [decides COMPLETED vs IDLE - treats all runs the same]
    ↓
[Manual runs get stuck because they're marked COMPLETED instead of IDLE]
```

### After (Separated Concerns)
```
User starts run
    ↓
RunExecutor.start()
    ↓
[Sets RUNNING in DB - Infrastructure]
    ↓
WorkflowEngine.execute()
    ↓
Middlewares.after_run() [Happy Path - Business Logic]
    ├─ Automatic → Sets COMPLETED
    └─ Manual → Sets IDLE + manual_wait_active=True
    ↓
RunExecutor catches exceptions only [Sad Path - Infrastructure]
    ├─ CancelledError → STOPPED
    └─ Exception → FAILED
```

## Benefits

1. **Clear Separation of Concerns**: Each component has a single, well-defined responsibility
2. **No More Manual Run Stuck Issues**: Manual runs properly return to IDLE after each turn
3. **Resilient to Server Restarts**: Zombie run cleanup intelligently recovers based on run type
4. **Type-Safe**: SystemState remains pure, no database concepts leak into the engine
5. **Testable**: Each component can be tested in isolation

## Testing Recommendations

### Test Case 1: Automatic Run Happy Path
```python
1. Create automatic run
2. Execute to completion
3. Verify: status="completed", completed_at is set
4. Verify: Middleware handled the status update, not RunExecutor
```

### Test Case 2: Manual Run Happy Path
```python
1. Create manual session
2. Submit first turn
3. Wait for completion
4. Verify: status="idle", manual_wait_active=True
5. Submit second turn
6. Verify: Run accepts new input without being stuck
```

### Test Case 3: Run Cancellation (Sad Path)
```python
1. Start any run
2. Cancel via API
3. Verify: status="stopped", completed_at is set
4. Verify: RunExecutor handled this, not middleware
```

### Test Case 4: Run Crash (Sad Path)
```python
1. Start run with node that raises exception
2. Wait for crash
3. Verify: status="failed", error message is captured
4. Verify: RunExecutor handled this, not middleware
```

### Test Case 5: Zombie Run Cleanup
```python
1. Insert test runs in DB with status="running"
   - One automatic run
   - One manual run
2. Restart server (call cleanup_zombie_runs)
3. Verify:
   - Automatic run → status="failed", error="Server restarted during execution"
   - Manual run → status="idle", manual_wait_active=True
```

## Migration Notes

### Backward Compatibility
- **API Contract**: No changes to request/response schemas
- **Database Schema**: No schema changes required
- **WebSocket Events**: No changes to event payloads

### What Changed
- Internal responsibility boundaries
- When and where database status updates occur
- Zombie run recovery logic

### What Didn't Change
- API endpoints and their signatures
- Database models and collections
- Node implementations
- Strategy implementations
- Frontend contracts

## Conclusion

This refactoring eliminates the God Object anti-pattern by enforcing clean architectural boundaries:
- **SystemState** stays pure (no DB concepts)
- **Middlewares** own business logic (Happy Path status transitions)
- **RunExecutor** only handles infrastructure (Sad Path failures)
- **RunManager** handles global lifecycle (zombie cleanup)

The system now correctly handles both Automatic and Manual runs with proper status transitions and resilient recovery from server restarts.
