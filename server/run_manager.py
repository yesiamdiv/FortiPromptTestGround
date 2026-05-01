"""
Run Manager

Manages the lifecycle of adversarial test runs.
Each run gets its own engine instance and executes as an isolated async task.
"""

import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum

from engine.workflow_engine import WorkflowEngine
from engine.graph_builder import build_default_graph
from middlewares.logging_middleware import LoggingMiddleware
from middlewares.database_middleware_v2 import DatabaseMiddlewareV2
from middlewares.websocket_middleware_v2 import WebSocketMiddlewareV2
from server.database.operations import get_db_ops
from server.database.connection import get_db
from server.websocket.socketio_manager import get_socketio_manager
from strategies.default_strategy import DefaultStrategy


class RunStatus(str, Enum):
    """Run execution status"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class RunExecutor:
    """
    Executes a single run with its own engine instance.
    
    Each run gets:
    - Dedicated engine instance
    - Dedicated middleware instances
    - Isolated async task
    """
    
    def __init__(self, run_id: str, strategy, config: Dict[str, Any]):
        """
        Initialize executor for a specific run.
        
        Args:
            run_id: Run identifier
            strategy: Strategy instance to use
            config: Run configuration
        """
        self.run_id = run_id
        self.strategy = strategy
        self.config = config
        
        # Create dedicated instances for this run
        self.graph = build_default_graph()
        
        # Create run-specific middlewares
        socketio_manager = get_socketio_manager()
        self.middlewares = [
            LoggingMiddleware({"verbose": False, "timestamps": True}),
            DatabaseMiddlewareV2(),
            WebSocketMiddlewareV2(socketio_manager)
        ]
        
        # Create dedicated engine
        self.engine = WorkflowEngine(
            compiled_graph=self.graph,
            middlewares=self.middlewares
        )
        
        # Execution control
        self.task: Optional[asyncio.Task] = None
        self.status = RunStatus.IDLE
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused initially
        self._stop_requested = False
    
    async def start(self, initial_payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Start run execution.
        
        Args:
            initial_payload: Initial payload for the run
        
        Returns:
            Execution result
        """
        if self.status == RunStatus.RUNNING:
            raise RuntimeError(f"Run {self.run_id} is already running")
        
        # Update status
        self.status = RunStatus.RUNNING
        await self._update_db_status(RunStatus.RUNNING)
        
        try:
            # Execute run
            result = await self.engine.execute_run(
                initial_payload=initial_payload,
                strategy=self.strategy,
                run_id=self.run_id,
                config=self.config
            )
            
            self.status = RunStatus.COMPLETED
            return result
            
        except asyncio.CancelledError:
            self.status = RunStatus.STOPPED
            await self._update_db_status(RunStatus.STOPPED)
            raise
            
        except Exception as e:
            self.status = RunStatus.FAILED
            await self._update_db_status(RunStatus.FAILED, error=str(e))
            raise
    
    async def pause(self):
        """Pause run execution"""
        if self.status != RunStatus.RUNNING:
            raise RuntimeError(f"Cannot pause run with status: {self.status}")
        
        self._pause_event.clear()
        self.status = RunStatus.PAUSED
        await self._update_db_status(RunStatus.PAUSED)
    
    async def resume(self):
        """Resume paused run"""
        if self.status != RunStatus.PAUSED:
            raise RuntimeError(f"Cannot resume run with status: {self.status}")
        
        self._pause_event.set()
        self.status = RunStatus.RUNNING
        await self._update_db_status(RunStatus.RUNNING)
    
    async def stop(self):
        """Stop run execution"""
        self._stop_requested = True
        
        if self.task and not self.task.done():
            self.task.cancel()
        
        self.status = RunStatus.STOPPED
        await self._update_db_status(RunStatus.STOPPED)
    
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
        
        await db_ops.update_run(self.run_id, updates)


class RunManager:
    """
    Manages all active runs.
    
    Responsibilities:
    - Create/start/pause/stop runs
    - Track active executors
    - Clean up completed runs
    """
    
    def __init__(self):
        """Initialize run manager"""
        self.executors: Dict[str, RunExecutor] = {}
        self._lock = asyncio.Lock()
    
    async def create_run(
        self,
        run_id: str,
        run_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new run (DB record only, doesn't start execution).
        
        Args:
            run_id: Run identifier
            run_data: Run metadata
        
        Returns:
            Created run data
        """
        db = get_db()
        if not db:
            raise RuntimeError("Database not connected")
        
        db_ops = get_db_ops(db)
        
        # Create run in database
        await db_ops.create_run({
            **run_data,
            "run_id": run_id,
            "status": RunStatus.IDLE.value
        })
        
        # Create Socket.IO room
        socketio_manager = get_socketio_manager()
        # Room is created automatically when clients join
        
        return await db_ops.get_run(run_id)
    
    async def start_run(
        self,
        run_id: str,
        strategy_name: str,
        strategy_config: Dict[str, Any],
        initial_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Start run execution.
        
        Args:
            run_id: Run identifier
            strategy_name: Name of strategy to use
            strategy_config: Strategy configuration
            initial_payload: Initial payload
        
        Returns:
            Run status
        """
        async with self._lock:
            # Check if already running
            if run_id in self.executors:
                executor = self.executors[run_id]
                if executor.status == RunStatus.RUNNING:
                    raise RuntimeError(f"Run {run_id} is already running")
            
            # Create strategy instance
            # TODO: Use strategy registry
            if strategy_name == "default":
                strategy = DefaultStrategy(strategy_config)
            else:
                raise ValueError(f"Unknown strategy: {strategy_name}")
            
            # Create executor
            executor = RunExecutor(
                run_id=run_id,
                strategy=strategy,
                config={"configurable": {"strategy": strategy}}
            )
            
            self.executors[run_id] = executor
            
            # Start execution as background task
            async def run_task():
                try:
                    await executor.start(initial_payload)
                finally:
                    # Cleanup after completion
                    await asyncio.sleep(300)  # Keep for 5 minutes
                    async with self._lock:
                        self.executors.pop(run_id, None)
            
            executor.task = asyncio.create_task(run_task())
            
            return {
                "run_id": run_id,
                "status": executor.status.value,
                "message": "Run started successfully"
            }
    
    async def pause_run(self, run_id: str) -> Dict[str, Any]:
        """
        Pause run execution.
        
        Args:
            run_id: Run identifier
        
        Returns:
            Run status
        """
        executor = self.executors.get(run_id)
        if not executor:
            raise ValueError(f"Run {run_id} not found or not active")
        
        await executor.pause()
        
        return {
            "run_id": run_id,
            "status": executor.status.value,
            "message": "Run paused successfully"
        }
    
    async def resume_run(self, run_id: str) -> Dict[str, Any]:
        """
        Resume paused run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            Run status
        """
        executor = self.executors.get(run_id)
        if not executor:
            raise ValueError(f"Run {run_id} not found or not active")
        
        await executor.resume()
        
        return {
            "run_id": run_id,
            "status": executor.status.value,
            "message": "Run resumed successfully"
        }
    
    async def stop_run(self, run_id: str) -> Dict[str, Any]:
        """
        Stop run execution.
        
        Args:
            run_id: Run identifier
        
        Returns:
            Run status
        """
        executor = self.executors.get(run_id)
        if not executor:
            raise ValueError(f"Run {run_id} not found or not active")
        
        await executor.stop()
        
        return {
            "run_id": run_id,
            "status": executor.status.value,
            "message": "Run stopped successfully"
        }
    
    async def get_run_status(self, run_id: str) -> Dict[str, Any]:
        """
        Get current run status.
        
        Args:
            run_id: Run identifier
        
        Returns:
            Run status info
        """
        executor = self.executors.get(run_id)
        
        if executor:
            return {
                "run_id": run_id,
                "status": executor.status.value,
                "is_active": executor.status in [RunStatus.RUNNING, RunStatus.PAUSED]
            }
        
        # Not in memory, check database
        db = get_db()
        if db:
            db_ops = get_db_ops(db)
            run = await db_ops.get_run(run_id)
            if run:
                return {
                    "run_id": run_id,
                    "status": run.get("status", "unknown"),
                    "is_active": False
                }
        
        raise ValueError(f"Run {run_id} not found")
    
    def get_active_runs(self) -> list:
        """
        Get list of active run IDs.
        
        Returns:
            List of run IDs
        """
        return [
            run_id for run_id, executor in self.executors.items()
            if executor.status in [RunStatus.RUNNING, RunStatus.PAUSED]
        ]


# Global run manager instance
_run_manager: Optional[RunManager] = None


def get_run_manager() -> RunManager:
    """
    Get the global run manager instance.
    
    Returns:
        RunManager instance
    """
    global _run_manager
    if _run_manager is None:
        _run_manager = RunManager()
    return _run_manager