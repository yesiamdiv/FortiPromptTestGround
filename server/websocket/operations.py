"""
WebSocket Operations

Broadcast operations for Socket.IO.
This module contains the actual WebSocket logic that middlewares call.
"""

from typing import Dict, Any
from server.websocket.socketio_manager import SocketIOManager
from engine.debug_utils import debug, err, tracer, step


class WebSocketOperations:
    """
    WebSocket broadcast operations.
    
    Provides clean API for broadcasting events without middlewares
    needing to know Socket.IO details.
    """
    
    def __init__(self, socketio_manager: SocketIOManager):
        """
        Initialize with Socket.IO manager.
        
        Args:
            socketio_manager: Socket.IO manager instance
        """
        tracer("WebSocketOperations initialized")
        self.sio_manager = socketio_manager
    
    # --- Automatic Run Events ---

    async def broadcast_run_started(self, run_id: str, data: Dict[str, Any]):
        """
        Broadcast run started event for automatic runs.
        """
        tracer("Broadcasting run_started", run_id=run_id)
        await self.sio_manager.broadcast_to_room(
            run_id,
            'run_started',
            {
                'type': 'run_started',
                'run_id': run_id,
                **data
            }
        )
        step("Broadcasted run_started", run_id=run_id)
    
    async def broadcast_attack_generated(
        self,
        run_id: str,
        turn_id: str,
        index: int,
        attack_data: Dict[str, Any]
    ):
        """
        Broadcast attack generation event for automatic runs.
        """
        debug("Broadcasting attack_generated", run_id=run_id, index=index)
        await self.sio_manager.broadcast_to_room(
            run_id,
            'attack_generated',
            {
                'type': 'attack_generated',
                'run_id': run_id,
                'turn_id': turn_id,
                'index': index,
                'attack': attack_data
            }
        )
    
    async def broadcast_defence_response(
        self,
        run_id: str,
        turn_id: str,
        index: int,
        defence_data: Dict[str, Any]
    ):
        """
        Broadcast defence response event for automatic runs.
        """
        debug("Broadcasting defence_response", run_id=run_id, index=index)
        await self.sio_manager.broadcast_to_room(
            run_id,
            'defence_response',
            {
                'type': 'defence_response',
                'run_id': run_id,
                'turn_id': turn_id,
                'index': index,
                'defence': defence_data
            }
        )
    
    async def broadcast_evaluation_complete(
        self,
        run_id: str,
        turn_id: str,
        index: int,
        evaluation_data: Dict[str, Any]
    ):
        """
        Broadcast evaluation completion event for automatic runs.
        """
        debug("Broadcasting evaluation_result", run_id=run_id, index=index)
        await self.sio_manager.broadcast_to_room(
            run_id,
            'evaluation_result',
            {
                'type': 'evaluation_result',
                'run_id': run_id,
                'turn_id': turn_id,
                'index': index,
                'evaluation': evaluation_data
            }
        )
    
    async def broadcast_turn_completed(
        self,
        run_id: str,
        turn_id: str,
        index: int
    ):
        """
        Broadcast turn completion event for automatic runs.
        """
        debug("Broadcasting turn_completed", run_id=run_id, index=index)
        await self.sio_manager.broadcast_to_room(
            run_id,
            'turn_completed',
            {
                'type': 'turn_completed',
                'run_id': run_id,
                'turn_id': turn_id,
                'index': index
            }
        )
    
    async def broadcast_run_progress(
        self,
        run_id: str,
        current: int,
        total: int,
        message: str = None
    ):
        """
        Broadcast general run progress for automatic runs.
        """
        debug("Broadcasting run_progress", run_id=run_id, current=current, total=total)
        await self.sio_manager.broadcast_to_room(
            run_id,
            'run_progress',
            {
                'type': 'run_progress',
                'run_id': run_id,
                'current': current,
                'total': total,
                'message': message,
                'progress_percent': (current / total * 100) if total > 0 else 0
            }
        )
    
    async def broadcast_run_completed(
        self,
        run_id: str,
        final_data: Dict[str, Any]
    ):
        """
        Broadcast run completion event (for automatic runs).
        """
        step("Broadcasting run_completed", run_id=run_id)
        await self.sio_manager.broadcast_to_room(
            run_id,
            'run_completed',
            {
                'type': 'run_completed',
                'run_id': run_id,
                **final_data
            }
        )
    
    async def broadcast_run_error(
        self,
        run_id: str,
        error: str,
        error_type: str = None
    ):
        """
        Broadcast run error event.
        """
        err("Broadcasting run_error", run_id=run_id, error=error)
        await self.sio_manager.broadcast_to_room(
            run_id,
            'run_error',
            {
                'type': 'run_error',
                'run_id': run_id,
                'error': error,
                'error_type': error_type
            }
        )
    
    # --- Manual Run Events (New) ---

    async def broadcast_manual_attack_generated(
        self,
        run_id: str,
        session_id: str,
        turn_id: str,
        index: int,
        attack_data: Dict[str, Any]
    ):
        """
        Broadcast attack generation event for manual runs (includes session_id).
        """
        debug("Broadcasting manual_attack_generated", run_id=run_id, index=index)
        await self.sio_manager.broadcast_to_room(
            session_id, # Broadcast to session room
            'manual_attack_generated',
            {
                'type': 'manual_attack_generated',
                'run_id': run_id,
                'session_id': session_id,
                'turn_id': turn_id,
                'index': index,
                'attack': attack_data
            }
        )

    async def broadcast_manual_defence_response(
        self,
        run_id: str,
        session_id: str,
        turn_id: str,
        index: int,
        defence_data: Dict[str, Any]
    ):
        """
        Broadcast defence response event for manual runs (includes session_id).
        """
        debug("Broadcasting manual_defence_response", run_id=run_id, index=index)
        await self.sio_manager.broadcast_to_room(
            session_id, # Broadcast to session room
            'manual_defence_response',
            {
                'type': 'manual_defence_response',
                'run_id': run_id,
                'session_id': session_id,
                'turn_id': turn_id,
                'index': index,
                'defence': defence_data
            }
        )

    async def broadcast_manual_evaluation_complete(
        self,
        run_id: str,
        session_id: str,
        turn_id: str,
        index: int,
        evaluation_data: Dict[str, Any]
    ):
        """
        Broadcast evaluation completion event for manual runs (includes session_id).
        """
        debug("Broadcasting manual_evaluation_complete", run_id=run_id, index=index)
        await self.sio_manager.broadcast_to_room(
            session_id, # Broadcast to session room
            'manual_evaluation_complete',
            {
                'type': 'manual_evaluation_complete',
                'run_id': run_id,
                'session_id': session_id,
                'turn_id': turn_id,
                'index': index,
                'evaluation': evaluation_data
            }
        )

    async def broadcast_manual_turn_completed(
        self,
        run_id: str,
        session_id: str,
        turn_id: str,
        index: int
    ):
        """
        Broadcast manual turn completion event (includes session_id).
        """
        step("Broadcasting manual_turn_completed", run_id=run_id, index=index)
        await self.sio_manager.broadcast_to_room(
            session_id, # Broadcast to session room
            'manual_turn_completed',
            {
                'type': 'manual_turn_completed',
                'run_id': run_id,
                'session_id': session_id,
                'turn_id': turn_id,
                'index': index
            }
        )

    async def broadcast_run_idle(
        self,
        run_id: str,
        data: Dict[str, Any]
    ):
        """
        Broadcast run idle event (for manual runs awaiting user input).
        Broadcasts to the session room (not the run room) so manual clients receive it.
        """
        debug("Broadcasting run_idle", run_id=run_id)
        session_id = data.get('session_id')
        room = session_id if session_id else run_id  # prefer session room for manual runs
        await self.sio_manager.broadcast_to_room(
            room,
            'run_idle',
            {
                'type': 'run_idle',
                'run_id': run_id,
                **data
            }
        )

    async def broadcast_new_run_available(self, run_id: str, run_summary: Dict[str, Any]):
        """
        Broadcast that a new run is available to all connections (includes run_summary).
        """
        step("Broadcasting new_run_available", run_id=run_id)
        await self.sio_manager.sio.emit(
            'new_run_available',
            {
                'type': 'new_run_available',
                'run_id': run_id,
                'run_summary': run_summary
            }
        )
    
    async def send_personal_message(
        self,
        session_id: str,
        event: str,
        data: Dict[str, Any]
    ):
        """
        Send message to specific session (direct to client). This might be for specific UI feedback.
        """
        debug("Sending personal message", session_id=session_id, event=event)
        await self.sio_manager.send_to_session(session_id, event, data)


# Convenience function
    async def broadcast_to_room(self, room: str, event: str, data: Dict[str, Any]) -> None:
        """
        Direct passthrough to sio_manager.broadcast_to_room.
        Allows middlewares to emit arbitrary events to any room without
        needing a named wrapper method for each one.
        """
        await self.sio_manager.broadcast_to_room(room, event, data)


def get_ws_ops(socketio_manager: SocketIOManager) -> WebSocketOperations:
    """
    Create WebSocketOperations instance.
    """
    debug("Creating WebSocketOperations instance")
    return WebSocketOperations(socketio_manager)
