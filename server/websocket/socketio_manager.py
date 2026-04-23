"""
Socket.IO Manager

Manages Socket.IO connections for real-time communication.
Replaces FastAPI WebSockets with Socket.IO for better compatibility.
"""

import socketio
from typing import Dict, Set, Any, Optional


class SocketIOManager:
    """
    Manages Socket.IO server and connections.
    
    Features:
    - Room-based broadcasting
    - Connection management
    - Event handling
    - Automatic reconnection support
    """
    
    def __init__(self):
        """Initialize Socket.IO server"""
        # Create Socket.IO server with ASGI mode
        self.sio = socketio.AsyncServer(
            async_mode='asgi',
            cors_allowed_origins='*',  # Configure as needed
            logger=False,
            engineio_logger=False
        )
        
        # Track connections per run
        self.run_rooms: Dict[str, Set[str]] = {}  # run_id -> set of session_ids
        self.session_runs: Dict[str, str] = {}  # session_id -> run_id
        
        # Register event handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register Socket.IO event handlers"""
        
        @self.sio.event
        async def connect(sid, environ):
            """Handle client connection"""
            print(f"🔌 Socket.IO client connected: {sid}")
            await self.sio.emit('connected', {
                'status': 'connected',
                'session_id': sid
            }, to=sid)
        
        @self.sio.event
        async def disconnect(sid):
            """Handle client disconnection"""
            print(f"🔌 Socket.IO client disconnected: {sid}")
            
            # Clean up room membership
            if sid in self.session_runs:
                run_id = self.session_runs[sid]
                if run_id in self.run_rooms:
                    self.run_rooms[run_id].discard(sid)
                    if not self.run_rooms[run_id]:
                        del self.run_rooms[run_id]
                del self.session_runs[sid]
        
        @self.sio.event
        async def join_run_room(sid, data):
            """
            Join a run-specific room.
            
            Data format:
            {
                "run_id": "run_abc123"
            }
            """
            try:
                run_id = data.get('run_id')
                if not run_id:
                    await self.sio.emit('error', {
                        'message': 'run_id is required'
                    }, to=sid)
                    return
                
                # Enter room
                await self.sio.enter_room(sid, run_id)
                
                # Track membership
                if run_id not in self.run_rooms:
                    self.run_rooms[run_id] = set()
                self.run_rooms[run_id].add(sid)
                self.session_runs[sid] = run_id
                
                print(f"👥 Client {sid} joined room: {run_id}")
                
                await self.sio.emit('room_joined', {
                    'run_id': run_id,
                    'message': f'Joined room for run {run_id}'
                }, to=sid)
                
            except Exception as e:
                print(f"❌ Error joining room: {e}")
                await self.sio.emit('error', {
                    'message': str(e)
                }, to=sid)
        
        @self.sio.event
        async def leave_run_room(sid, data):
            """
            Leave a run-specific room.
            
            Data format:
            {
                "run_id": "run_abc123"
            }
            """
            try:
                run_id = data.get('run_id')
                if not run_id:
                    return
                
                # Leave room
                await self.sio.leave_room(sid, run_id)
                
                # Update tracking
                if run_id in self.run_rooms:
                    self.run_rooms[run_id].discard(sid)
                    if not self.run_rooms[run_id]:
                        del self.run_rooms[run_id]
                
                if sid in self.session_runs and self.session_runs[sid] == run_id:
                    del self.session_runs[sid]
                
                print(f"👥 Client {sid} left room: {run_id}")
                
                await self.sio.emit('room_left', {
                    'run_id': run_id,
                    'message': f'Left room for run {run_id}'
                }, to=sid)
                
            except Exception as e:
                print(f"❌ Error leaving room: {e}")
        
        @self.sio.event
        async def ping(sid, data):
            """Handle ping for connection health check"""
            await self.sio.emit('pong', {'timestamp': data.get('timestamp')}, to=sid)
    
    async def broadcast_to_room(self, run_id: str, event: str, data: Dict[str, Any]):
        """
        Broadcast event to all clients in a run room.
        
        Args:
            run_id: Run identifier
            event: Event name
            data: Data to send
        """
        try:
            await self.sio.emit(event, data, room=run_id)
        except Exception as e:
            print(f"❌ Broadcast error: {e}")
    
    async def send_to_session(self, session_id: str, event: str, data: Dict[str, Any]):
        """
        Send event to specific session.
        
        Args:
            session_id: Session identifier
            event: Event name
            data: Data to send
        """
        try:
            await self.sio.emit(event, data, to=session_id)
        except Exception as e:
            print(f"❌ Send error: {e}")
    
    def get_room_count(self, run_id: str) -> int:
        """
        Get number of clients in a room.
        
        Args:
            run_id: Run identifier
        
        Returns:
            Number of connected clients
        """
        return len(self.run_rooms.get(run_id, set()))
    
    def get_total_connections(self) -> int:
        """
        Get total number of connections.
        
        Returns:
            Total connection count
        """
        return len(self.session_runs)
    
    def get_active_runs(self) -> list:
        """
        Get list of runs with active connections.
        
        Returns:
            List of run IDs
        """
        return list(self.run_rooms.keys())
    
    def get_asgi_app(self):
        """
        Get ASGI app for Socket.IO.
        
        Returns:
            Socket.IO ASGI app
        """
        return socketio.ASGIApp(self.sio)


# Global Socket.IO manager instance
_socketio_manager: Optional[SocketIOManager] = None


def get_socketio_manager() -> SocketIOManager:
    """
    Get the global Socket.IO manager instance.
    
    Returns:
        SocketIOManager instance
    """
    global _socketio_manager
    if _socketio_manager is None:
        _socketio_manager = SocketIOManager()
    return _socketio_manager


def create_socketio_manager() -> SocketIOManager:
    """
    Create a new Socket.IO manager instance.
    
    Returns:
        New SocketIOManager instance
    """
    return SocketIOManager()