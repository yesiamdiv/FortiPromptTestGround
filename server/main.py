"""
Main FastAPI Application - Updated with API Route Integration and Unified Registry"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

# Import API routers
from server.api.routes import router as api_router # Main API routes
from server.api.manual_routes import router as manual_router # Import manual routes
from server.api.discovery_routes import router as discovery_router # Discovery routes for nodes/strategies

# Database and WebSocket imports
from server.database.connection import init_db, close_db, get_db
from server.websocket.socketio_manager import get_socketio_manager
from server.run_manager import get_run_manager

# Unified registry for all components
from engine.registry import register_all_components # Use unified registration


# ============================================================================
# Application Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Startup order (runs before the server accepts any requests):
      1. Registries  - register all nodes, strategies, providers
      2. Database    - connect, ensure indexes, recover stale runs
      3. Socket.IO   - verify singleton is alive
      4. RunManager  - verify singleton is alive
    """
    # =========================================================================
    # STARTUP
    # =========================================================================
    print("Starting Adversarial Testing Engine...")

    # 1. Component registries (must come first)
    try:
        register_all_components()
        print("[OK] All components registered (nodes, strategies, providers)")
    except Exception as e:
        print(f"[FATAL] Component registration failed: {e}")
        raise  # Cannot operate without registries

    # 2. Database
    db = None
    try:
        mongo_url = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        db_name   = os.getenv("MONGODB_DB_NAME", "adversarial_testing")
        db = await init_db(mongo_url, db_name)
        print(f"[OK] Database connected ({db_name} @ {mongo_url})")
    except Exception as e:
        print(f"[WARN] Database connection failed: {e}")
        print("       Continuing startup - endpoints will return 500 individually.")

    # 2a. Ensure indexes for all collections
    if db is not None:
        try:
            await db.attacks.create_index("run_id")
            await db.attacks.create_index([("run_id", 1), ("index", 1)])
            await db.defences.create_index("run_id")
            await db.defences.create_index([("run_id", 1), ("index", 1)])
            await db.evaluations.create_index("run_id")
            await db.evaluations.create_index([("run_id", 1), ("score", -1)])
            await db.manual_sessions.create_index("run_id")
            await db.manual_sessions.create_index("session_id", unique=True)
            await db.manual_sessions.create_index("created_at")
            await db.manual_turns.create_index("session_id")
            await db.manual_turns.create_index([("session_id", 1), ("index", 1)])
            print("[OK] Database indexes ensured")
        except Exception as e:
            print(f"[WARN] Index creation: {e}")

    # 2b. Stale-run recovery - reset any run stuck in "running" from a previous crash
    if db is not None:
        try:
            run_manager = get_run_manager()
            cleanup_result = await run_manager.cleanup_zombie_runs()
            if cleanup_result["cleaned"] > 0:
                print(f"[OK] Cleaned up {cleanup_result['cleaned']} zombie run(s)")
            else:
                print("[OK] No zombie runs found")
        except Exception as e:
            print(f"[WARN] Zombie run cleanup failed: {e}")

    # 3. Socket.IO
    get_socketio_manager()
    print("[OK] Socket.IO manager ready")

    # 4. Run manager
    get_run_manager()
    print("[OK] Run manager ready")

    print("Server ready!\n")

    # =========================================================================
    yield  # server runs here
    # =========================================================================

    # SHUTDOWN
    print("\nShutting down Adversarial Testing Engine...")
    run_manager = get_run_manager()
    try:
        active_run_ids = run_manager.get_active_runs()
        if active_run_ids:
            print(f"  Stopping {len(active_run_ids)} active run(s)...")
            for run_id in active_run_ids:
                try:
                    await run_manager.stop_run(run_id)
                    print(f"  Stopped run: {run_id}")
                except Exception as e:
                    print(f"  Could not stop run {run_id}: {e}")
    except Exception as e:
        print(f"  Error during run shutdown: {e}")

    await close_db()
    print("Database connection closed")
    print("Shutdown complete")


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
# Read allowed origins from env var, falling back to localhost for development
import os as _os
_raw_origins = _os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
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
app.include_router(discovery_router, prefix="/api/v1") # Discovery routes for available nodes/strategies


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint providing basic server info."""
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



@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "fortiprompt"}


# ============================================================================
# Mount Socket.IO
# ============================================================================

socketio_manager = get_socketio_manager()
socket_app = socketio_manager.get_asgi_app()

# Mount Socket.IO at /socket.io path
app.mount("/socket.io", socket_app)


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
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