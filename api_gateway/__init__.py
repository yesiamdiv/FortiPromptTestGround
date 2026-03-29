from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
import socketio
from socketio.asgi import ASGIApp
from typing import Dict, Any

from api_gateway.websocket.socket_manager import SocketIOManager

from .routes import test
from db.db_client import DatabaseClient

class APIGateway:
    def __init__(self, db_client: DatabaseClient):
        self.app = FastAPI()
        self.sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
        self.sio_app = ASGIApp(self.sio, self.app)
        self.socket_manager = SocketIOManager(self.sio)
        self.db_client = db_client

        self._register_http_routes()
        self._register_socketio_events()

    def get_db_client(self) -> DatabaseClient:
        return self.db_client

    def _register_http_routes(self):
        # self.app.include_router(config.router, prefix="/api")
        self.app.include_router(test.router, prefix="/api")

        @self.app.get("/")
        async def read_root():
            return {"Hello": "World from API Gateway"}

    def _register_socketio_events(self):
        @self.sio.on("connect")
        async def connect(sid, environ, auth):
            print(f"Client connected: {sid}")

        @self.sio.on("disconnect")
        async def disconnect(sid):
            print(f"Client disconnected: {sid}")
            self.socket_manager.remove_sid_from_all_rooms(sid)

    def get_app(self):
        return self.sio_app