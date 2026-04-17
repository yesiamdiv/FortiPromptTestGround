"""Workflow Engine - Core Orchestrator"""

from typing import Dict, Any, List
import asyncio
import uuid
from datetime import datetime
from middlewares.base import BaseMiddleware
from engine.state_schema import create_initial_state


class WorkflowEngine:
    """Execution wrapper that runs LangGraph with middleware injection"""
    
    def __init__(self, compiled_graph, middlewares: List[BaseMiddleware] = None):
        self.graph = compiled_graph
        self.middlewares = middlewares or []
        self.active_runs: Dict[str, Dict[str, Any]] = {}
    
    async def execute_run(
        self,
        initial_payload: Dict[str, Any],
        strategy,
        config: Dict[str, Any] = None,
        run_id: str = None
    ) -> Dict[str, Any]:
        """Execute a complete adversarial run with middleware injection"""
        
        run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        runtime_config = {"configurable": {"strategy": strategy}}
        if config:
            runtime_config.update(config)
        
        initial_state = create_initial_state(run_id, initial_payload, runtime_config)
        
        self.active_runs[run_id] = {
            "status": "running",
            "started_at": datetime.utcnow().isoformat()
        }
        
        try:
            await self._trigger_before_run(initial_state, runtime_config, run_id)
            final_state = await self._execute_with_streaming(initial_state, runtime_config, run_id)
            await self._trigger_after_run(final_state, run_id)
            
            self.active_runs[run_id]["status"] = "completed"
            return final_state
            
        except Exception as e:
            self.active_runs[run_id]["status"] = "failed"
            self.active_runs[run_id]["error"] = str(e)
            await self._trigger_error(e, run_id)
            raise
    
    async def _execute_with_streaming(self, initial_state, config, run_id):
        final_state = initial_state
        async for step_data in self.graph.astream(initial_state, config):
            await self._trigger_after_step(step_data, run_id)
            final_state = {**final_state, **self._extract_updates(step_data)}
        return final_state
    
    def _extract_updates(self, step_data: Dict[str, Any]) -> Dict[str, Any]:
        for node_name, updates in step_data.items():
            return updates
        return {}
    
    async def _trigger_before_run(self, initial_state, config, run_id):
        tasks = [m.before_run(initial_state, config, run_id) for m in self.middlewares]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _trigger_after_step(self, step_data, run_id):
        tasks = [m.after_step(step_data, run_id) for m in self.middlewares]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _trigger_after_run(self, final_state, run_id):
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
