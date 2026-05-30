"""
Refactored Manual WebSocket Middleware

CHANGES FROM ORIGINAL:
- ✓ Uses strict SystemState typing
- ✓ Direct property access (NOT legacy getters)
- ✓ Consistent runtime_config naming
- ✓ Fixed .dict() calls to use .to_dict()
"""

from typing import Dict, Any, Optional
from middlewares.base import BaseMiddleware
from server.websocket.socketio_manager import SocketIOManager
from server.websocket.operations import get_ws_ops
from core.logging import debug, tracer, step, warn, err
from core.constants import NodeName
from engine.state import SystemState


class ManualWSMiddleware(BaseMiddleware):
    """
    WebSocket middleware for manual runs.
    
    Manages broadcasting state changes and signaling turn completion.
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
        """Broadcast run start event for manual mode"""
        tracer("ManualWSMiddleware.before_run", run_id=run_id)
        
        try:
            config_dict = state.get("config", {})
            strategy_config = config_dict.get("strategy_config", {})
            strategy_name = strategy_config.get("strategy_name", "unknown_strategy")
            payload = state.get("payload", {})
            session_id = state.get("session_id", payload.get("session_id"))
            
            if session_id:
                # Note: Server-side join_room isn't meaningful here;
                # clients join themselves via the join_session_room WS event.
                debug("Session room available", session=session_id)
            
            await self.ws_ops.broadcast_run_started(
                run_id,
                {
                    'strategy': strategy_name,
                    'intent': payload.get("intent", "unknown"),
                    'target': payload.get("target"),
                    'timestamp': state.get("start_time"),
                    'session_id': session_id
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
        """Broadcast step updates using manual-specific events"""
        if not state or not node_name:
            return
        
        try:
            context = state.get("strategy_context", {})
            iteration = context.get("iteration_count", 0)
            current_turn = state.get("current_turn", {})
            turn_id = current_turn.get("turn_id", f"turn_{iteration}")
            session_id = context.get("session_id")
            
            if not session_id:
                warn("Missing session_id, skipping manual broadcast", node=node_name)
                return
            
            if node_name == NodeName.ATTACK and self.middleware_config.get("broadcast_attacks"):
                attack = current_turn.get("attack")
                if attack:
                    attack_data = {
                        'preview': attack.to_string()[:200] if hasattr(attack, 'to_string') else str(attack)[:200],
                        'full_text': attack.to_string() if hasattr(attack, 'to_string') else str(attack),
                        'type': attack._infer_type() if hasattr(attack, '_infer_type') else 'text',
                        'metadata': attack.metadata if hasattr(attack, 'metadata') else {},
                        'timestamp': current_turn.get("timestamp")
                    }
                    await self.ws_ops.broadcast_manual_attack_generated(
                        run_id, session_id, turn_id, iteration, attack_data
                    )
            
            elif node_name == NodeName.DEFENCE and self.middleware_config.get("broadcast_defences"):
                defence = current_turn.get("defence")
                if defence:
                    defence_data = {
                        'preview': (defence.response_text if hasattr(defence, 'response_text') else str(defence))[:200],
                        'full_text': defence.response_text if hasattr(defence, 'response_text') else str(defence),
                        'status_code': defence.status_code if hasattr(defence, 'status_code') else 200,
                        'was_blocked': defence.was_blocked() if hasattr(defence, 'was_blocked') else False,
                        'metadata': defence.metadata if hasattr(defence, 'metadata') else {},
                        'timestamp': current_turn.get("timestamp")
                    }
                    await self.ws_ops.broadcast_manual_defence_response(
                        run_id, session_id, turn_id, iteration, defence_data
                    )
            
            elif node_name == NodeName.EVAL and self.middleware_config.get("broadcast_evaluations"):
                evaluation = current_turn.get("evaluation")
                if evaluation:
                    eval_data = {
                        'score': evaluation.score if hasattr(evaluation, 'score') else 0.0,
                        'success': evaluation.success if hasattr(evaluation, 'success') else False,
                        'category': evaluation.category if hasattr(evaluation, 'category') else 'unknown',
                        'reasoning': evaluation.reasoning if hasattr(evaluation, 'reasoning') else '',
                        'label': 'breached' if (hasattr(evaluation, 'success') and evaluation.success) else 'blocked',
                        'metadata': evaluation.metadata if hasattr(evaluation, 'metadata') else {},
                        'timestamp': current_turn.get("timestamp")
                    }
                    await self.ws_ops.broadcast_manual_evaluation_complete(
                        run_id, session_id, turn_id, iteration, eval_data
                    )
            
            elif node_name == NodeName.ROUTER:
                await self.ws_ops.broadcast_run_progress(
                    run_id,
                    current=iteration,
                    total=context.get("max_turns", iteration + 1),
                    message=f"Routing: {state.get('routing_signal')}"
                )
            
        except Exception as e:
            err("Error in after_step", error=str(e), node=node_name)

    async def after_run(
        self, 
        state: SystemState, 
        run_id: str
    ) -> None:
        """Broadcast run idle event for manual runs after a turn completes"""
        tracer("ManualWSMiddleware.after_run", run_id=run_id)
        
        try:
            context = state.get("strategy_context", {})
            current_turn = state.get("current_turn", {})
            session_id = context.get("session_id")
            
            if not session_id:
                warn("Missing session_id in final_state, cannot broadcast run_idle")
                return
            
            await self.ws_ops.broadcast_run_idle(
                run_id,
                {
                    'message': 'Awaiting user input for next turn',
                    'last_turn_id': current_turn.get("turn_id"),
                    'iteration_count': context.get("iteration_count", 0),
                    'session_id': session_id
                }
            )
            debug("Run idle broadcast sent")
            
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
