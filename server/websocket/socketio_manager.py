"""
Socket.IO Manager

Manages Socket.IO connections for real-time communication.
Replaces FastAPI WebSockets with Socket.IO for better compatibility.
"""

import socketio
from typing import Dict, Set, Any, Optional
from core.logging import debug, err, tracer, step, checkpoint


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
        tracer("Initializing SocketIOManager")

        # cors_allowed_origins must be set here — socket.io's ASGIApp intercepts
        # /socket.io/* before FastAPI's CORSMiddleware ever runs, so it has to do
        # its own CORS. An empty list means "deny all", causing 404 on the handshake.
        from core.env import get_settings
        _origins = get_settings().cors_origins  # same list used by FastAPI

        # Create Socket.IO server with ASGI mode
        self.sio = socketio.AsyncServer(
            async_mode='asgi',
            cors_allowed_origins=_origins,
            logger=False,
            engineio_logger=False,
            max_http_buffer_size=10000000,
        )
        
        # Track connections per run
        self.run_rooms: Dict[str, Set[str]] = {}  # run_id -> set of session_ids
        self.session_runs: Dict[str, str] = {}  # session_id -> run_id
        
        # Register event handlers
        self._register_handlers()
        checkpoint("SocketIOManager ready")
    
    def _register_handlers(self):
        """Register Socket.IO event handlers"""
        
        @self.sio.event
        async def connect(sid, environ):
            """Handle client connection"""
            debug("Socket.IO client connected", sid=sid)
            await self.sio.emit('connected', {
                'status': 'connected',
                'session_id': sid
            }, to=sid)
        
        @self.sio.event
        async def disconnect(sid):
            """Handle client disconnection"""
            debug("Socket.IO client disconnected", sid=sid)
            
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
            tracer("Client joining room", sid=sid)
            try:
                run_id = data.get('run_id') or data.get('runId')  # accept both during transition
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
                
                step("Client joined room", run_id=run_id, sid=sid)
                
                await self.sio.emit('room_joined', {
                    'run_id': run_id,
                    'message': f'Joined room for run {run_id}'
                }, to=sid)

            except Exception as e:
                err(f"Error joining room: {e}")
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
            debug("Client leaving room", sid=sid)
            try:
                run_id = data.get('run_id') or data.get('runId')  # accept both during transition
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
                
                debug("Client left room", run_id=run_id, sid=sid)
                
                await self.sio.emit('room_left', {
                    'run_id': run_id,
                    'message': f'Left room for run {run_id}'
                }, to=sid)
                
            except Exception as e:
                err(f"Error leaving room: {e}")
        
        @self.sio.event
        async def join_run_channel(sid, data):
            """Alias for join_run_room — accepts the frontend's event name."""
            await join_run_room(sid, data)

        @self.sio.event
        async def leave_run_channel(sid, data):
            """Alias for leave_run_room — accepts the frontend's event name."""
            await leave_run_room(sid, data)

        @self.sio.event
        async def join_session_room(sid, data):
            """
            Join a session-specific room (for manual runs).

            Data format:
            {
                "session_id": "sess_abc123"
            }
            """
            tracer("Client joining session room", sid=sid)
            try:
                session_id = data.get('session_id')
                if not session_id:
                    await self.sio.emit('error', {
                        'message': 'session_id is required'
                    }, to=sid)
                    return

                await self.sio.enter_room(sid, session_id)
                step("Client joined session room", session_id=session_id, sid=sid)

                await self.sio.emit('session_room_joined', {
                    'session_id': session_id,
                    'message': f'Joined room for session {session_id}'
                }, to=sid)

            except Exception as e:
                err(f"Error joining session room: {e}")
                await self.sio.emit('error', {'message': str(e)}, to=sid)

        @self.sio.event
        async def leave_session_room(sid, data):
            """
            Leave a session-specific room.

            Data format:
            {
                "session_id": "sess_abc123"
            }
            """
            debug("Client leaving session room", sid=sid)
            try:
                session_id = data.get('session_id')
                if session_id:
                    await self.sio.leave_room(sid, session_id)
                    debug("Client left session room", session_id=session_id, sid=sid)
            except Exception as e:
                err(f"Error leaving session room: {e}")

        @self.sio.event
        async def ping(sid, data):
            """Handle ping for connection health check"""
            debug("Ping received", sid=sid)
            await self.sio.emit('pong', {'timestamp': data.get('timestamp')}, to=sid)
    
    async def broadcast_to_room(self, run_id: str, event: str, data: Dict[str, Any]):
        """
        Broadcast event to all clients in a run room.
        
        Args:
            run_id: Run identifier
            event: Event name
            data: Data to send
        """
        tracer("Broadcasting to room", run_id=run_id, event=event)
        try:
            await self.sio.emit(event, data, room=run_id)
            step("Broadcasted to room", run_id=run_id, event=event)
        except Exception as e:
            err(f"Broadcast error: {e}")
    
    async def send_to_session(self, session_id: str, event: str, data: Dict[str, Any]):
        """
        Send event to specific session.
        
        Args:
            session_id: Session identifier
            event: Event name
            data: Data to send
        """
        tracer("Sending to session", session_id=session_id, event=event)
        try:
            await self.sio.emit(event, data, to=session_id)
            step("Sent to session", session_id=session_id, event=event)
        except Exception as e:
            err(f"Send error: {e}")
    
    def get_room_count(self, run_id: str) -> int:
        """
        Get number of clients in a room.
        
        Args:
            run_id: Run identifier
        
        Returns:
            Number of connected clients
        """
        debug("Getting room count", run_id=run_id)
        return len(self.run_rooms.get(run_id, set()))
    
    def get_total_connections(self) -> int:
        """
        Get total number of connections.
        
        Returns:
            Total connection count
        """
        debug("Getting total connections")
        return len(self.session_runs)
    
    def get_active_runs(self) -> list:
        """
        Get list of runs with active connections.
        
        Returns:
            List of run IDs
        """
        debug("Getting active runs")
        return list(self.run_rooms.keys())
    
    # def get_asgi_app(self, other_asgi_app=None):
    #     """
    #     Return a socketio.ASGIApp that wraps self.sio. 
    #     Pass other_asgi_app=<FastAPI app> so non-socket requests fall through.
    #     """
    #     debug("Getting ASGI app")
    #     return socketio.ASGIApp(
    #         socketio_server=self.sio,
    #         other_asgi_app=other_asgi_app,
    #         socketio_path="socket.io",
    #     )
    def get_asgi_app(self):
        """
        Get ASGI app for Socket.IO.
        
        Returns:
            Socket.IO ASGI app
        """
        debug("Getting ASGI app")
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