"""
Main FastAPI Application - Updated with API Route Integration and Unified Registry
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

# Import API routers
from server.api.routes import router as api_router # Main API routes
from server.api.manual_routes import router as manual_router # Import manual routes

# Database and WebSocket imports
from server.database.connection import init_db, close_db, get_db
from server.websocket.socketio_manager import get_socketio_manager
from server.run_manager import get_run_manager

# Unified registry for all components
from engine.registry import register_all_components # Use unified registration
from engine.debug_utils import debug, err, tracer, step, checkpoint, warn


# ============================================================================
# Application Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    Handles startup and shutdown tasks, including registry initialization.
    """
    # === STARTUP ===
    tracer("Server startup initiated")
    
    # 1. Initialize database
    try:
        mongo_url = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        db_name = os.getenv("MONGODB_DB_NAME", "adversarial_testing")
        step("Initializing database", mongo_url=mongo_url, db_name=db_name)
        await init_db(mongo_url, db_name)
        checkpoint("Database connected successfully")
    except Exception as e:
        err(f"Database connection failed: {e}")
        print(f"⚠ Database connection failed: {e}")
    
    # 2. Initialize Socket.IO
    socketio_manager = get_socketio_manager()
    step("Socket.IO manager initialized")
    checkpoint("Socket.IO ready")
    
    # 3. Initialize run manager
    run_manager = get_run_manager()
    step("Run manager initialized")
    checkpoint("Run manager ready")
    
    # 4. Initialize Registries (nodes, strategies, providers)
    try:
        step("Registering all components (nodes, strategies, providers)")
        register_all_components() # Call the unified registration function
        checkpoint("All components registered")
    except Exception as e:
        err(f"Component registration failed: {e}")
        raise e # Re-raise for detailed traceback

    # 5. Restore existing runs (This part might need re-evaluation based on new state management)
    # Consider re-implementing if needed, ensuring it aligns with manual/automatic distinctions.
    # For now, skipping direct run restoration in lifespan to focus on API/Middleware setup.
    
    checkpoint("Server ready to accept requests")
    
    yield # Application runs here
    
    # === SHUTDOWN ===
    tracer("Server shutdown initiated")
    
    # Stop all active runs
    active_runs = run_manager.get_active_runs()
    step(f"Stopping {len(active_runs)} active runs")
    
    for run_id in active_runs:
        try:
            await run_manager.stop_run(run_id)
            step(f"Stopped run: {run_id}")
        except Exception as e:
            warn(f"Failed to stop run {run_id}: {e}")
    
    # Close database connection
    await close_db()
    checkpoint("Database closed")
    
    debug("Shutdown complete")


# ============================================================================
# Create Application
# ============================================================================

app = FastAPI(
    title="Adversarial Testing Engine",
    description="Production-ready framework for automated adversarial testing of AI systems",
    version="2.0.0",
    lifespan=lifespan
)


# ============================================================================
# Middleware Configuration
# ============================================================================

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Routes
# ============================================================================

# Include API routers
app.include_router(api_router, prefix="/api/v1")       # Main API routes for runs, strategies, etc.
app.include_router(manual_router, prefix="/api/v1")    # Manual session and turn management routes


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint providing basic server info."""
    debug("Root endpoint accessed")
    return {
        "name": "Adversarial Testing Engine",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "api": "/api/v1",
        "socket_io": "/socket.io",
        "description": "A framework for automated adversarial testing of AI systems.",
        "tasks_completed": [
            "Strategy interface refactoring",
            "Provider registry implementation",
            "Middleware architecture for manual/auto modes",
            "API endpoints for run and manual session management",
            "WebSocket event broadcasting for UI feedback",
            "Corrected configuration data flow and graph instantiation",
            "Enhanced manual run state management"
        ]
    }


# ============================================================================
# Mount Socket.IO
# ============================================================================

socketio_manager = get_socketio_manager()
socket_app = socketio_manager.get_asgi_app()

# Mount Socket.IO at /socket.io path
app.mount("/socket", socket_app)


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8000"))
    reload = os.getenv("SERVER_RELOAD", "true").lower() == "true"
    
    tracer(f"Starting uvicorn server", host=host, port=port)
    debug(f"API docs available at http://{host}:{port}/docs")
    debug(f"Socket.IO available at http://{host}:{port}/socket")
    
    uvicorn.run(
        "server.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
