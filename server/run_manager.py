"""
class RunExecutor:
    \"\"\"
    Manages the lifecycle and execution of a single independent run.

    The RunExecutor acts as the state machine for a specific execution request. It binds 
    the WorkflowEngine to a specific `run_id`, manages the asynchronous `asyncio.Task` 
    responsible for the execution, handles graceful cancellations (stopping), and ensures 
    the database accurately reflects the current status (IDLE, RUNNING, COMPLETED, FAILED, STOPPED).

    Attributes:
        run_id (str): The unique identifier for this execution.
        graph_config (GraphConfig): The configuration payload driving this execution.
        engine (WorkflowEngine): The engine instance executing this specific run.
        status (RunStatus): The current execution state of the run.
        task (Optional[asyncio.Task]): The background task executing the run, allowing for cancellation.
    \"\"\"

class RunManager:
    \"\"\"
    Global singleton manager that oversees all active run executions in the application.

    The RunManager acts as the primary entry point for the API layer. It safely routes 
    requests to create, start, stop, and monitor runs. It maintains an internal registry 
    of active `RunExecutor` instances and uses asynchronous locks to prevent race conditions 
    (e.g., attempting to start a run that is already processing).

    Attributes:
        executors (Dict[str, RunExecutor]): A dictionary mapping active `run_id`s to their executors.
    \"\"\"
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
        """
        Start run execution.
        
        ARCHITECTURAL BOUNDARY - THE SAFETY NET:
        RunExecutor is responsible ONLY for infrastructure management.
        It sets status to RUNNING at the start, then only updates the database
        in the "Sad Path" (crashes and cancellations):
        - asyncio.CancelledError → STOPPED
        - Exception → FAILED
        
        "Happy Path" status updates (COMPLETED for automatic, IDLE for manual)
        are handled by the respective middlewares in their after_run hooks.
        """
        tracer("Starting run execution", run_id=self.run_id)
        
        if self.status == RunStatus.RUNNING:
            raise RuntimeError(f"Run {self.run_id} is already running")
        
        # Infrastructure: Set to RUNNING at start
        self.status = RunStatus.RUNNING
        await self._update_db_status(RunStatus.RUNNING)
        step("Run started")
        
        try:
            # Let the engine execute - middlewares handle success state
            final_state = await self._run_with_controls(payload)
            checkpoint("Run completed successfully", run_id=self.run_id)
            return final_state
            
        except asyncio.CancelledError:
            # Sad Path: User explicitly cancelled
            self.status = RunStatus.STOPPED
            await self._update_db_status(RunStatus.STOPPED)
            warn("Run stopped by user")
            raise
        except Exception as e:
            # Sad Path: Catastrophic Python crash
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
        """
        Update run status in database (INFRASTRUCTURE ONLY).
        
        ARCHITECTURAL BOUNDARY:
        This method is ONLY called for infrastructure states managed by RunExecutor:
        - RUNNING: Initial state when execution starts
        - STOPPED: User cancellation (asyncio.CancelledError)
        - FAILED: Catastrophic Python crash (Exception)
        
        Business logic states (COMPLETED, IDLE) are handled by middlewares.
        """
        debug("Updating run status in DB", run_id=self.run_id, status=status.value)
        
        db = get_db()
        if db is None:
            return
        
        db_ops = get_db_ops(db)
        updates = {"status": status.value}
        
        if error:
            updates["error"] = error
        
        # Only set completed_at for terminal failure states
        if status in [RunStatus.FAILED, RunStatus.STOPPED]:
            updates["completed_at"] = datetime.utcnow().isoformat()
            updates["manual_wait_active"] = False
            updates["manual_input_required"] = None

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
            
            # [FIXED]: Robustly determine current status and extract fields for BOTH Dicts and Models
            if isinstance(run_data, RunModel):
                current_status_str = run_data.status
                raw_graph_config = run_data.graph_config
                description = getattr(run_data, "description", "")
            elif isinstance(run_data, dict):
                current_status_str = run_data.get("status", RunStatus.IDLE.value)
                raw_graph_config = run_data.get("graph_config")
                description = run_data.get("description", "")
            else:
                raise TypeError(f"Unexpected type for run_data: {type(run_data)}")

            if current_status_str not in [RunStatus.IDLE.value, RunStatus.STOPPED.value]:
                raise RuntimeError(f"Cannot start run {run_id} in status: {current_status_str}")

            if not raw_graph_config:
                raise ValueError(f"Failed to find graph_config for run {run_id}")

            try:
                if isinstance(raw_graph_config, dict):
                    graph_config = GraphConfig(**raw_graph_config)
                else:
                    graph_config = raw_graph_config
            except Exception as e:
                raise ValueError(f"Failed to parse graph_config for run {run_id}: {e}")

            # Pass graph_config to executor
            executor = RunExecutor(
                run_id=run_id,
                graph_config=graph_config
            )
            self.executors[run_id] = executor
            
            payload = input_payload.copy() if input_payload else {}
            if "description" not in payload:
                payload["description"] = description

            executor.task = asyncio.create_task(executor.start(payload))

            # For manual runs: clean up the executor from memory when the turn completes
            # so the next turn can create a fresh executor without hitting the RUNNING guard.
            def _on_turn_done(fut, rid=run_id):
                self.executors.pop(rid, None)
            executor.task.add_done_callback(_on_turn_done)

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
    
    async def cleanup_zombie_runs(self) -> Dict[str, Any]:
        """
        Clean up "zombie" runs that were stuck in RUNNING during a server restart.
        
        ARCHITECTURAL BOUNDARY - GLOBAL LIFECYCLE:
        This method should be called on server startup to handle runs that died
        during a server crash/restart. It differentiates based on graph_type:
        
        - Automatic runs: Mark as FAILED (they were interrupted mid-loop)
        - Manual runs: Revert to IDLE (they were just waiting for the user anyway)
        
        Returns:
            Dict with cleanup statistics
        """
        tracer("Starting zombie run cleanup")
        
        db = get_db()
        if db is None:
            warn("Database not connected, skipping zombie cleanup")
            return {"cleaned": 0, "failed": 0, "message": "Database not connected"}
        
        try:
            db_ops = get_db_ops(db)
            
            # Find all runs stuck in RUNNING status
            zombie_runs = await db.runs.find({"status": "running"}).to_list(length=None)
            
            if not zombie_runs:
                step("No zombie runs found")
                return {"cleaned": 0, "failed": 0, "message": "No zombie runs found"}
            
            cleaned_count = 0
            failed_count = 0
            
            for run_doc in zombie_runs:
                try:
                    run_id = run_doc.get("run_id", str(run_doc.get("_id", "unknown")))
                    graph_config_dict = run_doc.get("graph_config", {})
                    
                    # Determine graph type
                    if isinstance(graph_config_dict, dict):
                        graph_type = graph_config_dict.get("graph_type", "automatic")
                    else:
                        # Fallback if it's a Pydantic model
                        graph_type = getattr(graph_config_dict, "graph_type", "automatic")
                    
                    if graph_type == "manual":
                        # Manual run: Revert to IDLE (it was just waiting for user)
                        await db_ops.update_run(run_id, {
                            "status": "idle",
                            "manual_wait_active": True,
                            "updated_at": datetime.utcnow().isoformat(),
                            "error": None  # Clear any previous error
                        })
                        step(f"Reverted manual zombie run to IDLE: {run_id}")
                    else:
                        # Automatic run: Mark as FAILED (it was interrupted mid-execution)
                        await db_ops.update_run(run_id, {
                            "status": "failed",
                            "completed_at": datetime.utcnow().isoformat(),
                            "error": "Server restarted during execution",
                            "manual_wait_active": False
                        })
                        step(f"Marked automatic zombie run as FAILED: {run_id}")
                    
                    cleaned_count += 1
                    
                except Exception as e:
                    err(f"Failed to clean up zombie run: {e}", run_id=run_id)
                    failed_count += 1
            
            checkpoint(f"Zombie cleanup complete: {cleaned_count} cleaned, {failed_count} failed")
            return {
                "cleaned": cleaned_count,
                "failed": failed_count,
                "message": f"Successfully cleaned {cleaned_count} zombie runs"
            }
            
        except Exception as e:
            err(f"Zombie cleanup failed: {e}")
            return {"cleaned": 0, "failed": 0, "message": f"Cleanup failed: {str(e)}"}


_run_manager: Optional[RunManager] = None

def get_run_manager() -> RunManager:
    global _run_manager
    if _run_manager is None:
        _run_manager = RunManager()
    return _run_manager
