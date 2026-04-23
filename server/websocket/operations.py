"""
WebSocket Operations

Broadcast operations for Socket.IO.
This module contains the actual WebSocket logic that middlewares call.
"""

from typing import Dict, Any
from server.websocket.socketio_manager import SocketIOManager


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
        self.sio_manager = socketio_manager
    
    async def broadcast_run_started(self, run_id: str, data: Dict[str, Any]):
        """
        Broadcast run started event.
        
        Args:
            run_id: Run identifier
            data: Event data including strategy, intent, etc.
        """
        await self.sio_manager.broadcast_to_room(
            run_id,
            'run_started',
            {
                'type': 'run_started',
                'run_id': run_id,
                **data
            }
        )
    
    async def broadcast_attack_generated(
        self,
        run_id: str,
        turn_id: str,
        index: int,
        attack_data: Dict[str, Any]
    ):
        """
        Broadcast attack generation event.
        
        Args:
            run_id: Run identifier
            turn_id: Turn identifier
            index: Attack iteration number
            attack_data: Attack data (prompt, metadata)
        """
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
        Broadcast defence response event.
        
        Args:
            run_id: Run identifier
            turn_id: Turn identifier
            index: Defence iteration number
            defence_data: Defence data (response, blocked status)
        """
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
        Broadcast evaluation completion event.
        
        Args:
            run_id: Run identifier
            turn_id: Turn identifier
            index: Evaluation iteration number
            evaluation_data: Evaluation data (score, success, feedback)
        """
        await self.sio_manager.broadcast_to_room(
            run_id,
            'evaluation_complete',
            {
                'type': 'evaluation_complete',
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
        Broadcast turn completion event.
        
        Args:
            run_id: Run identifier
            turn_id: Turn identifier
            index: Turn iteration number
        """
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
        Broadcast general run progress.
        
        Args:
            run_id: Run identifier
            current: Current iteration
            total: Total iterations
            message: Optional progress message
        """
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
        Broadcast run completion event.
        
        Args:
            run_id: Run identifier
            final_data: Final run data (total attempts, scores, etc.)
        """
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
        
        Args:
            run_id: Run identifier
            error: Error message
            error_type: Optional error type/category
        """
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
    
    async def broadcast_run_data_synced(
        self,
        run_id: str,
        data_summary: Dict[str, Any]
    ):
        """
        Broadcast data synchronization event.
        
        Args:
            run_id: Run identifier
            data_summary: Summary of synced data
        """
        await self.sio_manager.broadcast_to_room(
            run_id,
            'run_data_synced',
            {
                'type': 'run_data_synced',
                'run_id': run_id,
                **data_summary
            }
        )
    
    async def broadcast_new_run_available(self, run_id: str):
        """
        Broadcast that a new run is available.
        
        Broadcasts to all connections (not just a specific room).
        
        Args:
            run_id: Run identifier
        """
        # This goes to all connected clients
        await self.sio_manager.sio.emit(
            'new_run_available',
            {
                'type': 'new_run_available',
                'run_id': run_id
            }
        )
    
    async def send_personal_message(
        self,
        session_id: str,
        event: str,
        data: Dict[str, Any]
    ):
        """
        Send message to specific session.
        
        Args:
            session_id: Session identifier
            event: Event name
            data: Event data
        """
        await self.sio_manager.send_to_session(session_id, event, data)


# Convenience function
def get_ws_ops(socketio_manager: SocketIOManager) -> WebSocketOperations:
    """
    Create WebSocket operations instance.
    
    Args:
        socketio_manager: Socket.IO manager
    
    Returns:
        WebSocketOperations instance
    """
    return WebSocketOperations(socketio_manager)