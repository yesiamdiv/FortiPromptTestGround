from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from urllib.parse import quote_plus
from pydantic import ValidationError
from datetime import datetime
from typing import Dict, Any, List

# Import Pydantic models from schemas.py
from .models import Run, RunInDB, AttackData, DefenseData, EvaluationData, Progress, RunConfig

class DatabaseClient:
    def __init__(self, config):
        self.config = config
        self.client = None
        self.db = None
        self.runs_collection = None

    async def connect(self):
        try:
            mongo_uri = self.config.get('MONGO_URI')
            if not mongo_uri:
                # Fallback to constructing URI from components if MONGO_URI is not directly provided
                username = quote_plus(self.config.get('MONGO_USERNAME', ''))
                password = quote_plus(self.config.get('MONGO_PASSWORD', ''))
                host = self.config.get('MONGO_HOST', 'localhost')
                port = self.config.get('MONGO_PORT', '27017')
                db_name = self.config.get('MONGO_DB_NAME', 'agentic_testing_ground')

                if username and password:
                    mongo_uri = f"mongodb://{username}:{password}@{host}:{port}/?retryWrites=true&w=majority"
                else:
                    mongo_uri = f"mongodb://{host}:{port}/?retryWrites=true&w=majority"
            else:
                # If MONGO_URI is provided, use it directly
                db_name = self.config.get('MONGO_DB_NAME', 'agentic_testing_ground')

            self.client = AsyncIOMotorClient(mongo_uri)
            await self.client.admin.command('ismaster') # Check connection
            self.db = self.client[db_name]
            self.runs_collection = self.db.get_collection('runs')
            print(f"Successfully connected to MongoDB database: {db_name}")
        except ConnectionFailure as e:
            print(f"Could not connect to MongoDB: {e}")
            raise
        except ValueError as e:
            print(f"Configuration error: {e}")
            raise
        except Exception as e:
            print(f"An unexpected error occurred during MongoDB connection: {e}")
            raise

    def get_db(self):
        if not self.db:
            raise ConnectionError("Database not connected. Call connect() first.")
        return self.db

    def get_runs_collection(self):
        if not self.runs_collection:
            raise ConnectionError("Runs collection not initialized. Call connect() first.")
        return self.runs_collection

    async def close(self):
        if self.client:
            self.client.close()
            print("MongoDB connection closed.")

    # --- Methods for handling large data references ---
    # These methods would interact with your external storage module.
    # For now, they are placeholders.

    # async def store_large_data(self, data: List[Dict[str, Any]]) -> str:
    #     ...
    # async def retrieve_large_data(self, reference: str) -> List[Dict[str, Any]]:
    #     ...


