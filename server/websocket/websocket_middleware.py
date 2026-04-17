"""
WebSocket Middleware

Broadcasts execution updates via WebSockets.
"""

from typing import Dict, Any
from middlewares.base import BaseMiddleware
from server.websocket.manager import WebSocketManager


class WebSocketMiddleware(BaseMiddleware):
    """
    Middleware that broadcasts execution updates to WebSocket clients.
    
    Sends real-time updates to subscribed clients as the run progresses.
    """
    
    def __init__(self, ws_manager: WebSocketManager, config: Dict[str, Any] = None):
        """
        Initialize WebSocket middleware.
        
        Args:
            ws_manager: WebSocket manager instance
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
        self.ws_manager = ws_manager
    
    async def before_run(self, initial_state, config, run_id):
        """Broadcast run start event"""
        try:
            strategy = config["configurable"]["strategy"]
            initial_payload = initial_state.get("initial_payload", {})
            
            message = {
                "type": "run_started",
                "run_id": run_id,
                "strategy": strategy.name,
                "intent": initial_payload.get("intent", "unknown"),
                "target": initial_payload.get("target"),
                "timestamp": initial_state.get("start_time")
            }
            
            await self.ws_manager.broadcast(run_id, message)
            
        except Exception as e:
            print(f"[WS Middleware] Error in before_run: {e}")
    
    async def after_step(self, step_data, run_id):
        """Broadcast step updates"""
        if not step_data:
            return
        
        node_name = list(step_data.keys())[0]
        node_output = step_data[node_name]
        
        try:
            # Broadcast attack steps
            if node_name == "attack" and self.config.get("broadcast_attacks"):
                await self._broadcast_attack(run_id, node_output)
            
            # Broadcast defence steps
            elif node_name == "defence" and self.config.get("broadcast_defences"):
                await self._broadcast_defence(run_id, node_output)
            
            # Broadcast evaluation steps
            elif node_name == "eval" and self.config.get("broadcast_evaluations"):
                await self._broadcast_evaluation(run_id, node_output)
            
            # Broadcast routing decisions
            elif node_name == "strategy_router":
                await self._broadcast_routing(run_id, node_output)
            
        except Exception as e:
            print(f"[WS Middleware] Error in after_step: {e}")
    
    async def after_run(self, final_state, run_id):
        """Broadcast run completion event"""
        try:
            context = final_state.get("strategy_context", {})
            current_turn = final_state.get("current_turn", {})
            
            message = {
                "type": "run_completed",
                "run_id": run_id,
                "total_attempts": context.get("attempt_count", 0),
                "routing_signal": final_state.get("routing_signal"),
                "timestamp": current_turn.get("timestamp")
            }
            
            # Add final evaluation if present
            if current_turn.get("evaluation"):
                eval_result = current_turn["evaluation"]
                message["final_evaluation"] = {
                    "score": eval_result.get_score(),
                    "success": eval_result.is_success(),
                    "category": eval_result.get_category(),
                    "summary": eval_result.to_summary()
                }
            
            await self.ws_manager.broadcast(run_id, message)
            
        except Exception as e:
            print(f"[WS Middleware] Error in after_run: {e}")
    
    async def on_error(self, error, run_id, step_data=None):
        """Broadcast error event"""
        try:
            message = {
                "type": "run_error",
                "run_id": run_id,
                "error": str(error),
                "error_type": type(error).__name__
            }
            
            await self.ws_manager.broadcast(run_id, message)
            
        except Exception as e:
            print(f"[WS Middleware] Error in on_error: {e}")
    
    async def _broadcast_attack(self, run_id, node_output):
        """Broadcast attack update"""
        turn = node_output.get("current_turn", {})
        attack = turn.get("attack")
        
        if not attack:
            return
        
        message = {
            "type": "attack_generated",
            "run_id": run_id,
            "turn_id": turn.get("turn_id"),
            "attack": {
                "preview": attack.to_string()[:200],  # First 200 chars
                "full_text": attack.to_string(),
                "type": attack._infer_type(),
                "metadata": attack.metadata
            },
            "timestamp": turn.get("timestamp")
        }
        
        await self.ws_manager.broadcast(run_id, message)
    
    async def _broadcast_defence(self, run_id, node_output):
        """Broadcast defence update"""
        turn = node_output.get("current_turn", {})
        defence = turn.get("defence")
        
        if not defence:
            return
        
        message = {
            "type": "defence_response",
            "run_id": run_id,
            "turn_id": turn.get("turn_id"),
            "defence": {
                "preview": defence.get_text()[:200],  # First 200 chars
                "full_text": defence.get_text(),
                "status_code": defence.status_code,
                "was_blocked": defence.was_blocked(),
                "latency_ms": defence.get_latency_ms()
            },
            "timestamp": turn.get("timestamp")
        }
        
        await self.ws_manager.broadcast(run_id, message)
    
    async def _broadcast_evaluation(self, run_id, node_output):
        """Broadcast evaluation update"""
        turn = node_output.get("current_turn", {})
        evaluation = turn.get("evaluation")
        
        if not evaluation:
            return
        
        message = {
            "type": "evaluation_complete",
            "run_id": run_id,
            "turn_id": turn.get("turn_id"),
            "evaluation": {
                "score": evaluation.get_score(),
                "success": evaluation.is_success(),
                "category": evaluation.get_category(),
                "reasoning": evaluation.get_reasoning(),
                "summary": evaluation.to_summary()
            },
            "timestamp": turn.get("timestamp")
        }
        
        await self.ws_manager.broadcast(run_id, message)
    
    async def _broadcast_routing(self, run_id, node_output):
        """Broadcast routing decision"""
        routing_signal = node_output.get("routing_signal")
        context = node_output.get("strategy_context", {})
        
        message = {
            "type": "routing_decision",
            "run_id": run_id,
            "routing_signal": routing_signal,
            "attempt_count": context.get("attempt_count"),
            "will_continue": routing_signal in ["attack", "continue"]
        }
        
        await self.ws_manager.broadcast(run_id, message)
