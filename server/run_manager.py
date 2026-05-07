"""
Run Manager - Refactored for Middleware Factory Pattern and Correct Config Flow
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

from engine.workflow_engine import WorkflowEngine
from engine.graph_builder import build_default_graph, ConfigurableGraphBuilder
from engine.registry import get_node_registry, get_strategy_registry, get_provider_registry
from middlewares.base import BaseMiddleware
from middlewares.logging_middleware import LoggingMiddleware
from middlewares.automatic_database_middleware import AutomaticDatabaseMiddleware
from middlewares.manual_database_middleware import ManualDatabaseMiddleware
from engine.debug_utils import debug, err, tracer, step, checkpoint, warn
from middlewares.automatic_ws_middleware import AutomaticWSMiddleware
from middlewares.manual_ws_middleware import ManualWSMiddleware

from server.config.models import GraphConfig
from engine.state_schema import create_initial_state, SystemState, RoutingSignals
from server.database.connection import get_db
from server.database.models_v2 import RunModel
from server.database.operations import get_db_ops
from server.websocket.socketio_manager import SocketIOManager, get_socketio_manager # Import from server.database.models_v2 import RunModel # Import RunModel

class RunStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class RunExecutor:
    """Executes a single run with dynamic graph and automatic execution"""
    
    def __init__(self, run_id: str, graph_config: GraphConfig):
        self.run_id = run_id
        self.graph_config = graph_config
        tracer("RunExecutor initialized", run_id=run_id, graph_type=graph_config.graph_type)
        
        builder = ConfigurableGraphBuilder(self.graph_config)
        self.graph = builder.compile()
        
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
        step("Setting up middlewares", graph_type=config.graph_type)
        
        middlewares = [LoggingMiddleware()]
        
        if config.graph_type == "manual":
            middlewares.extend([
                ManualDatabaseMiddleware(),
                ManualWSMiddleware(get_socketio_manager()) # Use global instance
            ])
            step("Loaded manual middlewares")
        else:  # automatic or default
            middlewares.extend([
                AutomaticDatabaseMiddleware(),
                AutomaticWSMiddleware(get_socketio_manager()) # Use global instance
            ])
            step("Loaded automatic middlewares")
            
        return middlewares

    async def _initialize_dependencies(self):
        """Initialize database dependencies."""
        db = get_db()
        if db is None:
            raise RuntimeError("Database not connected")
        debug("Dependencies initialized", run_id=self.run_id)

    async def start(self, payload: Dict[str, Any]) -> SystemState:
        """Start run execution"""
        tracer("Starting run execution", run_id=self.run_id)
        
        if self.status == RunStatus.RUNNING:
            raise RuntimeError(f"Run {self.run_id} is already running")
        
        self.status = RunStatus.RUNNING
        await self._update_db_status(RunStatus.RUNNING)
        step("Run started")
        
        try:
            final_state = await self._run_with_controls(payload)
            
            if self.status == RunStatus.RUNNING:
                self.status = RunStatus.COMPLETED
            await self._update_db_status(self.status)
            checkpoint("Run completed successfully", run_id=self.run_id)
            return final_state
            
        except asyncio.CancelledError:
            self.status = RunStatus.STOPPED
            await self._update_db_status(RunStatus.STOPPED)
            warn("Run stopped by user")
            raise
        except Exception as e:
            self.status = RunStatus.FAILED
            await self._update_db_status(RunStatus.FAILED, error=str(e))
            err(f"Run failed: {e}")
            raise
    
    async def _run_with_controls(self, payload: Dict[str, Any]) -> SystemState:
        """Run execution delegating entirely to the WorkflowEngine"""
        
        await self._initialize_dependencies() 

        # Pass the full graph_config to the engine for initial state creation
        step("Executing workflow engine", run_id=self.run_id)
        final_state = await self.engine.execute_run(
            payload=payload,
            run_id=self.run_id,
            config=self.graph_config # Pass the structural graph_config
        )
        
        self._current_state = final_state
        return final_state

    async def stop(self):
        """Stop execution"""
        tracer("Stopping run", run_id=self.run_id)
        self._stop_requested = True
        
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        if self.status != RunStatus.STOPPED:
            self.status = RunStatus.STOPPED
            await self._update_db_status(RunStatus.STOPPED)
        step("Run stopped", run_id=self.run_id)
    
    def _extract_updates(self, step_data: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError("This method is deprecated. Use WorkflowEngine's extraction.")

    async def _trigger_middleware(self, method: str, *args):
        raise NotImplementedError("This method is deprecated. Use WorkflowEngine's middleware triggering.")

    async def _update_db_status(self, status: RunStatus, error: str = None):
        """Update run status in database"""
        debug("Updating run status in DB", run_id=self.run_id, status=status.value)
        
        db = get_db()
        if db is None:
            return
        
        db_ops = get_db_ops(db)
        updates = {"status": status.value}
        
        if error:
            updates["error"] = error
        
        if status in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.STOPPED]:
            updates["completed_at"] = datetime.utcnow().isoformat()
        
        updates["manual_wait_active"] = False
        updates["manual_input_required"] = None
        updates["routing_signal"] = RoutingSignals.END 

        await db_ops.update_run(self.run_id, updates)
        debug("Run status updated", run_id=self.run_id, status=status.value)


class RunManager:
    """Manages all active runs"""
    
    def __init__(self): 
        self.executors: Dict[str, RunExecutor] = {}
        self._lock = asyncio.Lock()
        tracer("RunManager initialized")
    
    async def create_run(self, run_id: str, run_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create run in database"""
        tracer("Creating run", run_id=run_id)
        
        db = get_db()
        if db is None:
            raise RuntimeError("Database not connected")
        
        db_ops = get_db_ops(db)
        await db_ops.create_run({**run_data, "run_id": run_id, "status": RunStatus.IDLE.value})
        step("Run created in database", run_id=run_id)
        
        return await db_ops.get_run(run_id)
    
    async def start_run(self, run_id: str, input_payload: Dict[str, Any] = None) -> Dict[str, Any]:
        """Start run execution, accepting an optional dynamic payload"""
        tracer("Starting run", run_id=run_id)
        
        async with self._lock:
            if run_id in self.executors and self.executors[run_id].status == RunStatus.RUNNING:
                raise RuntimeError(f"Run {run_id} is already running")
            
            db = get_db()
            if db is None:
                raise RuntimeError("Database not connected")
            
            db_ops = get_db_ops(db)
            run_data = await db_ops.get_run(run_id)
            
            if not run_data:
                raise ValueError(f"Run {run_id} not found in database")
            
            # Robustly determine current status
            current_status_str: str
            if isinstance(run_data, RunModel): # Check if it's a Pydantic model instance
                current_status_str = run_data.status
            elif isinstance(run_data, dict): # Check if it's a dictionary
                current_status_str = run_data.get("status", RunStatus.IDLE.value) # Use .get for dicts
            else:
                # Fallback for unexpected types, though less likely
                raise TypeError(f"Unexpected type for run_data: {type(run_data)}")

            if current_status_str not in [RunStatus.IDLE.value, RunStatus.STOPPED.value]:
                raise RuntimeError(f"Cannot start run {run_id} in status: {current_status_str}")

            try:
                graph_config = run_data.graph_config
            except Exception as e:
                raise ValueError(f"Failed to parse graph_config for run {run_id}: {e}")

            # Pass graph_config to executor. The executor will build the graph with strategy.
            executor = RunExecutor(
                run_id=run_id,
                graph_config=graph_config
            )
            self.executors[run_id] = executor
            
            payload = input_payload if input_payload else {
                "description": run_data.get("description", "")
            }

            executor.task = asyncio.create_task(executor.start(payload))
            step("Run execution started", run_id=run_id)
            
            return {
                "run_id": run_id,
                "status": executor.status.value,
                "message": "Run started successfully"
            }
    
    async def stop_run(self, run_id: str) -> Dict[str, Any]:
        tracer("Stopping run", run_id=run_id)
        
        executor = self.executors.get(run_id)
        if not executor:
            raise ValueError(f"Run {run_id} not active or executor not found")
        
        await executor.stop()
        step("Run stopped", run_id=run_id)
        return {"run_id": run_id, "status": executor.status.value}
    
    def get_run_status(self, run_id: str) -> Dict[str, Any]:
        debug("Getting run status", run_id=run_id)
        
        executor = self.executors.get(run_id)
        
        if executor:
            return {
                "run_id": run_id,
                "status": executor.status.value,
                "is_active": executor.status == RunStatus.RUNNING
            }
        
        db = get_db()
        if db:
            db_ops = get_db_ops(db)
            run = db_ops.get_run(run_id)
            if run:
                # Robust status retrieval for get_run_status
                current_status_str: str
                if isinstance(run, RunModel):
                    current_status_str = run.status
                elif isinstance(run, dict):
                    current_status_str = run.get("status", "unknown")
                else:
                    current_status_str = "unknown" # Fallback
                return {
                    "run_id": run_id,
                    "status": current_status_str, 
                    "is_active": False 
                }
        
        raise ValueError(f"Run {run_id} not found")
    
    def get_active_runs(self) -> List[str]:
        debug("Getting active runs")
        return [
            run_id for run_id, executor in self.executors.items()
            if executor.status == RunStatus.RUNNING
        ]


_run_manager: Optional[RunManager] = None

def get_run_manager() -> RunManager:
    global _run_manager
    if _run_manager is None:
        _run_manager = RunManager()
    return _run_manager
