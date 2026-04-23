"""
Main FastAPI Application

Entry point for the adversarial testing engine server with Socket.IO integration.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from server.api.routes import router, set_engine
from server.database.connection import init_db, close_db
from server.websocket.socketio_manager import get_socketio_manager
from engine.workflow_engine import WorkflowEngine
from engine.graph_builder import build_default_graph
from middlewares.logging_middleware import LoggingMiddleware
from middlewares.database_middleware_v2 import DatabaseMiddlewareV2
from middlewares.websocket_middleware_v2 import WebSocketMiddlewareV2


# ============================================================================
# Application Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Handles startup and shutdown tasks.
    """
    # === STARTUP ===
    print("🚀 Starting Adversarial Testing Engine...")
    
    # 1. Initialize database
    try:
        mongo_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
        db_name = os.getenv("MONGODB_DATABASE", "adversarial_testing")
        await init_db(mongo_url, db_name)
        print("✓ Database connected")
    except Exception as e:
        print(f"⚠ Database connection failed: {e}")
    
    # 2. Initialize Socket.IO
    socketio_manager = get_socketio_manager()
    print("✓ Socket.IO initialized")
    
    # 3. Build graph
    graph = build_default_graph()
    print("✓ Graph compiled")
    
    # 4. Create middlewares (V2 versions)
    logging_mw = LoggingMiddleware({"verbose": False, "timestamps": True})
    db_mw = DatabaseMiddlewareV2()
    ws_mw = WebSocketMiddlewareV2(socketio_manager)
    
    middlewares = [logging_mw, db_mw, ws_mw]
    print("✓ Middlewares initialized")
    
    # 5. Create engine
    engine = WorkflowEngine(
        compiled_graph=graph,
        middlewares=middlewares
    )
    set_engine(engine)
    print("✓ Engine ready")
    
    print("🎉 Server ready to accept requests!\n")
    
    yield
    
    # === SHUTDOWN ===
    print("\n🛑 Shutting down Adversarial Testing Engine...")
    
    # Close database connection
    await close_db()
    print("✓ Database closed")
    
    print("👋 Shutdown complete")


# ============================================================================
# Create Application
# ============================================================================

app = FastAPI(
    title="Adversarial Testing Engine",
    description="Production-ready framework for automated adversarial testing of AI systems",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================================================
# Middleware Configuration
# ============================================================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Routes
# ============================================================================

# Include API router
app.include_router(router, prefix="/api/v1")


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Adversarial Testing Engine",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "api": "/api/v1",
        "socket_io": "/socket.io"
    }


# ============================================================================
# Mount Socket.IO
# ============================================================================

# Get Socket.IO manager and mount its ASGI app
socketio_manager = get_socketio_manager()
socket_app = socketio_manager.get_asgi_app()

# Mount Socket.IO at /socket.io path
app.mount("/socket.io", socket_app)


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Get config from environment
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8000"))
    reload = os.getenv("SERVER_RELOAD", "true").lower() == "true"
    
    print(f"\n🌐 Starting server on http://{host}:{port}")
    print(f"📚 API docs available at http://{host}:{port}/docs")
    print(f"🔌 Socket.IO available at http://{host}:{port}/socket.io\n")
    
    uvicorn.run(
        "server.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )