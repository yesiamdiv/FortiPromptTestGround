"""
Workflow Engine - Core Orchestrator"""

from typing import Dict, Any, List
import asyncio
import uuid
from datetime import datetime
from middlewares.base import BaseMiddleware
from engine.state_schema import SystemState, create_initial_state, update_turn_data, RoutingSignals # IMPORT SYSTEMSTATE and RoutingSignals


class WorkflowEngine:
    """Execution wrapper that runs LangGraph with middleware injection"""
    
    def __init__(self, compiled_graph, middlewares: List[BaseMiddleware] = None):
        self.graph = compiled_graph
        self.middlewares = middlewares or []
        self.active_runs: Dict[str, Dict[str, Any]] = {}
    
    async def execute_run(
        self,
        payload: Dict[str, Any],
        graph_config: Any,  # The structural GraphConfig (Pydantic model)
        run_id: str = None
    ) -> SystemState:  # UPDATE RETURN TYPE
        
        run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        
        # Extract the runtime_config from the payload
        runtime_config = payload.pop("runtime_config", {})
        
        # Convert Pydantic graph_config to dict for the state
        state_config_dict = graph_config.dict() if hasattr(graph_config, 'dict') else {}

        # Create state using the structural config!
        initial_state = create_initial_state(run_id, payload, state_config_dict)
        
        self.active_runs[run_id] = {
            "status": "running",
            "started_at": datetime.utcnow().isoformat()
        }
        
        try:
            # Pass runtime_config directly to middlewares
            await self._trigger_before_run(initial_state, runtime_config, run_id)
            # Stream uses the extracted runtime_config!
            final_state = await self._execute_with_streaming(initial_state, runtime_config, run_id)
            await self._trigger_after_run(final_state, run_id)
            
            self.active_runs[run_id]["status"] = "completed"
            return final_state
            
        except Exception as e:
            self.active_runs[run_id]["status"] = "failed"
            self.active_runs[run_id]["error"] = str(e)
            await self._trigger_error(e, run_id)
            raise
    
    async def _execute_with_streaming(self, initial_state: SystemState, runtime_config: Dict[str, Any], run_id: str) -> SystemState:
        final_state = initial_state.copy()
        
        async for step_data in self.graph.astream(initial_state, runtime_config): # Use runtime_config here
            await self._trigger_after_step(step_data, run_id)
            
            updates = self._extract_updates(step_data)
            
            final_state = self._merge_state(final_state, updates)
            
        return final_state

    def _extract_updates(self, step_data: Dict[str, Any]) -> Dict[str, Any]:
        combined_updates = {}
        for node_name, updates in step_data.items():
            if isinstance(updates, dict):
                combined_updates.update(updates)
        return combined_updates

    def _merge_state(self, current_state: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        new_state = current_state.copy()
        
        for key, value in updates.items():
            if key == "current_turn" and isinstance(value, dict) and isinstance(new_state.get("current_turn"), dict):
                new_state["current_turn"] = update_turn_data(new_state["current_turn"], **value)
            elif isinstance(value, dict) and isinstance(new_state.get(key), dict):
                new_state[key] = {**new_state[key], **value}
            else:
                new_state[key] = value
                
        return new_state

    async def _trigger_before_run(self, initial_state: SystemState, runtime_config: Dict[str, Any], run_id: str):
        # Clean and simple: Pass runtime_config directly
        tasks = [m.before_run(initial_state, runtime_config, run_id) for m in self.middlewares]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _trigger_after_step(self, step_data, run_id):
        tasks = [m.after_step(step_data, run_id) for m in self.middlewares]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _trigger_after_run(self, final_state: SystemState, run_id):
        tasks = [m.after_run(final_state, run_id) for m in self.middlewares]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _trigger_error(self, error, run_id, step_data=None):
        tasks = [m.on_error(error, run_id, step_data) for m in self.middlewares if hasattr(m, 'on_error')]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

def create_default_engine():
    """Create a default engine with logging middleware"""
    from engine.graph_builder import build_default_graph
    from middlewares.logging_middleware import LoggingMiddleware
    
    graph = build_default_graph()
    middleware = LoggingMiddleware()
    return WorkflowEngine(compiled_graph=graph, middlewares=[middleware])
