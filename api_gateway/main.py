from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
import socketio
from socketio.asgi import ASGIApp
from typing import Dict, Any
import os

from .routes import runs, config  # Import the routes
from .websocket.socket_manager import SocketIOManager # NEW
from db.db_client import DatabaseClient
# from config import AppConfig  # Assuming your config is in config.py - No longer needed


class APIGateway:
    def __init__(self):
        self.app = FastAPI()
        self.sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
        self.sio_app = ASGIApp(self.sio, self.app)
        self.socket_manager = SocketIOManager(self.sio) # Initialize SocketIOManager
        # self.config = AppConfig() # Load configuration - No longer needed
        config = {
            "MONGO_URI": os.getenv("MONGO_URI", "mongodb://localhost:27017/"),
            "MONGO_DB_NAME": os.getenv("MONGO_DB_NAME", "testdb"),
            "MONGO_USERNAME": os.getenv("MONGO_USERNAME", "user"),
            "MONGO_PASSWORD": os.getenv("MONGO_PASSWORD", "password"),
            "MONGO_HOST": os.getenv("MONGO_HOST", "localhost"),
            "MONGO_PORT": os.getenv("MONGO_PORT", "27017"),
        }
        self.db_client = DatabaseClient(config) # Initialize DatabaseClient

        self._register_http_routes()
        self._register_socketio_events()
        self._register_startup_shutdown_events()

    def _register_http_routes(self):
        # Include your HTTP routers
        self.app.include_router(config.router, prefix="/api")
        self.app.include_router(runs.router, prefix="/api")

        @self.app.get("/")
        async def read_root():
            return {"Hello": "World from API Gateway"}

    def _register_socketio_events(self):
        # Socket.IO connection event
        @self.sio.on("connect")
        async def connect(sid, environ, auth):
            print(f"Client connected: {sid}")
            # Potentially handle authentication here
            # You might want to store some client-specific data if needed

        # Socket.IO disconnect event
        @self.sio.on("disconnect")
        async def disconnect(sid):
            print(f"Client disconnected: {sid}")
            self.socket_manager.remove_sid_from_all_rooms(sid)

        # Event for joining a specific run room
        @self.sio.on("join_run_room")
        async def join_run_room(sid, data: Dict[str, Any]):
            run_id = data.get("run_id")
            if not run_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="run_id is required to join a room.")
            
            # Optionally, verify if the run_id exists in your database
            # run_exists = await self.db_client.get_run(run_id)
            # if not run_exists:
            #     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run with ID {run_id} not found.")

            await self.socket_manager.join_room(sid, run_id)
            await self.socket_manager.broadcast_to_room(run_id, "room_joined", {"message": f"Client {sid} has joined run {run_id}."})
            print(f"Client {sid} joining room: {run_id}")

        # Event for leaving a specific run room (optional)
        @self.sio.on("leave_run_room")
        async def leave_run_room(sid, data: Dict[str, Any]):
            run_id = data.get("run_id")
            if not run_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="run_id is required to leave a room.")
            await self.socket_manager.leave_room(sid, run_id)
            await self.socket_manager.broadcast_to_room(run_id, "room_left", {"message": f"Client {sid} has left run {run_id}."})
            print(f"Client {sid} leaving room: {run_id}")

        # Example event for receiving data from frontend
        @self.sio.on("frontend_message")
        async def handle_frontend_message(sid, data: Dict[str, Any]):
            print(f"Received message from {sid}: {data}")
            # Process frontend message, e.g., trigger engine action, save to DB
            await self.sio.emit("backend_response", {"status": "received", "data": data}, room=sid)

    def _register_startup_shutdown_events(self):
        @self.app.on_event("startup")
        async def startup_event():
            await self.db_client.connect()
            print("API Gateway starting up and connected to DB.")

        @self.app.on_event("shutdown")
        async def shutdown_event():
            await self.db_client.close()
            print("API Gateway shutting down and DB connection closed.")

    def get_app(self):
        return self.sio_app

# Global instance of the APIGateway
api_gateway_instance = APIGateway()

# To be imported by other modules that need to send WebSocket messages
def get_socket_manager() -> SocketIOManager:
    return api_gateway_instance.socket_manager

def get_db_client() -> DatabaseClient:
    return api_gateway_instance.db_client

# Main execution block
if __name__ == "__main__":
    import uvicorn
    # Use the sio_app to run both FastAPI and Socket.IO
    uvicorn.run(api_gateway_instance.get_app(), host="0.0.0.0", port=8000)

