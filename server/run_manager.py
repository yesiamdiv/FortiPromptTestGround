
"""
Run Manager - Final Integrated Version without Manual Input Handling"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

from engine.workflow_engine import WorkflowEngine
from engine.graph_builder import build_default_graph
from engine.registry import get_node_registry, get_strategy_registry
from middlewares.base import BaseMiddleware
from middlewares.logging_middleware import LoggingMiddleware
from middlewares.database_middleware_v2 import DatabaseMiddlewareV2
from server.config.models import GraphConfig
from engine.state_schema import create_initial_state, SystemState, RoutingSignals
from server.database.connection import get_db
from server.database.operations import get_db_ops


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
        
        # Build graph based on config (ensuring it's automatic)
        self.graph = build_default_graph()
        
        # REMOVED: Strategy retrieval is now handled within ConfigurableGraphBuilder
        # and passed to the router node during graph construction.
        # strategy_registry = get_strategy_registry()
        # self.strategy = strategy_registry.get(
        #     graph_config.strategy_config.strategy_name,
        #     config=graph_config.strategy_config.strategy_params
        # )
        
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
        
        middlewares = [
            LoggingMiddleware({"verbose": False}),
            DatabaseMiddlewareV2()
        ]
        
        return middlewares

    async def _initialize_dependencies(self):
        """Initialize database operations."""
        db = get_db()
        if not db:
            raise RuntimeError("Database not connected")

    async def start(self, initial_payload: Dict[str, Any]) -> SystemState:
        """Start run execution"""
        if self.status == RunStatus.RUNNING:
            raise RuntimeError(f"Run {self.run_id} is already running")
        
        self.status = RunStatus.RUNNING
        await self._update_db_status(RunStatus.RUNNING)
        
        try:
            final_state = await self._run_with_controls(initial_payload)
            
            if self.status == RunStatus.RUNNING:
                self.status = RunStatus.COMPLETED
            await self._update_db_status(self.status)
            return final_state
            
        except asyncio.CancelledError:
            self.status = RunStatus.STOPPED
            await self._update_db_status(RunStatus.STOPPED)
            raise
        except Exception as e:
            self.status = RunStatus.FAILED
            await self._update_db_status(RunStatus.FAILED, error=str(e))
            raise
    
    async def _run_with_controls(self, initial_payload: Dict[str, Any]) -> SystemState:
        """Run execution delegating entirely to the WorkflowEngine"""
        
        await self._initialize_dependencies() 
        
        # Delegate entirely to the engine. 
        # The engine handles the stream, state merging, middlewares, and initial state creation.
        # Pass graph_config.dict() for runtime context. Strategy is embedded in graph config.
        final_state = await self.engine.execute_run(
            initial_payload=initial_payload,
            # REMOVED: strategy parameter as it's handled by graph config
            config=self.graph_config.dict() 
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
        
        if self.status != RunStatus.STOPPED:
            self.status = RunStatus.STOPPED
            await self._update_db_status(RunStatus.STOPPED)
    
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
        
        if status in [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.STOPPED]:
            updates["completed_at"] = datetime.utcnow().isoformat()
        
        updates["manual_wait_active"] = False
        updates["manual_input_required"] = None
        updates["routing_signal"] = RoutingSignals.END 

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
            if current_status not in [RunStatus.IDLE.value, RunStatus.STOPPED.value]:
                raise RuntimeError(f"Cannot start run {run_id} in status: {current_status}")

            try:
                graph_config = GraphConfig(**run_data["graph_config"])
            except Exception as e:
                raise ValueError(f"Failed to parse graph_config for run {run_id}: {e}")

            # Pass graph_config to executor. The executor will build the graph with strategy.
            executor = RunExecutor(
                run_id=run_id,
                graph_config=graph_config
            )
            self.executors[run_id] = executor
            
            initial_payload = input_payload if input_payload else {
                "description": run_data.get("description", "")
            }

            executor.task = asyncio.create_task(executor.start(initial_payload))
            
            return {
                "run_id": run_id,
                "status": executor.status.value,
                "message": "Run started successfully"
            }
    
    async def stop_run(self, run_id: str) -> Dict[str, Any]:
        executor = self.executors.get(run_id)
        if not executor:
            raise ValueError(f"Run {run_id} not active or executor not found")
        
        await executor.stop()
        return {"run_id": run_id, "status": executor.status.value}
    
    def get_run_status(self, run_id: str) -> Dict[str, Any]:
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
                return {
                    "run_id": run_id,
                    "status": run.get("status", "unknown"),
                    "is_active": False 
                }
        
        raise ValueError(f"Run {run_id} not found")
    
    def get_active_runs(self) -> List[str]:
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
