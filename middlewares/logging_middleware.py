"""
Refactored Logging Middleware

CHANGES FROM ORIGINAL:
- ✓ Uses strict SystemState typing
- ✓ Direct property access (NOT legacy getters or getattr)
- ✓ Consistent runtime_config naming
- ✓ Aligned with base_refactored.py signature
"""

from typing import Dict, Any, Optional
from datetime import datetime
from middlewares.base import BaseMiddleware
from engine.debug_utils import debug, tracer, step, warn, err
from engine.state_schema import SystemState


class LoggingMiddleware(BaseMiddleware):
    """Console logging middleware for observing execution flow"""
    
    def __init__(self, middleware_config: Dict[str, Any] = None):
        default_config = {"verbose": False, "timestamps": True}
        if middleware_config:
            default_config.update(middleware_config)
        super().__init__(default_config)
        self.run_timings: Dict[str, float] = {}
    
    async def before_run(
        self, 
        state: SystemState, 
        runtime_config: Dict[str, Any], 
        run_id: str
    ) -> None:
        """Log run start"""
        tracer("LoggingMiddleware.before_run", run_id=run_id)
        self.run_timings[run_id] = datetime.utcnow().timestamp()
        
        config_dict = state.get("config", {})
        strategy_config = config_dict.get("strategy_config", {})
        strategy_name = strategy_config.get("strategy_name", "unknown_strategy")
        intent = state.get("payload", {}).get("intent", "unknown")
        
        self._log(f"\n{'='*60}")
        self._log(f"RUN STARTED: {run_id}")
        self._log(f"   Strategy: {strategy_name}")
        self._log(f"   Intent: {intent}")
        self._log(f"{'='*60}\n")
    
    async def after_step(
        self, 
        state: SystemState, 
        run_id: str, 
        node_name: Optional[str] = None
    ) -> None:
        """Log step completion"""
        if not state or not node_name:
            return
        
        self._log(f"NODE: {node_name}")
        
        current_turn = state.get("current_turn", {})
        
        # ✓ REFACTORED: Direct property/method access
        if current_turn.get("attack"):
            attack = current_turn["attack"]
            preview = attack.to_string()[:100]  # Method
            self._log(f"   Attack: {preview}...")
        
        if current_turn.get("defence"):
            defence = current_turn["defence"]
            blocked = "BLOCKED" if defence.was_blocked() else "ALLOWED"  # Method
            self._log(f"   Defence: {blocked}")
        
        if current_turn.get("evaluation"):
            evaluation = current_turn["evaluation"]
            summary = evaluation.to_summary()  # Method
            self._log(f"   Eval: {summary}")
        
        if state.get("routing_signal"):
            signal = state["routing_signal"]
            self._log(f"   Routing: {signal}")
        
        self._log("")
    
    async def after_run(
        self, 
        state: SystemState, 
        run_id: str
    ) -> None:
        """Log run completion"""
        if run_id in self.run_timings:
            elapsed = datetime.utcnow().timestamp() - self.run_timings[run_id]
            del self.run_timings[run_id]
        else:
            elapsed = 0
        
        self._log(f"\n{'='*60}")
        self._log(f"RUN COMPLETED: {run_id}")
        self._log(f"   Duration: {elapsed:.2f}s")
        
        current_turn = state.get("current_turn", {})
        if current_turn.get("evaluation"):
            # ✓ REFACTORED: Direct method call
            evaluation = current_turn["evaluation"]
            summary = evaluation.to_summary()
            self._log(f"   Final Result: {summary}")
        
        self._log(f"{'='*60}\n")
    
    async def on_error(
        self, 
        error: Exception, 
        run_id: str, 
        state: Optional[SystemState] = None
    ) -> None:
        """Log error"""
        err("Middleware caught error", run_id=run_id, 
            error_type=type(error).__name__, message=str(error))
        
        self._log(f"\nERROR in {run_id}: {type(error).__name__}")
        self._log(f"   Message: {str(error)}\n")
    
    def _log(self, message: str):
        """Internal logging helper"""
        if self.middleware_config.get("timestamps"):
            timestamp = datetime.utcnow().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] {message}")
        else:
            print(message)










# """
# Logging Middleware
# """

# from typing import Dict, Any
# from datetime import datetime
# from middlewares.base import BaseMiddleware
# from engine.debug_utils import debug, tracer, step, warn, err


# class LoggingMiddleware(BaseMiddleware):
#     """Console logging middleware for observing execution flow"""
    
#     def __init__(self, config: Dict[str, Any] = None):
#         default_config = {"verbose": False, "timestamps": True}
#         if config:
#             default_config.update(config)
#         super().__init__(default_config)
#         self.run_timings: Dict[str, float] = {}
    
#     async def before_run(self, initial_state: Dict[str, Any], config: Dict[str, Any], run_id: str):
#         tracer("LoggingMiddleware.before_run", run_id=run_id)
#         self.run_timings[run_id] = datetime.utcnow().timestamp()
        
#         strategy_config = initial_state.get("config", {}).get("strategy_config", {})
#         strategy_name = strategy_config.get("strategy_name", "unknown_strategy")
#         intent = initial_state.get("payload", {}).get("intent", "unknown")
        
#         self._log(f"\n{'='*60}")
#         self._log(f"RUN STARTED: {run_id}")
#         self._log(f"   Strategy: {strategy_name}")
#         self._log(f"   Intent: {intent}")
#         self._log(f"{'='*60}\n")
    
#     async def after_step(self, step_data, run_id):
#         if not step_data:
#             return
        
#         node_name = list(step_data.keys())[0]
#         node_output = step_data[node_name]
        
#         self._log(f"NODE: {node_name}")
        
#         if "current_turn" in node_output:
#             turn = node_output["current_turn"]
            
#             if turn.get("attack"):
#                 attack = turn["attack"]
#                 preview = getattr(attack, 'to_string', lambda: 'N/A')()[:100]
#                 self._log(f"   Attack: {preview}...")
            
#             if turn.get("defence"):
#                 defence = turn["defence"]
#                 blocked = "BLOCKED" if getattr(defence, 'was_blocked', lambda: False)() else "ALLOWED"
#                 self._log(f"   Defence: {blocked}")
            
#             if turn.get("evaluation"):
#                 eval_result = turn["evaluation"]
#                 summary = getattr(eval_result, 'to_summary', lambda: 'N/A')()
#                 self._log(f"   Eval: {summary}")
        
#         if "routing_signal" in node_output:
#             signal = node_output["routing_signal"]
#             self._log(f"   Routing: {signal}")
        
#         self._log("")
    
#     async def after_run(self, final_state, run_id):
#         if run_id in self.run_timings:
#             elapsed = datetime.utcnow().timestamp() - self.run_timings[run_id]
#             del self.run_timings[run_id]
#         else:
#             elapsed = 0
        
#         self._log(f"\n{'='*60}")
#         self._log(f"RUN COMPLETED: {run_id}")
#         self._log(f"   Duration: {elapsed:.2f}s")
        
#         if final_state.get("current_turn", {}).get("evaluation"):
#             eval_result = final_state["current_turn"]["evaluation"]
#             summary = getattr(eval_result, 'to_summary', lambda: 'N/A')()
#             self._log(f"   Final Result: {summary}")
        
#         self._log(f"{'='*60}\n")
    
#     async def on_error(self, error, run_id, step_data=None):
#         err("Middleware caught error", run_id=run_id, error_type=type(error).__name__, message=str(error))
#         self._log(f"\nERROR in {run_id}: {type(error).__name__}")
#         self._log(f"   Message: {str(error)}\n")
    
#     def _log(self, message: str):
#         if self.config.get("timestamps"):
#             timestamp = datetime.utcnow().strftime("%H:%M:%S.%f")[:-3]
#             print(f"[{timestamp}] {message}")
#         else:
#             print(message)
