"""
WebSocket Middleware - Refactored

Uses server/websocket/operations.py for actual WebSocket logic.
Middleware only orchestrates - doesn't implement WebSocket operations.
"""

from typing import Dict, Any
from middlewares.base import BaseMiddleware
from server.websocket.socketio_manager import SocketIOManager
from server.websocket.operations import get_ws_ops


class WebSocketMiddlewareV2(BaseMiddleware):
    """
    Refactored middleware using WebSocket operations module.
    
    Broadcasts execution updates via Socket.IO.
    """
    
    def __init__(self, socketio_manager: SocketIOManager, config: Dict[str, Any] = None):
        """
        Initialize WebSocket middleware.
        
        Args:
            socketio_manager: Socket.IO manager instance
            config: Configuration including:
                - broadcast_attacks: Whether to broadcast attack data (default: True)
                - broadcast_defences: Whether to broadcast defence data (default: True)
                - broadcast_evaluations: Whether to broadcast evaluation data (default: True)
        """
        default_config = {
            "broadcast_attacks": True,
            "broadcast_defences": True,
            "broadcast_evaluations": True
        }
        
        if config:
            default_config.update(config)
        
        super().__init__(default_config)
        
        # Get operations instance
        self.ws_ops = get_ws_ops(socketio_manager)
        self._iteration_counters = {}  # Track iteration numbers per run
    
    async def before_run(self, initial_state, config, run_id):
        """Broadcast run start event"""
        try:
            strategy = config["configurable"]["strategy"]
            initial_payload = initial_state.get("initial_payload", {})
            
            # Initialize iteration counter
            self._iteration_counters[run_id] = 0
            
            await self.ws_ops.broadcast_run_started(
                run_id,
                {
                    'strategy': strategy.name,
                    'intent': initial_payload.get("intent", "unknown"),
                    'target': initial_payload.get("target"),
                    'timestamp': initial_state.get("start_time")
                }
            )
            
        except Exception as e:
            print(f"[WS Middleware] Error in before_run: {e}")
    
    async def after_step(self, step_data, run_id):
        """Broadcast step updates"""
        if not step_data:
            return
        
        node_name = list(step_data.keys())[0]
        node_output = step_data[node_name]
        
        try:
            # Get current iteration
            iteration = self._iteration_counters.get(run_id, 0)
            
            # Broadcast based on node type
            if node_name == "attack" and self.config.get("broadcast_attacks"):
                await self._broadcast_attack(run_id, iteration, node_output)
                # Increment after attack
                self._iteration_counters[run_id] = iteration + 1
            
            elif node_name == "defence" and self.config.get("broadcast_defences"):
                await self._broadcast_defence(run_id, iteration, node_output)
            
            elif node_name == "eval" and self.config.get("broadcast_evaluations"):
                await self._broadcast_evaluation(run_id, iteration, node_output)
            
            elif node_name == "strategy_router":
                await self._broadcast_routing(run_id, node_output)
            
        except Exception as e:
            print(f"[WS Middleware] Error in after_step: {e}")
    
    async def after_run(self, final_state, run_id):
        """Broadcast run completion event"""
        try:
            context = final_state.get("strategy_context", {})
            current_turn = final_state.get("current_turn", {})
            
            final_data = {
                'total_attempts': context.get("attempt_count", 0),
                'routing_signal': final_state.get("routing_signal"),
                'timestamp': current_turn.get("timestamp")
            }
            
            # Add final evaluation if present
            if current_turn.get("evaluation"):
                eval_result = current_turn["evaluation"]
                final_data['final_evaluation'] = {
                    'score': eval_result.get_score(),
                    'success': eval_result.is_success(),
                    'category': eval_result.get_category(),
                    'summary': eval_result.to_summary()
                }
            
            await self.ws_ops.broadcast_run_completed(run_id, final_data)
            
            # Clean up counter
            self._iteration_counters.pop(run_id, None)
            
        except Exception as e:
            print(f"[WS Middleware] Error in after_run: {e}")
    
    async def on_error(self, error, run_id, step_data=None):
        """Broadcast error event"""
        try:
            await self.ws_ops.broadcast_run_error(
                run_id,
                error=str(error),
                error_type=type(error).__name__
            )
            
            # Clean up counter
            self._iteration_counters.pop(run_id, None)
            
        except Exception as e:
            print(f"[WS Middleware] Error in on_error: {e}")
    
    async def _broadcast_attack(self, run_id, iteration, node_output):
        """Broadcast attack update using operations"""
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
            turn.get("turn_id", f"turn_{iteration}"),
            iteration,
            attack_data
        )
    
    async def _broadcast_defence(self, run_id, iteration, node_output):
        """Broadcast defence update using operations"""
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
            turn.get("turn_id", f"turn_{iteration}"),
            iteration,
            defence_data
        )
    
    async def _broadcast_evaluation(self, run_id, iteration, node_output):
        """Broadcast evaluation update using operations"""
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
            turn.get("turn_id", f"turn_{iteration}"),
            iteration,
            evaluation_data
        )
        
        # Also broadcast turn completed
        await self.ws_ops.broadcast_turn_completed(
            run_id,
            turn.get("turn_id", f"turn_{iteration}"),
            iteration
        )
    
    async def _broadcast_routing(self, run_id, node_output):
        """Broadcast routing decision"""
        routing_signal = node_output.get("routing_signal")
        context = node_output.get("strategy_context", {})
        
        # Broadcast as progress update
        current = context.get("attempt_count", 0)
        total = context.get("max_attempts", current + 1)
        
        await self.ws_ops.broadcast_run_progress(
            run_id,
            current=current,
            total=total,
            message=f"Routing: {routing_signal}"
        )