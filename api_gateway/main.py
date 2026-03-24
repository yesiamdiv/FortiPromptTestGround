from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
import socketio
from socketio.asgi import ASGIApp
from typing import Dict, Any

from api_gateway.websocket.socket_manager import SocketIOManager

from .routes import runs, config  # Import the routes
from db.db_client import DatabaseClient

class APIGateway:
    def __init__(self, db_client: DatabaseClient):
        self.app = FastAPI()
        self.sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
        self.sio_app = ASGIApp(self.sio, self.app)
        self.socket_manager = SocketIOManager(self.sio) # Initialize SocketIOManager
        self.db_client = db_client

        self._register_http_routes()
        self._register_socketio_events()
        # self._register_startup_shutdown_events()

    def get_db_client(self) -> DatabaseClient:
        return self.db_client

    def _register_http_routes(self):
        # Include your HTTP routers
        self.app.include_router(config.router, prefix="/api")
        # self.app.include_router(runs.router, prefix="/api", dependencies=[Depends(self.get_db_client)])
        self.app.include_router(runs.router, prefix="/api")


        @self.app.get("/")
        async def read_root():
            return {"Hello": "World from API Gateway"}


    def _register_socketio_events(self):

        # # Event handlers for Socket.IO (example)
        # @self.sio.event
        # async def connect(sid, environ):
        #     print(f"Client connected: {sid}")

        # @self.sio.event
        # async def disconnect(sid):
        #     print(f"Client disconnected: {sid}")

        # Socket.IO connection event
        @self.sio.on("connect")
        async def connect(sid, environ, auth):
            print(f"Client connected: {sid}")
   

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

    def get_app(self):
        return self.sio_app
