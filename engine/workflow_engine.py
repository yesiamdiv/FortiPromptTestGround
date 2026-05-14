"""
Refactored WorkflowEngine

CHANGES FROM ORIGINAL:
- ✓ Properly passes SystemState (not step_data dict) to after_step()
- ✓ Extracts node_name from step_data and passes it separately
- ✓ Maintains backward compatibility with current execution flow
- ✓ Preserves all existing merge/update logic
- ✓ Aligned middleware calls with refactored base interface

KEY INSIGHT:
The original engine passed raw step_data (Dict[str, Any]) to middlewares,
forcing them to extract state manually. Now we pass the merged SystemState
plus the node_name explicitly, giving middlewares type-safe access.
"""

from typing import Dict, Any, List, Optional
import asyncio
import uuid
from datetime import datetime
from middlewares.base import BaseMiddleware
from engine.state_schema import SystemState, create_initial_state, update_turn_data, RoutingSignals
from engine.debug_utils import debug, tracer, step, checkpoint, warn, err, state
from langgraph.graph.state import CompiledStateGraph


class WorkflowEngine:
    """
    Core orchestrator that executes a compiled state graph with middleware injection.
    
    The WorkflowEngine wraps LangGraph's streaming execution to provide robust
    lifecycle hooks. It handles state initialization, merging node outputs, and
    triggering before/after middlewares at both run-level and step-level.
    """
    
    def __init__(
        self, 
        compiled_graph: CompiledStateGraph, 
        middlewares: List[BaseMiddleware] = None
    ):
        self.graph: CompiledStateGraph = compiled_graph
        self.middlewares = middlewares or []
        self.active_runs: Dict[str, Dict[str, Any]] = {}
    
    async def execute_run(
        self,
        payload: Dict[str, Any],
        config: Any,
        run_id: str = None
    ) -> SystemState:
        """
        Execute a complete graph run with middleware hooks.
        
        Args:
            payload: Input payload containing runtime_config and other data
            config: Pydantic config object (strategy config, node config, etc.)
            run_id: Optional run identifier (generated if not provided)
            
        Returns:
            Final SystemState after graph completion
        """
        run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        tracer("execute_run started", run_id=run_id)
        
        # Extract runtime_config from payload
        runtime_config = payload.pop("runtime_config", {})
        step("Extracted runtime_config", config_keys=list(runtime_config.keys()))
        
        # Convert config to dict for state storage
        state_config_dict = config.dict() if hasattr(config, 'dict') else {}

        # Create initial state
        initial_state = create_initial_state(run_id, payload, state_config_dict)
        checkpoint("Created initial state")
        
        # Track run status
        self.active_runs[run_id] = {
            "status": "running",
            "started_at": datetime.utcnow().isoformat()
        }
        
        try:
            # Trigger before_run middlewares
            await self._trigger_before_run(initial_state, runtime_config, run_id)
            
            # Execute graph with streaming
            final_state = await self._execute_with_streaming(
                initial_state, 
                runtime_config, 
                run_id
            )
            
            # Trigger after_run middlewares
            await self._trigger_after_run(final_state, run_id)
            
            self.active_runs[run_id]["status"] = "completed"
            step("execute_run completed", run_id=run_id)
            return final_state
            
        except Exception as e:
            self.active_runs[run_id]["status"] = "failed"
            self.active_runs[run_id]["error"] = str(e)
            await self._trigger_error(e, run_id, initial_state)
            raise
    
    async def _execute_with_streaming(
        self, 
        initial_state: SystemState, 
        runtime_config: Dict[str, Any], 
        run_id: str
    ) -> SystemState:
        """
        Stream through graph execution and merge state updates.
        
        This is where the refactor happens: we track the merged state and pass
        it to middlewares instead of raw step_data.
        """
        # Start with initial state
        current_state = initial_state.copy()
        step("Starting streaming execution", run_id=run_id)
        
        # Configure LangGraph with runtime_config.
        # recursion_limit is stored on the graph object by GraphBuilder.compile();
        # fall back to a generous default if somehow not set.
        recursion_limit = getattr(self.graph, "_recursion_limit", 200)
        langgraph_config = {
            "configurable":  runtime_config,
            "recursion_limit": recursion_limit,
        }
        debug("Graph execution config", recursion_limit=recursion_limit)

        # Stream through graph execution
        async for step_data in self.graph.astream(initial_state, langgraph_config):
            # Extract node name from step_data
            node_name = self._extract_node_name(step_data)
            
            # Merge updates into current state
            updates = self._extract_updates(step_data)
            current_state = self._merge_state(current_state, updates)
            
            # ✓ REFACTORED: Pass SystemState + node_name to middlewares
            await self._trigger_after_step(current_state, run_id, node_name)
            
            checkpoint("Processed step update", node=node_name)
        
        return current_state
    
    def _extract_node_name(self, step_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract the node name from step_data.
        
        LangGraph returns step_data as {node_name: updates}, so we grab the first key.
        """
        if not step_data:
            return None
        return list(step_data.keys())[0] if step_data else None

    def _extract_updates(self, step_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract state updates from step_data.
        
        Combines all updates from all nodes in this step (usually just one node).
        """
        combined_updates = {}
        for node_name, updates in step_data.items():
            if isinstance(updates, dict):
                combined_updates.update(updates)
        debug("Extracted updates", nodes=list(step_data.keys()))
        return combined_updates

    def _merge_state(
        self, 
        current_state: Dict[str, Any], 
        updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge state updates into current state.
        
        Special handling for current_turn to preserve type safety.
        """
        tracer("_merge_state", keys=list(updates.keys()))
        new_state = current_state.copy()
        
        for key, value in updates.items():
            # Special merge for current_turn
            if key == "current_turn" and isinstance(value, dict) and isinstance(new_state.get("current_turn"), dict):
                new_state["current_turn"] = update_turn_data(
                    new_state["current_turn"], 
                    **value
                )
                debug("Merged current_turn", keys=list(value.keys()))
            
            # Deep merge for nested dicts
            elif isinstance(value, dict) and isinstance(new_state.get(key), dict):
                new_state[key] = {**new_state[key], **value}
            
            # Direct assignment for everything else
            else:
                new_state[key] = value
                
        step("State merge complete", new_keys=list(new_state.keys()))
        return new_state

    # =========================================================================
    # MIDDLEWARE TRIGGER METHODS - Refactored Signatures
    # =========================================================================

    async def _trigger_before_run(
        self, 
        initial_state: SystemState, 
        runtime_config: Dict[str, Any], 
        run_id: str
    ) -> None:
        """Trigger all before_run middleware hooks"""
        debug("Triggering before_run middlewares", count=len(self.middlewares))
        
        tasks = [
            m.before_run(initial_state, runtime_config, run_id) 
            for m in self.middlewares
        ]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _trigger_after_step(
        self, 
        state: SystemState, 
        run_id: str, 
        node_name: Optional[str]
    ) -> None:
        """
        Trigger all after_step middleware hooks.
        
        ✓ REFACTORED: Passes SystemState (not Dict[str, Any])
        ✓ REFACTORED: Passes node_name explicitly
        """
        debug(
            "Triggering after_step middlewares", 
            run_id=run_id, 
            node=node_name
        )
        
        tasks = [
            m.after_step(state, run_id, node_name) 
            for m in self.middlewares
        ]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _trigger_after_run(
        self, 
        final_state: SystemState, 
        run_id: str
    ) -> None:
        """Trigger all after_run middleware hooks"""
        step("Triggering after_run middlewares", run_id=run_id)
        
        tasks = [
            m.after_run(final_state, run_id) 
            for m in self.middlewares
        ]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _trigger_error(
        self, 
        error: Exception, 
        run_id: str, 
        state: Optional[SystemState] = None
    ) -> None:
        """Trigger all on_error middleware hooks"""
        err("Workflow error", error=str(error), run_id=run_id)
        
        tasks = [
            m.on_error(error, run_id, state) 
            for m in self.middlewares 
            if hasattr(m, 'on_error')
        ]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


def create_default_engine():
    """
    Factory function for creating a default engine instance.
    
    Uses the default graph and logging middleware.
    """
    tracer("create_default_engine")
    from engine.graph_builder import build_default_graph
    from middlewares.logging_middleware import LoggingMiddleware
    
    graph = build_default_graph()
    step("Built default graph")
    
    middleware = LoggingMiddleware()
    engine = WorkflowEngine(compiled_graph=graph, middlewares=[middleware])
    checkpoint("Default engine created")
    return engine


