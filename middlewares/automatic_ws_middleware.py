"""
Refactored Automatic WebSocket Middleware

CHANGES FROM ORIGINAL:
- ✓ Uses strict SystemState typing (not Dict[str, Any])
- ✓ Direct property access (NOT legacy getters)
- ✓ Consistent runtime_config naming
- ✓ Aligned with base.py signature
- ✓ Eliminated dictionary-style assumptions
- ✓ Fixed all domain model access patterns
"""

from typing import Dict, Any, Optional
from middlewares.base import BaseMiddleware
from server.websocket.socketio_manager import SocketIOManager
from server.websocket.operations import get_ws_ops
from engine.debug_utils import debug, tracer, step, warn, err
from engine.state_schema import SystemState


class AutomaticWSMiddleware(BaseMiddleware):
    """
    WebSocket middleware for automatic runs.
    
    Broadcasts real-time updates as the graph executes.
    """
    
    def __init__(
        self, 
        socketio_manager: SocketIOManager, 
        middleware_config: Dict[str, Any] = None
    ):
        default_config = {
            "broadcast_attacks": True,
            "broadcast_defences": True,
            "broadcast_evaluations": True
        }
        if middleware_config:
            default_config.update(middleware_config)
        super().__init__(default_config)
        
        self.ws_ops = get_ws_ops(socketio_manager)

    async def before_run(
        self, 
        state: SystemState, 
        runtime_config: Dict[str, Any], 
        run_id: str
    ) -> None:
        """Broadcast run start event"""
        tracer("AutomaticWSMiddleware.before_run", run_id=run_id)
        
        try:
            # Extract configuration with type-safe access
            config_dict = state.get("config", {})
            strategy_config = config_dict.get("strategy_config", {})
            strategy_name = strategy_config.get("strategy_name", "unknown_strategy")
            
            payload = state.get("payload", {})
            
            await self.ws_ops.broadcast_run_started(
                run_id,
                {
                    'strategy': strategy_name,
                    'intent': payload.get("intent", "unknown"),
                    'target': payload.get("target"),
                    'timestamp': state.get("start_time")
                }
            )
            debug("Run started broadcast sent")
            
        except Exception as e:
            err("Error in before_run", error=str(e))
    
    async def after_step(
        self, 
        state: SystemState, 
        run_id: str, 
        node_name: Optional[str] = None
    ) -> None:
        """Broadcast step updates"""
        if not state or not node_name:
            return
        
        try:
            # Extract iteration context
            context = state.get("strategy_context", {})
            iteration = context.get("iteration_count", 0)
            # 5-B4: turn_id lives in current_turn, not strategy_context
            turn_id = state.get("current_turn", {}).get("turn_id") or context.get("turn_id", f"turn_{iteration}")

            # Route based on node name
            if node_name == "attack" and self.middleware_config.get("broadcast_attacks"):
                await self._broadcast_attack(run_id, iteration, state, turn_id)
            
            elif node_name == "defence" and self.middleware_config.get("broadcast_defences"):
                await self._broadcast_defence(run_id, iteration, state, turn_id)
            
            elif node_name == "eval" and self.middleware_config.get("broadcast_evaluations"):
                await self._broadcast_evaluation(run_id, iteration, state, turn_id)
            
            elif node_name == "router":
                await self._broadcast_routing(run_id, state)
            
        except Exception as e:
            err("Error in after_step", error=str(e), node=node_name)
    
    async def after_run(
        self, 
        state: SystemState, 
        run_id: str
    ) -> None:
        """Broadcast run completion event"""
        tracer("AutomaticWSMiddleware.after_run", run_id=run_id)
        
        try:
            context = state.get("strategy_context", {})
            current_turn = state.get("current_turn", {})
            routing_signal = state.get("routing_signal")
            
            final_data = {
                'total_attempts': context.get("iteration_count", 0),
                'routing_signal': routing_signal,
                'timestamp': current_turn.get("timestamp")
            }
            
            # ✓ REFACTORED: Direct property access for evaluation
            if current_turn.get("evaluation"):
                eval_result = current_turn["evaluation"]
                final_data['final_evaluation'] = {
                    'score': eval_result.score,       # Direct property
                    'success': eval_result.success,   # Direct property
                    'category': eval_result.category, # Direct property
                    'summary': eval_result.to_summary() # Method
                }
            
            await self.ws_ops.broadcast_run_completed(run_id, final_data)
            step("Run completed broadcast sent")

            # Notify all connected clients that a new completed run is available
            # (used to refresh the runs list in the frontend sidebar)
            context = state.get("strategy_context", {})
            await self.ws_ops.broadcast_new_run_available(run_id, {
                "strategy": context.get("strategy_name", "unknown"),
                "status": "completed",
            })

        except Exception as e:
            err("Error in after_run", error=str(e))
    
    async def on_error(
        self, 
        error: Exception, 
        run_id: str, 
        state: Optional[SystemState] = None
    ) -> None:
        """Broadcast error event"""
        try:
            await self.ws_ops.broadcast_run_error(
                run_id,
                error=str(error),
                error_type=type(error).__name__
            )
            debug("Error broadcast sent")
        except Exception as e:
            err("Error in on_error handler", error=str(e))
    
    # =========================================================================
    # PRIVATE HELPER METHODS - Refactored with Direct Property Access
    # =========================================================================
    
    async def _broadcast_attack(
        self, 
        run_id: str, 
        iteration: int, 
        state: SystemState, 
        turn_id: str
    ) -> None:
        """Broadcast attack generated event"""
        current_turn = state.get("current_turn", {})
        attack = current_turn.get("attack")
        
        if not attack:
            return
        
        # ✓ REFACTORED: Use .to_string() method and direct .metadata access
        attack_text = attack.to_string()
        
        attack_data = {
            'preview': attack_text[:200],
            'full_text': attack_text,
            'type': attack._infer_type() if hasattr(attack, '_infer_type') else 'text',
            'metadata': attack.metadata,  # Direct property access
            'timestamp': current_turn.get("timestamp")
        }
        
        await self.ws_ops.broadcast_attack_generated(
            run_id,
            turn_id,
            iteration,
            attack_data
        )
    
    async def _broadcast_defence(
        self, 
        run_id: str, 
        iteration: int, 
        state: SystemState, 
        turn_id: str
    ) -> None:
        """Broadcast defence response event"""
        current_turn = state.get("current_turn", {})
        defence = current_turn.get("defence")
        
        if not defence:
            return
        
        # ✓ REFACTORED: All direct property access
        defence_data = {
            'preview': defence.response_text[:200],      # Direct property
            'full_text': defence.response_text,          # Direct property
            'status_code': defence.status_code,          # Direct property
            'was_blocked': defence.was_blocked(),        # Method with logic
            'latency_ms': defence.metadata.get('latency_ms'),  # Metadata property
            'timestamp': current_turn.get("timestamp")
        }
        
        await self.ws_ops.broadcast_defence_response(
            run_id,
            turn_id,
            iteration,
            defence_data
        )
    
    async def _broadcast_evaluation(
        self, 
        run_id: str, 
        iteration: int, 
        state: SystemState, 
        turn_id: str
    ) -> None:
        """Broadcast evaluation complete event"""
        current_turn = state.get("current_turn", {})
        evaluation = current_turn.get("evaluation")
        
        if not evaluation:
            return
        
        # ✓ REFACTORED: All direct property access
        evaluation_data = {
            'score': evaluation.score,         # Direct property
            'success': evaluation.success,     # Direct property
            'category': evaluation.category,   # Direct property
            'reasoning': evaluation.reasoning, # Direct property
            'summary': evaluation.to_summary(), # Method
            'timestamp': current_turn.get("timestamp")
        }
        
        await self.ws_ops.broadcast_evaluation_complete(
            run_id,
            turn_id,
            iteration,
            evaluation_data
        )
        
        # Also broadcast turn completed
        await self.ws_ops.broadcast_turn_completed(
            run_id,
            turn_id,
            iteration
        )

        # Emit per-turn stats using context (no extra DB hit needed)
        context = state.get("strategy_context", {})
        iteration_count = context.get("iteration_count", iteration)
        successful = context.get("successful_iterations", 0)
        total = max(iteration_count, 1)
        await self.ws_ops.broadcast_to_room(run_id, "evaluation_stats_updated", {
            "type": "evaluation_stats_updated",
            "run_id": run_id,
            "stats": {
                "total_evaluations": iteration_count,
                "success_rate": successful / total if total else 0.0,
                "latest_score": evaluation.score,
                "latest_success": evaluation.success,
                "latest_category": evaluation.category,
            }
        })

    async def _broadcast_routing(
        self, 
        run_id: str, 
        state: SystemState
    ) -> None:
        """Broadcast routing decision event"""
        routing_signal = state.get("routing_signal")
        context = state.get("strategy_context", {})
        
        current = context.get("iteration_count", 0)
        total = context.get("max_iterations", current + 1)
        
        await self.ws_ops.broadcast_run_progress(
            run_id,
            current=current,
            total=total,
            message=f"Routing: {routing_signal}"
        )





# """
# Automatic WebSocket Middleware

# Handles broadcasting updates during automatic runs.
# """

# from typing import Dict, Any
# from middlewares.base import BaseMiddleware
# from server.websocket.socketio_manager import SocketIOManager
# from server.websocket.operations import get_ws_ops
# from engine.debug_utils import debug, tracer, step, warn, err
# from engine.state_schema import SystemState, RoutingSignals


# class AutomaticWSMiddleware(BaseMiddleware):
#     """
#     WebSocket middleware for automatic runs.
    
#     Streams live updates of graph activity.
#     """
    
#     def __init__(self, socketio_manager: SocketIOManager, config: Dict[str, Any] = None):
#         default_config = {
#             "broadcast_attacks": True,
#             "broadcast_defences": True,
#             "broadcast_evaluations": True
#         }
#         if config:
#             default_config.update(config)
#         super().__init__(default_config)
        
#         self.ws_ops = get_ws_ops(socketio_manager)

#     async def before_run(self, initial_state: SystemState, config: Dict[str, Any], run_id: str):
#         """Broadcast run start event"""
#         tracer("AutomaticWSMiddleware.before_run", run_id=run_id)
#         try:
#             strategy_config = initial_state.get("config", {}).get("strategy_config", {})
#             strategy_name = strategy_config.get("strategy_name", "unknown_strategy")
#             payload = initial_state.get("payload", {})
            
#             await self.ws_ops.broadcast_run_started(
#                 run_id,
#                 {
#                     'strategy': strategy_name,
#                     'intent': payload.get("intent", "unknown"),
#                     'target': payload.get("target"),
#                     'timestamp': initial_state.get("start_time")
#                 }
#             )
#             debug("Run started broadcast sent")
            
#         except Exception as e:
#             err("Error in before_run", error=str(e))
    
#     async def after_step(self, step_data, run_id):
#         """Broadcast step updates"""
#         if not step_data:
#             return
        
#         node_name = list(step_data.keys())[0]
#         node_output = step_data[node_name]
        
#         try:
#             context = node_output.get("strategy_context", {})
#             iteration = context.get("iteration_count", 0)
#             # 5-B4: turn_id lives in current_turn, not strategy_context
            # turn_id = state.get("current_turn", {}).get("turn_id") or context.get("turn_id", f"turn_{iteration}")

#             if node_name == "attack" and self.config.get("broadcast_attacks"):
#                 await self._broadcast_attack(run_id, iteration, node_output, turn_id)
            
#             elif node_name == "defence" and self.config.get("broadcast_defences"):
#                 await self._broadcast_defence(run_id, iteration, node_output, turn_id)
            
#             elif node_name == "eval" and self.config.get("broadcast_evaluations"):
#                 await self._broadcast_evaluation(run_id, iteration, node_output, turn_id)
            
#             elif node_name == "router":
#                 await self._broadcast_routing(run_id, node_output)
            
#         except Exception as e:
#             err("Error in after_step", error=str(e))
    
#     async def after_run(self, final_state, run_id):
#         """Broadcast run completion event"""
#         tracer("AutomaticWSMiddleware.after_run", run_id=run_id)
#         try:
#             context = final_state.get("strategy_context", {})
#             current_turn = final_state.get("current_turn", {})
#             routing_signal = final_state.get("routing_signal")
            
#             final_data = {
#                 'total_attempts': context.get("iteration_count", 0),
#                 'routing_signal': routing_signal,
#                 'timestamp': current_turn.get("timestamp")
#             }
            
#             if current_turn.get("evaluation"):
#                 eval_result = current_turn["evaluation"]
#                 final_data['final_evaluation'] = {
#                     'score': eval_result.get_score(),
#                     'success': eval_result.is_success(),
#                     'category': eval_result.get_category(),
#                     'summary': eval_result.to_summary()
#                 }
            
#             await self.ws_ops.broadcast_run_completed(run_id, final_data)
#             step("Run completed broadcast sent")
            
#         except Exception as e:
#             err("Error in after_run", error=str(e))
    
#     async def on_error(self, error, run_id, step_data=None):
#         """Broadcast error event"""
#         try:
#             await self.ws_ops.broadcast_run_error(
#                 run_id,
#                 error=str(error),
#                 error_type=type(error).__name__
#             )
#             debug("Error broadcast sent")
#         except Exception as e:
#             err("Error in on_error", error=str(e))
    
#     async def _broadcast_attack(self, run_id, iteration, node_output, turn_id):
#         turn = node_output.get("current_turn", {})
#         attack = turn.get("attack")
        
#         if not attack:
#             return
        
#         attack_data = {
#             'preview': attack.to_string()[:200],
#             'full_text': attack.to_string(),
#             'type': attack._infer_type() if hasattr(attack, '_infer_type') else 'text',
#             'metadata': attack.metadata,
#             'timestamp': turn.get("timestamp")
#         }
        
#         await self.ws_ops.broadcast_attack_generated(
#             run_id,
#             turn_id,
#             iteration,
#             attack_data
#         )
    
#     async def _broadcast_defence(self, run_id, iteration, node_output, turn_id):
#         turn = node_output.get("current_turn", {})
#         defence = turn.get("defence")
        
#         if not defence:
#             return
        
#         defence_data = {
#             'preview': defence.get_text()[:200],
#             'full_text': defence.get_text(),
#             'status_code': defence.status_code,
#             'was_blocked': defence.was_blocked(),
#             'latency_ms': defence.get_latency_ms() if hasattr(defence, 'get_latency_ms') else None,
#             'timestamp': turn.get("timestamp")
#         }
        
#         await self.ws_ops.broadcast_defence_response(
#             run_id,
#             turn_id,
#             iteration,
#             defence_data
#         )
    
#     async def _broadcast_evaluation(self, run_id, iteration, node_output, turn_id):
#         turn = node_output.get("current_turn", {})
#         evaluation = turn.get("evaluation")
        
#         if not evaluation:
#             return
        
#         evaluation_data = {
#             'score': evaluation.get_score(),
#             'success': evaluation.is_success(),
#             'category': evaluation.get_category(),
#             'reasoning': evaluation.get_reasoning(),
#             'summary': evaluation.to_summary(),
#             'timestamp': turn.get("timestamp")
#         }
        
#         await self.ws_ops.broadcast_evaluation_complete(
#             run_id,
#             turn_id,
#             iteration,
#             evaluation_data
#         )
        
#         # Also broadcast turn completed
#         await self.ws_ops.broadcast_turn_completed(
#             run_id,
#             turn_id,
#             iteration
#         )
    
#     async def _broadcast_routing(self, run_id, node_output):
#         routing_signal = node_output.get("routing_signal")
#         context = node_output.get("strategy_context", {})
        
#         current = context.get("iteration_count", 0) # Use iteration_count for progress
#         total = context.get("max_iterations", current + 1) # Use max_iterations for total
        
#         await self.ws_ops.broadcast_run_progress(
#             run_id,
#             current=current,
#             total=total,
#             message=f"Routing: {routing_signal}"
#         )
