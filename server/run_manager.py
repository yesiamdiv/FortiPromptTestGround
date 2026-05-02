
"""
Run Manager - Final Integrated Version with Wait/Pause/Resume Logic and WebSocket Emissions
"""

import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

from engine.workflow_engine import WorkflowEngine
from engine.graph_builder import build_dynamic_graph
from engine.registry import get_node_registry, get_strategy_registry
from middlewares.logging_middleware import LoggingMiddleware
from middlewares.database_middleware_v2 import DatabaseMiddlewareV2
from middlewares.websocket_middleware_v2 import WebSocketMiddlewareV2
from server.database.operations import get_db_ops
from server.database.connection import get_db
from server.websocket.socketio_manager import get_socketio_manager
from server.config.models import GraphConfig
from engine.state_schema import create_initial_state, SystemState, RoutingSignals
from server.database.manual_operations import get_manual_ops # Import manual ops
from server.database.manual_models import ManualTurn # For type hinting

# Import WebSocket event functions
from server.websocket_event_manager import (
    emit_manual_wait_events,
    emit_resumption_event,
    emit_turn_update_events
)


class RunStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_INPUT = "waiting_input"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class RunExecutor:
    """Executes a single run with dynamic graph and manual input support"""
    
    def __init__(self, run_id: str, graph_config: GraphConfig):
        self.run_id = run_id
        self.graph_config = graph_config
        
        self.graph = build_dynamic_graph(graph_config)
        
        strategy_registry = get_strategy_registry()
        self.strategy = strategy_registry.get(
            graph_config.strategy_config.strategy_name,
            config=graph_config.strategy_config.strategy_params
        )
        
        socketio_manager = get_socketio_manager()
        self.middlewares = [
            LoggingMiddleware({"verbose": False}),
            DatabaseMiddlewareV2(),
            WebSocketMiddlewareV2(socketio_manager)
        ]
        
        self.engine = WorkflowEngine(
            compiled_graph=self.graph,
            middlewares=self.middlewares
        )
        
        self.task: Optional[asyncio.Task] = None
        self.status = RunStatus.IDLE
        self._pause_event = asyncio.Event() 
        self._pause_event.set()  # Not paused initially
        self._manual_input_event = asyncio.Event() # Event for manual input signal
        self._stop_requested = False
        self._current_state: Optional[SystemState] = None
        self._manual_wait_active = False
        self.manual_ops = None # To be initialized from manual_ops

    async def _initialize_dependencies(self):
        """Initialize database operations and get manual_ops if needed."""
        db = get_db()
        if not db:
            raise RuntimeError("Database not connected")
        if self.manual_ops is None:
            self.manual_ops = get_manual_ops(db)

    async def start(self, initial_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Start run execution"""
        if self.status == RunStatus.RUNNING:
            raise RuntimeError(f"Run {self.run_id} is already running")
        
        self.status = RunStatus.RUNNING
        await self._update_db_status(RunStatus.RUNNING)
        
        try:
            result = await self._run_with_controls(initial_payload)
            
            # Final status update after loop finishes normally
            if self.status == RunStatus.RUNNING:
                self.status = RunStatus.COMPLETED
            await self._update_db_status(self.status)
            return result
            
        except asyncio.CancelledError:
            self.status = RunStatus.STOPPED
            await self._update_db_status(RunStatus.STOPPED)
            raise
        except Exception as e:
            self.status = RunStatus.FAILED
            await self._update_db_status(RunStatus.FAILED, error=str(e))
            raise
    
    async def _run_with_controls(self, initial_payload: Dict[str, Any]) -> Dict[str, Any]:
        """Run loop with pause and manual input support"""
        
        await self._initialize_dependencies() # Ensure manual_ops is ready
        
        runtime_config = {"configurable": {"strategy": self.strategy}}
        initial_state = create_initial_state(self.run_id, initial_payload, runtime_config)
        self._current_state = initial_state
        
        await self._trigger_middleware("before_run", initial_state, runtime_config, self.run_id)
        
        async for step_data in self.graph.astream(initial_state, runtime_config):
            # --- Check for Stop Request ---
            if self._stop_requested:
                break

            # --- Update State ---
            self._current_state.update(self._extract_updates(step_data))

            # --- Handle Manual Wait ---
            if self._current_state.get("manual_wait_active") == True:
                session_id = self._current_state.get("session_id")
                if session_id:
                    # Emit WebSocket events indicating manual wait
                    await emit_manual_wait_events(self, session_id)
                else:
                    print(f"ManualWaitError: Session ID missing in state for run {self.run_id} during manual wait.")
                
                # Pause execution and wait for manual input signal
                await self._handle_manual_wait()
                
                # After resuming, the loop continues with the updated state.
                # No explicit 'continue' needed here as the loop progresses naturally.

            # --- Handle General Pause ---
            if not self._pause_event.is_set():
                await self._handle_general_pause()

            # Trigger middleware for the current step
            await self._trigger_middleware("after_step", step_data, self.run_id)
        
        # Trigger after_run middleware with the final state
        await self._trigger_middleware("after_run", self._current_state, self.run_id)
        
        return self._current_state
    
    async def _handle_manual_wait(self):
        """Handles the pause and wait logic for manual input."""
        self.status = RunStatus.WAITING_INPUT
        await self._update_db_status(RunStatus.WAITING_INPUT)
        
        # Wait for the manual input event to be set externally (e.g., by API)
        await self._manual_input_event.wait()
        
        # --- Resuming after manual input ---
        self._manual_input_event.clear() # Clear the event after waking up
        self._manual_wait_active = False # Reset the internal flag
        # Update state flags to reflect that manual wait is over
        if self.current_state:
            self.current_state["manual_wait_active"] = False
            self.current_state["manual_input_required"] = None
        
        self.status = RunStatus.RUNNING # Set status back to running
        await self._update_db_status(RunStatus.RUNNING)

    async def _handle_general_pause(self):
        """Handles general pausing of the run."""
        self.status = RunStatus.PAUSED
        await self._update_db_status(RunStatus.PAUSED)
        print(f"Run {self.run_id}: Paused. Waiting for resume signal...")
        await self._pause_event.wait()
        
        self.status = RunStatus.RUNNING
        await self._update_db_status(RunStatus.RUNNING)
        print(f"Run {self.run_id}: Resumed from general pause.")
        self._pause_event.set() # Reset the pause event

    async def provide_manual_input(self, input_data: Dict[str, Any]):
        """Provide manual input and resume execution"""
        # Check if the executor is in a state that expects manual input
        if not self._manual_wait_active and self.status != RunStatus.WAITING_INPUT:
            raise RuntimeError(f"Run {self.run_id} is not waiting for manual input (current status: {self.status}, manual_wait_active: {self._manual_wait_active})")
        
        session_id = self._current_state.get("session_id")
        if not session_id:
            # Fallback: try to get from DB if not in state (e.g., if executor restarted)
            db = get_db()
            if db:
                manual_ops = get_manual_ops(db)
                sessions = await manual_ops.list_sessions(self.run_id, status='active', limit=1)
                if sessions:
                    session_id = sessions[0]["session_id"]
                else:
                    raise ValueError(f"No active manual session found for run {self.run_id} to provide input.")
            else:
                raise RuntimeError("Database not connected. Cannot provide manual input.")

        turn_index = self._current_state.get("turn_index", 0)
        turn_id = f"{session_id}_turn_{turn_index}"

        # Update state with manual input
        if "attack_prompt" in input_data and self.current_state:
            attack = create_simple_attack(input_data["attack_prompt"])
            self.current_state["current_turn"]["attack"] = attack
            self.current_state["manual_wait_active"] = False
            self.current_state["manual_input_required"] = None
            self.current_state["routing_signal"] = RoutingSignals.ATTACK # Signal to proceed
            print(f"Manual input processed. State updated for run {self.run_id}.")

        # Update DB with prompt and reset wait flags
        if self.manual_ops:
            await self.manual_ops.add_turn(
                session_id=session_id,
                turn_id=turn_id,
                turn_index=turn_index,
                role="attacker",
                attack_prompt=input_data.get("attack_prompt"),
                metadata={"status": "input_received", "run_id": self.run_id, "session_id": session_id}
            )
            await self.manual_ops.update_session(session_id, {
                "status": "active",
                "turn_count": turn_index + 1
            })

        # Signal to resume execution
        self._manual_input_event.set()
        self._manual_wait_active = False
        self._manual_input_event.clear() 

        # Emit resumption event
        await emit_resumption_event(self.run_id, session_id, turn_id)

    async def pause(self):
        """Pause execution"""
        if self.status not in [RunStatus.RUNNING, RunStatus.WAITING_INPUT]:
            raise RuntimeError(f"Cannot pause run with status: {self.status}")
        
        self._pause_event.clear()
        if self._manual_wait_active:
            self._manual_input_event.set()
            await asyncio.sleep(0.01)
        
        self.status = RunStatus.PAUSED
        await self._update_db_status(RunStatus.PAUSED)
    
    async def resume(self):
        """Resume paused execution"""
        if self.status != RunStatus.PAUSED:
            raise RuntimeError(f"Cannot resume run with status: {self.status}")
        
        self._pause_event.set()
        self._manual_input_event.set()
        
        self._manual_wait_active = False
        if self.current_state:
            self.current_state["manual_wait_active"] = False
            self.current_state["manual_input_required"] = None

        self.status = RunStatus.RUNNING
        await self._update_db_status(RunStatus.RUNNING)
    
    async def stop(self):
        """Stop execution"""
        self._stop_requested = True
        self._pause_event.set()
        self._manual_input_event.set()
        
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        self.status = RunStatus.STOPPED
        await self._update_db_status(RunStatus.STOPPED)
    
    def _extract_updates(self, step_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract state updates from step data"""
        updates = {{}}
        for node_name, node_output in step_data.items():
            if isinstance(node_output, dict):
                updates.update(node_output)
        return updates

    async def _trigger_middleware(self, method: str, *args):
        """Trigger middleware method"""
        tasks = []
        for m in self.middlewares:
            if hasattr(m, method):
                tasks.append(getattr(m, method)(*args))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
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
        
        if status in [RunStatus.STOPPED, RunStatus.FAILED, RunStatus.COMPLETED]:
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
        await db_ops.create_run({**run_data, "run_id": run_id, "status": "idle"})
        
        return await db_ops.get_run(run_id)
    
    async def start_run(self, run_id: str) -> Dict[str, Any]:
        """Start run execution"""
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

            executor = RunExecutor(
                run_id=run_id,
                graph_config=graph_config
            )
            self.executors[run_id] = executor
            
            initial_payload = {
                "intent": run_data.get("intent", ""),
                "target": run_data.get("target"),
                "user_id": run_data.get("user_id"),
                "session_id": run_data.get("session_id"), 
                "tags": run_data.get("tags", []),
                "description": run_data.get("description", "")
            }

            executor.task = asyncio.create_task(executor.start(initial_payload))
            
            return {
                "run_id": run_id,
                "status": executor.status.value,
                "message": "Run started successfully"
            }
    
    async def provide_manual_input(self, run_id: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        executor = self.executors.get(run_id)
        if not executor:
            raise ValueError(f"Run {run_id} not active or executor not found")
        
        await executor.provide_manual_input(input_data)
        
        return {
            "run_id": run_id,
            "status": "input_provided",
            "message": "Manual input processed, executor signaled to resume."
        }

    async def pause_run(self, run_id: str) -> Dict[str, Any]:
        executor = self.executors.get(run_id)
        if not executor:
            raise ValueError(f"Run {run_id} not active or executor not found")
        
        await executor.pause()
        return {"run_id": run_id, "status": executor.status.value}
    
    async def resume_run(self, run_id: str) -> Dict[str, Any]:
        executor = self.executors.get(run_id)
        if not executor:
            raise ValueError(f"Run {run_id} not active or executor not found")
        
        await executor.resume()
        return {"run_id": run_id, "status": executor.status.value}
    
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
                "is_active": executor.status in [RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.WAITING_INPUT]
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
            if executor.status in [RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.WAITING_INPUT]
        ]


_run_manager: Optional[RunManager] = None

def get_run_manager() -> RunManager:
    global _run_manager
    if _run_manager is None:
        _run_manager = RunManager()
    return _run_manager
