from .db_client import DatabaseClient
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from urllib.parse import quote_plus
from datetime import datetime
import config

def get_db_config() -> dict:
    """Gets database configuration, prioritizing provided config, then config.py."""
    if config.MONGO_URI:
        # Use provided config if available and has MONGO_URI
        return {
            'MONGO_URI': config.MONGO_URI,
            'MONGO_DB_NAME': config.MONGO_DB_NAME,
            'MONGO_USERNAME': config.MONGO_USERNAME,
            'MONGO_PASSWORD': config.MONGO_PASSWORD,
            'MONGO_HOST': config.MONGO_HOST,
            'MONGO_PORT': config.MONGO_PORT
        }
    else:
        # Fallback to config.py if no config or MONGO_URI is provided
        # Assumes config.py is available in the workspace and loads MONGO_URI and MONGO_DB_NAME
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
            print("config.py not found. Using default MongoDB URI and DB name.")
            return {
                'MONGO_URI': 'mongodb://localhost:27017/',
                'MONGO_DB_NAME': 'agentic_testing_ground',
                'MONGO_USERNAME': '',
                'MONGO_PASSWORD': '',
                'MONGO_HOST': 'localhost',
                'MONGO_PORT': 27017
            }

async def initialize_database():
    """Initializes the database connection and ensures collections exist."""
    db_config = get_db_config()
    db_client = DatabaseClient(db_config)
    try:
        await db_client.connect()
        db = db_client.get_db()

        # Check and create collections if they don't exist
        collection_names = await db.list_collection_names()
        
        required_collections = [
            'runs',
            'attack_prompts',
            'defense_responses',
            'evaluation_results'
        ] # Add other collection names here if needed
        
        for collection_name in required_collections:
            if collection_name not in collection_names:
                print(f"Collection '{collection_name}' not found. Creating...")
                # Create collection (optional, MongoDB creates on first insert, but explicit creation can set options)
                await db.create_collection(collection_name)
                print(f"Collection '{collection_name}' created.")

        print("Database initialization complete. Required collections are present.")
        return db_client

    except (ConnectionFailure, ValueError, Exception) as e:
        print(f"Database initialization failed: {e}")
        # Depending on the application's needs, you might want to exit or handle this error differently.
        raise

# Example of how to use this initialization function:
# async def main():
#     # Load your configuration (e.g., from .env or config.py)
#     config = {
#         'MONGO_URI': 'mongodb://localhost:27017/',
#         'MONGO_DB_NAME': 'agentic_testing_ground'
#     }
#     
#     try:
#         db_client = await initialize_database(config)
#         # Now you can use db_client for database operations
#         # For example:
#         # await db_client.create_run({...})
#         await db_client.close()
#     except Exception as e:
#         print(f"Failed to initialize or use database: {e}")

# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(main())
