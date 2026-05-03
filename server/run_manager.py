
"""
Run Manager - Final Integrated Version without Manual Input Handling
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

from engine.workflow_engine import WorkflowEngine
from engine.graph_builder import build_default_graph
from engine.registry import get_node_registry, get_strategy_registry
from middlewares.logging_middleware import LoggingMiddleware
from middlewares.database_middleware_v2 import DatabaseMiddlewareV2
# Removed WebSocketMiddlewareV2 import as it was associated with manual input events
# from middlewares.websocket_middleware_v2 import WebSocketMiddlewareV2
from server.database.operations import get_db_ops
from server.database.connection import get_db
# Removed import related to manual operations
# from server.database.manual_operations import get_manual_ops 
from server.config.models import GraphConfig
from engine.state_schema import create_initial_state, SystemState, RoutingSignals

# Removed imports related to WebSocket events for manual input
# from server.websocket_event_manager import (
#     emit_manual_wait_events,
#     emit_resumption_event,
#     emit_turn_update_events
# )


class RunStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    # Removed PAUSED, WAITING_INPUT statuses as they are for manual control
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class RunExecutor:
    """Executes a single run with dynamic graph and automatic execution"""
    
    def __init__(self, run_id: str, graph_config: GraphConfig):
        self.run_id = run_id
        self.graph_config = graph_config
        
        # Build graph based on config (ensuring it's automatic)
        self.graph = build_default_graph()
        
        strategy_registry = get_strategy_registry()
        self.strategy = strategy_registry.get(
            graph_config.strategy_config.strategy_name,
            config=graph_config.strategy_config.strategy_params
        )
        
        # Setup middlewares dynamically based on config. For now, using a base set.
        self.middlewares = self._setup_middlewares(graph_config)
        
        self.engine = WorkflowEngine(
            compiled_graph=self.graph,
            middlewares=self.middlewares
        )
        
        self.task: Optional[asyncio.Task] = None
        self.status = RunStatus.IDLE
        self._stop_requested = False
        self._current_state: Optional[SystemState] = None

    def _setup_middlewares(self, config: GraphConfig) -> List[BaseMiddleware]:
        """Determine which middlewares to load based on the execution mode."""
        
        # Base middlewares that apply to ALL modes
        middlewares = [
            LoggingMiddleware({"verbose": False}),
            DatabaseMiddlewareV2()
        ]
        
        # Dynamic middleware loading based on config.graph_type if needed in future.
        # Currently, all manual-specific middleware (like WebSockets for streaming) are removed.
        # if config.graph_type == "manual":
        #     pass # No manual-specific middlewares needed anymore
        
        return middlewares

    async def _initialize_dependencies(self):
        """Initialize database operations."""
        db = get_db()
        if not db:
            raise RuntimeError("Database not connected")
        # Removed manual_ops initialization

    async def start(self, initial_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Start run execution"""
        if self.status == RunStatus.RUNNING:
            raise RuntimeError(f"Run {self.run_id} is already running")
        
        self.status = RunStatus.RUNNING
        await self._update_db_status(RunStatus.RUNNING)
        
        try:
            # Delegate entire execution to the WorkflowEngine
            final_state = await self._run_with_controls(initial_payload)
            
            # Update status after successful completion (if not stopped/failed)
            if self.status == RunStatus.RUNNING:
                self.status = RunStatus.COMPLETED
            await self._update_db_status(self.status)
            return final_state
            
        except asyncio.CancelledError:
            # Task was cancelled (e.g., by stop() method)
            self.status = RunStatus.STOPPED
            await self._update_db_status(RunStatus.STOPPED)
            raise
        except Exception as e:
            # Catch any other exceptions during execution
            self.status = RunStatus.FAILED
            await self._update_db_status(RunStatus.FAILED, error=str(e))
            raise
    
    async def _run_with_controls(self, initial_payload: Dict[str, Any]) -> SystemState:
        """Run execution delegating entirely to the WorkflowEngine"""
        
        await self._initialize_dependencies() # Ensure DB is ready
        
        # Delegate entirely to the engine. 
        # The engine handles the stream, state merging, middlewares, and initial state creation.
        final_state = await self.engine.execute_run(
            initial_payload=initial_payload,
            strategy=self.strategy,
            run_id=self.run_id,
            config=self.graph_config.dict() # Pass graph config for runtime context
        )
        
        self._current_state = final_state
        return final_state

    async def stop(self):
        """Stop execution"""
        self._stop_requested = True
        
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        # Status update will be handled by the exception catching in start()
        # Ensure status is set to STOPPED if task cancellation doesn't complete the cycle.
        if self.status != RunStatus.STOPPED:
            self.status = RunStatus.STOPPED
            await self._update_db_status(RunStatus.STOPPED)
    
    # Removed manual input methods and related logic:
    # async def provide_manual_input(self, input_data: Dict[str, Any]): ...
    # async def _handle_manual_wait(self):
    # async def _handle_general_pause(self):
    # async def pause(self):
    # async def resume(self):
    
    def _extract_updates(self, step_data: Dict[str, Any]) -> Dict[str, Any]:
        """This method is now part of WorkflowEngine and should not be here."""
        raise NotImplementedError("This method is deprecated. Use WorkflowEngine's extraction.")

    async def _trigger_middleware(self, method: str, *args):
        """This method is now part of WorkflowEngine and should not be here."""
        raise NotImplementedError("This method is deprecated. Use WorkflowEngine's middleware triggering.")

    async def _update_db_status(self, status: RunStatus, error: str = None):
        """Update run status in database"""
        db = get_db()
        if not db:
            return
        
        db_ops = get_db_ops(db)
        updates = {"status": status.value}
        
        if error:
            updates["error"] = error
        
        # Set completed_at timestamp only on final states
        if status in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.STOPPED]:
            updates["completed_at"] = datetime.utcnow().isoformat()
        
        # Reset manual flags if they existed, though they are now removed from the executor state.
        # This ensures database consistency if older states were somehow present.
        updates["manual_wait_active"] = False
        updates["manual_input_required"] = None
        updates["routing_signal"] = RoutingSignals.END # Ensure graph stops on final states

        await db_ops.update_run(self.run_id, updates)


class RunManager:
    """Manages all active runs"""
    
    def __init__(self): 
        self.executors: Dict[str, RunExecutor] = {}
        self._lock = asyncio.Lock()
    
    async def create_run(self, run_id: str, run_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create run in database"""
        db = get_db()
        if not db:
            raise RuntimeError("Database not connected")
        
        db_ops = get_db_ops(db)
        # Ensure status is set to idle upon creation
        await db_ops.create_run({**run_data, "run_id": run_id, "status": RunStatus.IDLE.value})
        
        return await db_ops.get_run(run_id)
    
    async def start_run(self, run_id: str, input_payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """Start run execution, accepting an optional dynamic payload"""
        async with self._lock:
            if run_id in self.executors and self.executors[run_id].status == RunStatus.RUNNING:
                raise RuntimeError(f"Run {run_id} is already running")
            
            db = get_db()
            if not db:
                raise RuntimeError("Database not connected")
            
            db_ops = get_db_ops(db)
            run_data = await db_ops.get_run(run_id)
            
            if not run_data:
                raise ValueError(f"Run {run_id} not found in database")
            
            current_status = run_data.get("status", RunStatus.IDLE.value)
            # Only allow starting from IDLE or STOPPED states
            if current_status not in [RunStatus.IDLE.value, RunStatus.STOPPED.value]:
                raise RuntimeError(f"Cannot start run {run_id} in status: {current_status}")

            try:
                graph_config = GraphConfig(**run_data["graph_config"])
            except Exception as e:
                raise ValueError(f"Failed to parse graph_config for run {run_id}: {e}")

            executor = RunExecutor(
                run_id=run_id,
                graph_config=graph_config
            )
            self.executors[run_id] = executor
            
            # Unified Payload Handling: Use provided input_payload, fallback to DB description.
            initial_payload = input_payload if input_payload else {
                "description": run_data.get("description", "")
            }

            # Start the executor task
            executor.task = asyncio.create_task(executor.start(initial_payload))
            
            return {
                "run_id": run_id,
                "status": executor.status.value,
                "message": "Run started successfully"
            }
    
    # Removed manual input and control methods:
    # async def provide_manual_input(self, run_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]: ...
    # async def pause_run(self, run_id: str) -> Dict[str, Any]: ...
    # async def resume_run(self, run_id: str) -> Dict[str, Any]: ...
    
    async def stop_run(self, run_id: str) -> Dict[str, Any]:
        executor = self.executors.get(run_id)
        if not executor:
            raise ValueError(f"Run {run_id} not active or executor not found")
        
        await executor.stop()
        # Status update is handled within executor.stop()
        return {"run_id": run_id, "status": executor.status.value}
    
    def get_run_status(self, run_id: str) -> Dict[str, Any]:
        executor = self.executors.get(run_id)
        
        if executor:
            return {
                "run_id": run_id,
                "status": executor.status.value,
                # Only RUNNING is considered active now
                "is_active": executor.status == RunStatus.RUNNING
            }
        
        # If executor not found, check DB for status
        db = get_db()
        if db:
            db_ops = get_db_ops(db)
            run = db_ops.get_run(run_id)
            if run:
                return {
                    "run_id": run_id,
                    "status": run.get("status", "unknown"),
                    "is_active": False # Not active if executor isn't managing it
                }
        
        raise ValueError(f"Run {run_id} not found")
    
    def get_active_runs(self) -> List[str]:
        return [
            run_id for run_id, executor in self.executors.items()
            # Only RUNNING executors are considered active
            if executor.status == RunStatus.RUNNING
        ]


_run_manager: Optional[RunManager] = None

def get_run_manager() -> RunManager:
    global _run_manager
    if _run_manager is None:
        _run_manager = RunManager()
    return _run_manager
