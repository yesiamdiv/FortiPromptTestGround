"""
================================================================================
REFACTORED BASE MIDDLEWARE INTERFACE (Gold Standard - V2)
================================================================================

ARCHITECTURAL PRINCIPLES:
--------------------------------------------------------------------------------
1. Strict Type Safety: All methods use SystemState, TurnData, and Domain Models
2. Read-Only Contract: Middlewares are pure observers - NO state mutation
3. Consistent Naming: runtime_config (not config), aligned with engine semantics
4. Explicit Domain Model Access: Use direct properties (NOT deprecated getters)
5. Immutability Enforcement: Documented and architecturally enforced

WHAT CHANGED FROM V1:
--------------------------------------------------------------------------------
- after_step() now receives SystemState instead of Dict[str, Any]
- Parameter renamed: config → runtime_config throughout
- Eliminated all legacy getter assumptions in documentation
- Added explicit immutability warnings
- Aligned lifecycle hook signatures with WorkflowEngine

MIDDLEWARE RESPONSIBILITIES:
--------------------------------------------------------------------------------
✓ Observation: Read SystemState and TurnData
✓ Persistence: Save to database
✓ Broadcasting: Emit WebSocket events
✓ Logging: Record execution traces
✓ Monitoring: Track performance metrics

✗ State Mutation: NEVER modify SystemState
✗ Execution Control: NEVER alter graph flow
✗ State Deltas: NEVER return state updates
✗ Side Effects During Graph Execution: NEVER block the execution pipeline

================================================================================
"""

from abc import ABC
from typing import Dict, Any, Optional
from engine.state_schema import SystemState
from engine.debug_utils import debug, tracer


class BaseMiddleware(ABC):
    """
    Abstract interface for system observers.
    
    Middlewares sit outside the LangGraph execution loop and observe state transitions.
    They are strictly READ-ONLY and must not mutate the state object.
    """
    
    def __init__(self, middleware_config: Dict[str, Any] = None):
        """
        Initialize middleware with configuration.
        
        Args:
            middleware_config: Middleware-specific configuration (NOT runtime_config)
        """
        self.middleware_config = middleware_config if middleware_config is not None else {}
        self.name = self.__class__.__name__
    
    async def before_run(
        self, 
        state: SystemState, 
        runtime_config: Dict[str, Any], 
        run_id: str
    ) -> None:
        """
        Triggered once before the graph starts execution.
        
        Use this to:
        - Initialize database records
        - Broadcast 'run_started' events
        - Set up monitoring/tracing contexts
        
        Args:
            state: The initial SystemState (READ-ONLY)
            runtime_config: Runtime execution configuration passed to LangGraph
            run_id: Unique identifier for this run
            
        WARNING: Do NOT mutate state. Changes will not propagate to graph execution.
        """
        pass
    
    async def after_step(
        self, 
        state: SystemState, 
        run_id: str, 
        node_name: Optional[str] = None
    ) -> None:
        """
        Triggered after every individual node execution.
        
        Use this to:
        - Read current_turn to check what just happened
        - Persist attack/defence/evaluation data
        - Broadcast real-time updates
        - Log step completion
        
        Args:
            state: The current SystemState after the step (READ-ONLY)
            run_id: Unique identifier for this run
            node_name: Name of the node that just executed (e.g., 'attack', 'defence', 'eval')
            
        Access pattern examples:
            # ✓ CORRECT - Direct property access
            attack = state["current_turn"]["attack"]
            if attack:
                text = attack.to_string()  # Method that returns string
                metadata = attack.metadata  # Direct property access
            
            defence = state["current_turn"]["defence"]
            if defence:
                response = defence.response_text  # Direct property access
                blocked = defence.was_blocked()   # Method with logic
            
            evaluation = state["current_turn"]["evaluation"]
            if evaluation:
                score = evaluation.score         # Direct property access
                success = evaluation.success     # Direct property access
                category = evaluation.category   # Direct property access
                reasoning = evaluation.reasoning # Direct property access
            
            # ✗ WRONG - Legacy getter patterns (DEPRECATED)
            # defence.get_text()          # Use: defence.response_text
            # evaluation.get_score()      # Use: evaluation.score
            # evaluation.is_success()     # Use: evaluation.success
            # evaluation.get_category()   # Use: evaluation.category
            # evaluation.get_reasoning()  # Use: evaluation.reasoning
            
        WARNING: Do NOT mutate state. Changes will not propagate to graph execution.
        """
        pass
    
    async def after_run(
        self, 
        state: SystemState, 
        run_id: str
    ) -> None:
        """
        Triggered once when the graph fully completes execution.
        
        Use this to:
        - Mark database runs as complete
        - Record final scores
        - Broadcast 'run_completed' events
        - Clean up resources
        
        Args:
            state: The final SystemState (READ-ONLY)
            run_id: Unique identifier for this run
            
        Access pattern:
            final_turn = state["current_turn"]
            if final_turn.get("evaluation"):
                final_score = final_turn["evaluation"].score  # Direct property
            
            context = state.get("strategy_context", {})
            best_score = context.get("best_score")
            
        WARNING: Do NOT mutate state. Changes will not propagate.
        """
        pass
    
    async def on_error(
        self, 
        error: Exception, 
        run_id: str, 
        state: Optional[SystemState] = None
    ) -> None:
        """
        Triggered when an execution error crashes the graph.
        
        Use this to:
        - Mark runs as failed in database
        - Broadcast error events
        - Log error details
        - Clean up partial state
        
        Args:
            error: The exception that occurred
            run_id: Unique identifier for the failed run
            state: The SystemState at error time (may be None if error occurred before state creation)
            
        WARNING: state may be None if error occurred during initialization.
        """
        pass


