"""
Automatic WebSocket Middleware

Handles broadcasting updates during automatic runs.
"""

from typing import Dict, Any
from middlewares.base import BaseMiddleware
from server.websocket.socketio_manager import SocketIOManager
from server.websocket.operations import get_ws_ops
from engine.debug_utils import debug, tracer, step, warn, err
from engine.state_schema import SystemState, RoutingSignals


class AutomaticWSMiddleware(BaseMiddleware):
    """
    WebSocket middleware for automatic runs.
    
    Streams live updates of graph activity.
    """
    
    def __init__(self, socketio_manager: SocketIOManager, config: Dict[str, Any] = None):
        default_config = {
            "broadcast_attacks": True,
            "broadcast_defences": True,
            "broadcast_evaluations": True
        }
        if config:
            default_config.update(config)
        super().__init__(default_config)
        
        self.ws_ops = get_ws_ops(socketio_manager)

    async def before_run(self, initial_state: SystemState, config: Dict[str, Any], run_id: str):
        """Broadcast run start event"""
        tracer("AutomaticWSMiddleware.before_run", run_id=run_id)
        try:
            strategy_config = initial_state.get("config", {}).get("strategy_config", {})
            strategy_name = strategy_config.get("strategy_name", "unknown_strategy")
            payload = initial_state.get("payload", {})
            
            await self.ws_ops.broadcast_run_started(
                run_id,
                {
                    'strategy': strategy_name,
                    'intent': payload.get("intent", "unknown"),
                    'target': payload.get("target"),
                    'timestamp': initial_state.get("start_time")
                }
            )
            debug("Run started broadcast sent")
            
        except Exception as e:
            err("Error in before_run", error=str(e))
    
    async def after_step(self, step_data, run_id):
        """Broadcast step updates"""
        if not step_data:
            return
        
        node_name = list(step_data.keys())[0]
        node_output = step_data[node_name]
        
        try:
            context = node_output.get("strategy_context", {})
            iteration = context.get("iteration_count", 0)
            turn_id = context.get("turn_id", f"turn_{iteration}")

            if node_name == "attack" and self.config.get("broadcast_attacks"):
                await self._broadcast_attack(run_id, iteration, node_output, turn_id)
            
            elif node_name == "defence" and self.config.get("broadcast_defences"):
                await self._broadcast_defence(run_id, iteration, node_output, turn_id)
            
            elif node_name == "eval" and self.config.get("broadcast_evaluations"):
                await self._broadcast_evaluation(run_id, iteration, node_output, turn_id)
            
            elif node_name == "router":
                await self._broadcast_routing(run_id, node_output)
            
        except Exception as e:
            err("Error in after_step", error=str(e))
    
    async def after_run(self, final_state, run_id):
        """Broadcast run completion event"""
        tracer("AutomaticWSMiddleware.after_run", run_id=run_id)
        try:
            context = final_state.get("strategy_context", {})
            current_turn = final_state.get("current_turn", {})
            routing_signal = final_state.get("routing_signal")
            
            final_data = {
                'total_attempts': context.get("iteration_count", 0),
                'routing_signal': routing_signal,
                'timestamp': current_turn.get("timestamp")
            }
            
            if current_turn.get("evaluation"):
                eval_result = current_turn["evaluation"]
                final_data['final_evaluation'] = {
                    'score': eval_result.get_score(),
                    'success': eval_result.is_success(),
                    'category': eval_result.get_category(),
                    'summary': eval_result.to_summary()
                }
            
            await self.ws_ops.broadcast_run_completed(run_id, final_data)
            step("Run completed broadcast sent")
            
        except Exception as e:
            err("Error in after_run", error=str(e))
    
    async def on_error(self, error, run_id, step_data=None):
        """Broadcast error event"""
        try:
            await self.ws_ops.broadcast_run_error(
                run_id,
                error=str(error),
                error_type=type(error).__name__
            )
            debug("Error broadcast sent")
        except Exception as e:
            err("Error in on_error", error=str(e))
    
    async def _broadcast_attack(self, run_id, iteration, node_output, turn_id):
        turn = node_output.get("current_turn", {})
        attack = turn.get("attack")
        
        if not attack:
            return
        
        attack_data = {
            'preview': attack.to_string()[:200],
            'full_text': attack.to_string(),
            'type': attack._infer_type() if hasattr(attack, '_infer_type') else 'text',
            'metadata': attack.metadata,
            'timestamp': turn.get("timestamp")
        }
        
        await self.ws_ops.broadcast_attack_generated(
            run_id,
            turn_id,
            iteration,
            attack_data
        )
    
    async def _broadcast_defence(self, run_id, iteration, node_output, turn_id):
        turn = node_output.get("current_turn", {})
        defence = turn.get("defence")
        
        if not defence:
            return
        
        defence_data = {
            'preview': defence.get_text()[:200],
            'full_text': defence.get_text(),
            'status_code': defence.status_code,
            'was_blocked': defence.was_blocked(),
            'latency_ms': defence.get_latency_ms() if hasattr(defence, 'get_latency_ms') else None,
            'timestamp': turn.get("timestamp")
        }
        
        await self.ws_ops.broadcast_defence_response(
            run_id,
            turn_id,
            iteration,
            defence_data
        )
    
    async def _broadcast_evaluation(self, run_id, iteration, node_output, turn_id):
        turn = node_output.get("current_turn", {})
        evaluation = turn.get("evaluation")
        
        if not evaluation:
            return
        
        evaluation_data = {
            'score': evaluation.get_score(),
            'success': evaluation.is_success(),
            'category': evaluation.get_category(),
            'reasoning': evaluation.get_reasoning(),
            'summary': evaluation.to_summary(),
            'timestamp': turn.get("timestamp")
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
    
    async def _broadcast_routing(self, run_id, node_output):
        routing_signal = node_output.get("routing_signal")
        context = node_output.get("strategy_context", {})
        
        current = context.get("iteration_count", 0) # Use iteration_count for progress
        total = context.get("max_iterations", current + 1) # Use max_iterations for total
        
        await self.ws_ops.broadcast_run_progress(
            run_id,
            current=current,
            total=total,
            message=f"Routing: {routing_signal}"
        )
