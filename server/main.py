"""
Main FastAPI Application - Updated

Entry point with startup initialization for existing runs.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from server.api.routes import router as main_router
from server.api.attack_routes import router as attack_router
from server.api.defense_routes import router as defense_router
from server.database.connection import init_db, close_db, get_db
from server.websocket.socketio_manager import get_socketio_manager
from server.run_manager import get_run_manager


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
        mongo_url = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        db_name = os.getenv("MONGODB_DB_NAME", "adversarial_testing")
        await init_db(mongo_url, db_name)
        print("✓ Database connected")
    except Exception as e:
        print(f"⚠ Database connection failed: {e}")
    
    # 2. Initialize Socket.IO
    socketio_manager = get_socketio_manager()
    print("✓ Socket.IO initialized")
    
    # 3. Initialize run manager
    run_manager = get_run_manager()
    print("✓ Run manager initialized")
    
    # 4. Restore existing runs
    await restore_existing_runs(socketio_manager, run_manager)
    
    print("🎉 Server ready to accept requests!\n")
    
    yield
    
    # === SHUTDOWN ===
    print("\n🛑 Shutting down Adversarial Testing Engine...")
    
    # Stop all active runs
    run_manager = get_run_manager()
    active_runs = run_manager.get_active_runs()
    
    for run_id in active_runs:
        try:
            await run_manager.stop_run(run_id)
            print(f"✓ Stopped run: {run_id}")
        except Exception as e:
            print(f"⚠ Failed to stop run {run_id}: {e}")
    
    # Close database connection
    await close_db()
    print("✓ Database closed")
    
    print("👋 Shutdown complete")


async def restore_existing_runs(socketio_manager, run_manager):
    """
    Restore existing runs on startup.
    
    This function:
    1. Fetches all runs from database
    2. Creates Socket.IO rooms for each run
    3. Tracks active/running runs
    4. Optionally resumes interrupted runs
    """
    print("\n📦 Restoring existing runs...")
    
    db = get_db()
    if db is None:
        print("⚠ Cannot restore runs - database not connected")
        return
    
    try:
        # Fetch all runs
        runs_cursor = db.runs.find({})
        runs = await runs_cursor.to_list(length=None)
        
        print(f"Found {len(runs)} existing runs in database")
        
        # Track statistics
        stats = {
            "total": len(runs),
            "idle": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "stopped": 0,
            "rooms_created": 0
        }
        
        for run in runs:
            run_id = run["run_id"]
            status = run.get("status", "idle")
            
            # Count by status
            stats[status] = stats.get(status, 0) + 1
            
            # Create Socket.IO room for this run
            # Note: Rooms are created implicitly when clients join,
            # but we can track them in the manager
            socketio_manager.run_rooms[run_id] = set()
            stats["rooms_created"] += 1
            
            # Handle runs that were interrupted
            if status == "running":
                print(f"  ⚠ Run {run_id} was interrupted (status: running)")
                
                # Option 1: Mark as stopped
                from server.database.operations import get_db_ops
                db_ops = get_db_ops(db)
                await db_ops.update_run(run_id, {
                    "status": "stopped",
                    "error": "Server restart - run was interrupted"
                })
                print(f"    → Marked as stopped")
                
                # Option 2: Auto-resume (uncomment to enable)
                # try:
                #     print(f"    → Attempting to resume...")
                #     # Get strategy and config
                #     strategy_name = run.get("strategy", "default")
                #     strategy_config = run.get("config", {}).get("strategy_config", {})
                #     initial_payload = {
                #         "intent": run.get("intent", ""),
                #         "target": run.get("target")
                #     }
                #     
                #     await run_manager.start_run(
                #         run_id=run_id,
                #         strategy_name=strategy_name,
                #         strategy_config=strategy_config,
                #         initial_payload=initial_payload
                #     )
                #     print(f"    ✓ Resumed successfully")
                # except Exception as e:
                #     print(f"    ✗ Resume failed: {e}")
        
        # Print summary
        print("\n📊 Run restoration summary:")
        print(f"  Total runs: {stats['total']}")
        print(f"  Idle: {stats.get('idle', 0)}")
        print(f"  Running: {stats.get('running', 0)} (marked as stopped)")
        print(f"  Paused: {stats.get('paused', 0)}")
        print(f"  Completed: {stats.get('completed', 0)}")
        print(f"  Failed: {stats.get('failed', 0)}")
        print(f"  Stopped: {stats.get('stopped', 0)}")
        print(f"  Socket.IO rooms created: {stats['rooms_created']}")
        print("")
        
    except Exception as e:
        print(f"❌ Error during run restoration: {e}")
        import traceback
        traceback.print_exc()


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
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Routes
# ============================================================================

# Include API routers
app.include_router(main_router, prefix="/api/v1")
app.include_router(attack_router, prefix="/api/v1")
app.include_router(defense_router, prefix="/api/v1")


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Adversarial Testing Engine",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "api": "/api/v1",
        "socket_io": "/socket.io",
        "changes": [
            "Separated run creation from execution",
            "Added lifecycle endpoints: start, pause, resume, stop",
            "Added attack and defense configuration endpoints",
            "Auto-restore runs on startup",
            "Per-run engine isolation"
        ]
    }


# ============================================================================
# Mount Socket.IO
# ============================================================================

# Get Socket.IO manager and mount its ASGI app
socketio_manager = get_socketio_manager()
socket_app = socketio_manager.get_asgi_app()

# Mount Socket.IO at /socket.io path
app.mount("/socket", socket_app)


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    # Get config from environment
    host = os.getenv("SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("SERVER_PORT", "8000"))
    reload = os.getenv("SERVER_RELOAD", "false").lower() == "true"  # Disabled by default
    
    print(f"\n🌐 Starting server on http://{host}:{port}")
    print(f"📚 API docs available at http://{host}:{port}/docs")
    print(f"🔌 Socket.IO available at http://{host}:{port}/socket\n")
    
    uvicorn.run(
        "server.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )

