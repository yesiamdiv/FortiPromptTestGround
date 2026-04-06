from .db_client import DatabaseClient
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from urllib.parse import quote_plus
from datetime import datetime
import config

def get_db_config() -> dict:
    if config.MONGO_URI:
        return {
            'MONGO_URI': config.MONGO_URI,
            'MONGO_DB_NAME': config.MONGO_DB_NAME,
            'MONGO_USERNAME': config.MONGO_USERNAME,
            'MONGO_PASSWORD': config.MONGO_PASSWORD,
            'MONGO_HOST': config.MONGO_HOST,
            'MONGO_PORT': config.MONGO_PORT
        }
    else:
        try:
            import config as app_config
            return {
                'MONGO_URI': app_config.MONGO_URI,
                'MONGO_DB_NAME': app_config.MONGO_DB_NAME,
                'MONGO_USERNAME': app_config.MONGO_USERNAME,
                'MONGO_PASSWORD': app_config.MONGO_PASSWORD,
                'MONGO_HOST': app_config.MONGO_HOST,
                'MONGO_PORT': app_config.MONGO_PORT
            }
        except ImportError:
            return {
                'MONGO_URI': 'mongodb://localhost:27017/',
                'MONGO_DB_NAME': 'agentic_testing_ground',
                'MONGO_USERNAME': '',
                'MONGO_PASSWORD': '',
                'MONGO_HOST': 'localhost',
                'MONGO_PORT': 27017
            }


async def initialize_database():
    db_config = get_db_config()
    db_client = DatabaseClient(db_config)
    try:
        await db_client.connect()
        db = db_client.get_db()

        collection_names = await db.list_collection_names()

        required_collections = [
            'runs',
            'attack_prompts',
            'defense_responses',
            'evaluation_results',
            # ── NEW: Manual Attack collections ────────────────────────────
            'manual_runs',      # one doc per manual run (keyed by run_id)
            'manual_sessions',  # one doc per chat session (keyed by session_id)
        ]

        for collection_name in required_collections:
            if collection_name not in collection_names:
                print(f"Collection '{collection_name}' not found. Creating...")
                await db.create_collection(collection_name)
                print(f"Collection '{collection_name}' created.")

        # Create indexes for manual collections for fast lookups
        await db['manual_runs'].create_index('run_id', unique=True, background=True)
        await db['manual_sessions'].create_index('session_id', unique=True, background=True)
        await db['manual_sessions'].create_index('run_id', background=True)

        print("Database initialization complete.")
        return db_client

    except (ConnectionFailure, ValueError, Exception) as e:
        print(f"Database initialization failed: {e}")
        raise


# ─── How to wire ManualAttackOrchestrator in app.py ──────────────────────────
#
# from limited_engine.manual_attack_orchestrator import ManualAttackOrchestrator
#
# async def main():
#     db_client = await initialize_database()
#     api_gateway = APIGateway(db_client=db_client)
#
#     orchestrator        = LimitedOrchestrator(db_client=db_client, api_gateway=api_gateway)
#     manual_orchestrator = ManualAttackOrchestrator(db_client=db_client, api_gateway=api_gateway)
#     # ManualAttackOrchestrator registers its own routes in __init__
#
#     app = api_gateway.get_app()
#     config = uvicorn.Config(app, host="0.0.0.0", port=8000)
#     server = uvicorn.Server(config)
#     await server.serve()
