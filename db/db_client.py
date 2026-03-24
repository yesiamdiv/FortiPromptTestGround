from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from urllib.parse import quote_plus
from pydantic import ValidationError
from datetime import datetime
from typing import Dict, Any, List, Optional
from bson import ObjectId

# Import Pydantic models from schemas.py
from .models import Run, RunInDB, AttackData, DefenseData, EvaluationData, Progress, RunConfig
from config import MONGO_URI, MONGO_DB_NAME
from db.models import ArenaState

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

 
    async def create_run(self, run_data: Dict[str, Any]) -> str:
        """Creates a new run document in the database."""
        run_id = run_data.get('run_id')
        if not run_id:
            raise ValueError("run_id is required")

        # Ensure the run_id is unique before inserting
        existing_run = await self.runs_collection.find_one({{"run_id": run_id}})
        if existing_run:
            raise ValueError(f"Run with id {run_id} already exists")

        result = await self.runs_collection.insert_one(run_data)
        return str(result.inserted_id)

    async def get_run(self, run_id: str) -> Optional[Run]:
        """Retrieves a single run by its ID."""
        run_data = await self.runs_collection.find_one({{"run_id": run_id}})
        if run_data:
            return Run(**run_data)
        return None

    async def get_runs(self) -> List[Run]:
        """Retrieves all runs from the database."""
        runs_data = await self.runs_collection.find().to_list(length=None)
        return [Run(**run) for run in runs_data]

    async def update_run(self, run_id: str, update_data: Dict[str, Any]) -> bool:
        """Updates an existing run document."""
        result = await self.runs_collection.update_one({{"run_id": run_id}}, {{"\$set": update_data}})
        return result.modified_count > 0

    async def delete_run(self, run_id: str) -> bool:
        """Deletes a run document by its ID."""
        result = await self.runs_collection.delete_one({{"run_id": run_id}})
        return result.deleted_count > 0

    async def save_arena_state(self, run_id: str, state: ArenaState):
        """Saves or updates the ArenaState for a given run_id."""
        # We can use update_one with upsert=True to either insert a new state or update an existing one
        await self.runs_collection.update_one(
            {{"run_id": run_id}},
            {{"\$set": state.dict()}},
            upsert=True
        )

    async def get_arena_state(self, run_id: str) -> Optional[ArenaState]:
        """Retrieves the ArenaState for a given run_id."""
        run_data = await self.runs_collection.find_one({{"run_id": run_id}})
        if run_data:
            return ArenaState(**run_data)
        return None

    async def create_attack_prompt(self, prompt_data: Dict[str, Any]) -> str:
        """Creates a new attack prompt document in the database."""
        result = await self.attack_prompts_collection.insert_one(prompt_data)
        return str(result.inserted_id)

    async def get_attack_prompt(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single attack prompt by its ID."""
        prompt_data = await self.attack_prompts_collection.find_one({{"_id": ObjectId(prompt_id)}})
        return prompt_data

    async def update_attack_prompt(self, prompt_id: str, update_data: Dict[str, Any]) -> bool:
        """Updates an existing attack prompt document."""
        result = await self.attack_prompts_collection.update_one({{"_id": ObjectId(prompt_id)}}, {{"\$set": update_data}})
        return result.modified_count > 0

    async def delete_attack_prompt(self, prompt_id: str) -> bool:
        """Deletes an attack prompt document by its ID."""
        result = await self.attack_prompts_collection.delete_one({{"_id": ObjectId(prompt_id)}})
        return result.deleted_count > 0

    async def create_defense_response(self, response_data: Dict[str, Any]) -> str:
        """Creates a new defense response document in the database."""
        result = await self.defense_responses_collection.insert_one(response_data)
        return str(result.inserted_id)

    async def get_defense_response(self, response_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single defense response by its ID."""
        response_data = await self.defense_responses_collection.find_one({{"_id": ObjectId(response_id)}})
        return response_data

    async def update_defense_response(self, response_id: str, update_data: Dict[str, Any]) -> bool:
        """Updates an existing defense response document."""
        result = await self.defense_responses_collection.update_one({{"_id": ObjectId(response_id)}}, {{"\$set": update_data}})
        return result.modified_count > 0

    async def delete_defense_response(self, response_id: str) -> bool:
        """Deletes a defense response document by its ID."""
        result = await self.defense_responses_collection.delete_one({{"_id": ObjectId(response_id)}})
        return result.deleted_count > 0

    async def create_evaluation_result(self, result_data: Dict[str, Any]) -> str:
        """Creates a new evaluation result document in the database."""
        result = await self.evaluation_results_collection.insert_one(result_data)
        return str(result.inserted_id)

    async def get_evaluation_result(self, result_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a single evaluation result by its ID."""
        result_data = await self.evaluation_results_collection.find_one({{"_id": ObjectId(result_id)}})
        return result_data

    async def update_evaluation_result(self, result_id: str, update_data: Dict[str, Any]) -> bool:
        """Updates an existing evaluation result document."""
        result = await self.evaluation_results_collection.update_one({{"_id": ObjectId(result_id)}}, {{"\$set": update_data}})
        return result.modified_count > 0

    async def delete_evaluation_result(self, result_id: str) -> bool:
        """Deletes an evaluation result document by its ID."""
        result = await self.evaluation_results_collection.delete_one({{"_id": ObjectId(result_id)}})
        return result.deleted_count > 0

    def save_prompt(self, run_id: str, prompt: str, metadata: dict):
        """Saves a prompt for a run to the database."""
        # Implement the database save logic here
        print(f"Saving prompt for run {run_id} to the database")
        # Example:  self.runs_collection.insert_one({"run_id": run_id, "prompt": prompt, **metadata})


