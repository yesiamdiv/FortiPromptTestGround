"""
Main FastAPI Application - Updated with API Route Integration and Unified Registry"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

# Import API routers
from server.api.runs import router as runs_router
from server.api.discovery import router as discovery_router
from server.api.data import router as data_router
from server.api.manual_routes import router as manual_router

# Database and WebSocket imports
from server.database.connection import init_db, close_db
from server.websocket.socketio_manager import get_socketio_manager
from server.run_manager import get_run_manager

# Unified registry for all components
from engine.registry import register_all_components # Use unified registration
from core.env import get_settings


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
        _settings = get_settings()
        mongo_url = _settings.mongodb_uri
        db_name   = _settings.mongodb_db_name
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

    # 3. Ollama health check — auto-start if not running
    try:
        from providers.ollama_provider import OllamaProvider
        ollama = OllamaProvider({"model": "health-check"})
        ollama_ok = await ollama.ensure_running()
        if ollama_ok:
            print("[OK] Ollama is reachable")
        else:
            print("[WARN] Ollama is not available – LLM nodes will fail until it is started")
    except Exception as e:
        print(f"[WARN] Ollama health check failed: {e}")

    # 4. Socket.IO
    get_socketio_manager()
    print("[OK] Socket.IO manager ready")

    # 5. Run manager
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

# Read allowed origins from settings
_allowed_origins = get_settings().cors_origins

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
app.include_router(runs_router, prefix="/api/v1")       # Run lifecycle: create, start, stop, delete, list
app.include_router(discovery_router, prefix="/api/v1")  # Strategy, provider, and node discovery
app.include_router(data_router, prefix="/api/v1")       # Run data: attacks, defences, evaluations, stats
app.include_router(manual_router, prefix="/api/v1")     # Manual session and turn management


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
# FastAPI's CORSMiddleware handles CORS for all paths (API + /socket.io/*).
# Socket.IO is mounted at /socket.io so it only sees its own requests.
# CORS inside the SocketIOManager is set to [] — it relies entirely on
# FastAPI's CORSMiddleware for CORS headers.

socketio_manager = get_socketio_manager()
socket_app = socketio_manager.get_asgi_app()
app.mount("/socket.io", socket_app)




# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    _s = get_settings()
    host = _s.host
    port = _s.port
    reload = os.getenv("SERVER_RELOAD", "true").lower() == "true"
    
    print(f"\nStarting server on http://{host}:{port}")
    print(f"API docs available at http://{host}:{port}/docs")
    print(f"Socket.IO available at http://{host}:{port}/socket.io\n")

    uvicorn.run(
        "server.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )