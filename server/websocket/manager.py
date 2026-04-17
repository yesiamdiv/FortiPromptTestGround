"""
WebSocket Connection Manager

Manages WebSocket connections for real-time updates.
"""

from typing import Dict, Set, Any
from fastapi import WebSocket
import json


class WebSocketManager:
    """
    Manages WebSocket connections with room-based broadcasting.
    
    Supports:
    - Multiple connections per run (rooms)
    - Broadcasting to specific runs
    - Connection lifecycle management
    """
    
    def __init__(self):
        """Initialize the manager"""
        # Map of run_id -> set of websockets
        self.rooms: Dict[str, Set[WebSocket]] = {}
        
        # Map of websocket -> run_id for cleanup
        self.connections: Dict[WebSocket, str] = {}
    
    async def connect(self, websocket: WebSocket, run_id: str):
        """
        Accept a new WebSocket connection.
        
        Args:
            websocket: WebSocket connection
            run_id: Run ID to subscribe to
        """
        await websocket.accept()
        
        # Add to room
        if run_id not in self.rooms:
            self.rooms[run_id] = set()
        
        self.rooms[run_id].add(websocket)
        self.connections[websocket] = run_id
        
        print(f"WebSocket connected to run: {run_id}")
        
        # Send connection confirmation
        await self.send_personal(websocket, {
            "type": "connected",
            "run_id": run_id,
            "message": f"Connected to run {run_id}"
        })
    
    def disconnect(self, websocket: WebSocket):
        """
        Remove a WebSocket connection.
        
        Args:
            websocket: WebSocket to disconnect
        """
        if websocket in self.connections:
            run_id = self.connections[websocket]
            
            # Remove from room
            if run_id in self.rooms:
                self.rooms[run_id].discard(websocket)
                
                # Clean up empty rooms
                if not self.rooms[run_id]:
                    del self.rooms[run_id]
            
            # Remove from connections map
            del self.connections[websocket]
            
            print(f"WebSocket disconnected from run: {run_id}")
    
    async def send_personal(self, websocket: WebSocket, message: Dict[str, Any]):
        """
        Send message to a specific WebSocket.
        
        Args:
            websocket: Target WebSocket
            message: Message dictionary
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            print(f"Error sending to websocket: {e}")
            self.disconnect(websocket)
    
    async def broadcast(self, run_id: str, message: Dict[str, Any]):
        """
        Broadcast message to all connections in a run room.
        
        Args:
            run_id: Target run ID
            message: Message dictionary
        """
        if run_id not in self.rooms:
            return
        
        # Get list of connections (avoid modifying set during iteration)
        connections = list(self.rooms[run_id])
        
        # Send to all connections
        for websocket in connections:
            await self.send_personal(websocket, message)
    
    async def broadcast_all(self, message: Dict[str, Any]):
        """
        Broadcast message to all connected WebSockets.
        
        Args:
            message: Message dictionary
        """
        connections = list(self.connections.keys())
        
        for websocket in connections:
            await self.send_personal(websocket, message)
    
    def get_room_count(self, run_id: str) -> int:
        """
        Get number of connections in a room.
        
        Args:
            run_id: Run ID
        
        Returns:
            Number of connections
        """
        return len(self.rooms.get(run_id, set()))
    
    def get_total_connections(self) -> int:
        """
        Get total number of active connections.
        
        Returns:
            Total connection count
        """
        return len(self.connections)
    
    def get_active_runs(self) -> list:
        """
        Get list of run IDs with active connections.
        
        Returns:
            List of run IDs
        """
        return list(self.rooms.keys())


# Global WebSocket manager instance
ws_manager = WebSocketManager()


def get_ws_manager() -> WebSocketManager:
    """
    Get the global WebSocket manager instance.
    
    Returns:
        WebSocket manager
    """
    return ws_manager
