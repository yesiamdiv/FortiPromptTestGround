from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
from socketio.asgi import ASGIApp

from api_gateway.websocket.socket_manager import SocketIOManager
from .routes import test
from db.db_client import DatabaseClient


class APIGateway:
    def __init__(self, db_client: DatabaseClient):
        # ✅ Create FastAPI app
        self.app = FastAPI()

        # ✅ FIX: Add CORS middleware (THIS WAS MISSING)
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:3000"],  # frontend URL
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # ✅ Socket.IO setup (already correct)
        self.sio = socketio.AsyncServer(
            async_mode="asgi",
            cors_allowed_origins="*"
        )

        # Combine FastAPI + Socket.IO
        self.sio_app = ASGIApp(self.sio, self.app)

        self.socket_manager = SocketIOManager(self.sio)
        self.db_client = db_client

        # Register routes and events
        self._register_http_routes()
        self._register_socketio_events()

    def get_db_client(self) -> DatabaseClient:
        return self.db_client

    def _register_http_routes(self):
        # API routes
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