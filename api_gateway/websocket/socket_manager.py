import socketio
from typing import Dict, List, Any
import json

class SocketIOManager:
    def __init__(self, sio: socketio.AsyncServer):
        self.sio = sio
        # A dictionary mapping run_id to a list of active SIDs (session IDs)
        self.room_sids: Dict[str, List[str]] = {}

    async def join_room(self, sid: str, room: str):
        self.sio.enter_room(sid, room)
        if room not in self.room_sids:
            self.room_sids[room] = []
        self.room_sids[room].append(sid)
        print(f"Client {sid} joined room {room}. Total clients in room: {len(self.room_sids[room])}")

    async def leave_room(self, sid: str, room: str):
        self.sio.leave_room(sid, room)
        if room in self.room_sids and sid in self.room_sids[room]:
            self.room_sids[room].remove(sid)
            if not self.room_sids[room]:
                del self.room_sids[room] # Clean up empty rooms
        print(f"Client {sid} left room {room}.")

    async def broadcast_to_room(self, room: str, event_name: str, data: Dict[str, Any]):
        """
        Broadcasts an event with data to all clients in a specific room.
        event_name: The name of the Socket.IO event (e.g., 'run_update', 'attack_progress').
        data: The payload to send.
        """
        print(f"Broadcasting event '{event_name}' to room '{room}' with data: {data}")
        await self.sio.emit(event_name, data, room=room)

    async def send_prompt_to_frontend(self, run_id: str, prompt: str):
        """Sends a prompt to the frontend via Socket.IO."""
        print(f"Sending prompt to frontend for run {run_id}")
        await self.sio.emit("new_prompt", {"run_id": run_id, "prompt": prompt}, room=run_id)

    def get_connected_sids_in_room(self, room: str) -> List[str]:
        return self.room_sids.get(room, [])

    def remove_sid_from_all_rooms(self, sid: str):
        # Iterate through all rooms and remove the sid if present
        for room in list(self.room_sids.keys()): # Iterate on a copy as dict might change during iteration
            if sid in self.room_sids[room]:
                self.room_sids[room].remove(sid)
                self.sio.leave_room(sid, room)
                if not self.room_sids[room]:
                    del self.room_sids[room]
        print(f"Client {sid} removed from all rooms.")

    def ensure_room_exists(self, room: str):
        if room not in self.room_sids:
            self.room_sids[room] = []
            print(f"Ensured room {room} exists for future connections.")
