import config
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import ConnectionFailure
from urllib.parse import quote_plus
from pydantic import ValidationError
from datetime import datetime
from typing import Dict, Any, List, Optional
from bson import ObjectId

# Import Pydantic models from schemas.py
from .models import Run, RunInDB, AttackData, DefenseData, EvaluationData, RunConfig

class DatabaseClient:
    def __init__(self,config):
        self.config = config
        self.client = None
        self.db = None
        self.runs_collection = None
        print("Initializing DatabaseClient...")

    async def connect(self):
        print("Inside connect method...")
        try:
            mongo_uri = self.config.get('MONGO_URI')
            if not mongo_uri:
                # Fallback to constructing URI from components if MONGO_URI is not directly provided
                username = self.config.get('MONGO_USERNAME')
                password = self.config.get('MONGO_PASSWORD')
                host = self.config.get('MONGO_HOST')
                port = self.config.get('MONGO_PORT')
                db_name = self.config.get('MONGO_DB_NAME')

                if username and password:
                    mongo_uri = f"mongodb://{username}:{password}@{host}:{port}/?retryWrites=true&w=majority"
                else:
                    mongo_uri = f"mongodb://{host}:{port}/?retryWrites=true&w=majority"
            else:
                # If MONGO_URI is provided, use it directly
                db_name = self.config.get('MONGO_DB_NAME')

            print(f"MongoDB URI: {mongo_uri}")
            print(f"Database Name: {db_name}")
            self.client = AsyncIOMotorClient(mongo_uri)
            await self.client.admin.command('ismaster') # Check connection
            self.db = self.client[db_name]

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
        if self.db == None:
            raise ConnectionError("Database not connected. Call connect() first.")
        return self.db

    async def create_attack_data(self, run_id: str, attack_data: AttackData) -> str:
        """Creates a new attack data record and returns its ID."""
        # We need to store the attack data itself, and then link it via run_id.
        # For simplicity, let's assume we store attack data in a 'prompts' collection.
        # In a more complex system, you might have a dedicated 'attack_data' collection.
        
        # Add run_id to the data to be stored
        attack_data_dict = attack_data.dict()
        attack_data_dict['run_id'] = run_id
        
        print(f"Attempting to create attack data for run {run_id} with data: {attack_data_dict}")
        result = await self.db.get_collection('attack_prompts').insert_one(attack_data_dict)
        print(f"Attack data inserted with ID: {result.inserted_id}")
        return str(result.inserted_id)

    async def get_attack_data(self, attack_id: str) -> Optional[AttackData]:
        """Retrieves a single attack data record by its ID."""
        print(f"Attempting to get attack data with attack_id: {attack_id}")
        attack_data = await self.db.get_collection('attack_prompts').find_one({{"_id": ObjectId(attack_id)}})
        if attack_data:
            print(f"Found attack data: {attack_data.get('_id')}")
            return AttackData(**attack_data)
        print(f"Attack data with id: {attack_id} not found.")
        return None

    async def get_attack_data_for_run(self, run_id: str) -> List[AttackData]:
        """Retrieves all attack data records for a given run_id."""
        attack_data_list = await self.db.get_collection('attack_prompts').find({{"run_id": run_id}}).to_list(length=None)
        return [AttackData(**data) for data in attack_data_list]

    async def update_attack_data(self, attack_id: str, update_data: Dict[str, Any]) -> bool:
        """Updates an existing attack data record."""
        print(f"Attempting to update attack data {attack_id} with data: {update_data}")
        result = await self.db.get_collection('attack_prompts').update_one({{"_id": ObjectId(attack_id)}}, {{"$set": update_data}})
        if result.modified_count > 0:
            print(f"Attack data {attack_id} updated successfully.")
        else:
            print(f"Attack data {attack_id} not found or no changes made.")
        return result.modified_count > 0

    async def create_defense_data(self, run_id: str, defense_data: DefenseData) -> str:
        """Creates a new defense data record and returns its ID."""
        # Similar to attack data, store in a dedicated collection, e.g., 'responses'
        defense_data_dict = defense_data.dict()
        defense_data_dict['run_id'] = run_id
        print(f"Attempting to create defense data for run {run_id} with data: {defense_data_dict}")
        result = await self.db.get_collection('defense_responses').insert_one(defense_data_dict)
        print(f"Defense data inserted with ID: {result.inserted_id}")
        return str(result.inserted_id)

    async def get_defense_data(self, defense_id: str) -> Optional[DefenseData]:
        """Retrieves a single defense data record by its ID."""
        print(f"Attempting to get defense data with defense_id: {defense_id}")
        defense_data = await self.db.get_collection('defense_responses').find_one({{"_id": ObjectId(defense_id)}})
        if defense_data:
            print(f"Found defense data: {defense_data.get('_id')}")
            return DefenseData(**defense_data)
        print(f"Defense data with id: {defense_id} not found.")
        return None

    async def get_defense_data_for_run(self, run_id: str) -> List[DefenseData]:
        """Retrieves all defense data records for a given run_id."""
        defense_data_list = await self.db.get_collection('defense_responses').find({{"run_id": run_id}}).to_list(length=None)
        return [DefenseData(**data) for data in defense_data_list]

    async def update_defense_data(self, defense_id: str, update_data: Dict[str, Any]) -> bool:
        """Updates an existing defense data record."""
        print(f"Attempting to update defense data {defense_id} with data: {update_data}")
        result = await self.db.get_collection('defense_responses').update_one({{"_id": ObjectId(defense_id)}}, {{"$set": update_data}})
        if result.modified_count > 0:
            print(f"Defense data {defense_id} updated successfully.")
        else:
            print(f"Defense data {defense_id} not found or no changes made.")
        return result.modified_count > 0

    async def create_evaluation_data(self, run_id: str, evaluation_data: EvaluationData) -> str:
        """Creates a new evaluation data record and returns its ID."""
        # Store in an 'evaluations' collection
        evaluation_data_dict = evaluation_data.dict()
        evaluation_data_dict['run_id'] = run_id
        print(f"Attempting to create evaluation data for run {run_id} with data: {evaluation_data_dict}")
        result = await self.db.get_collection('evaluation_results').insert_one(evaluation_data_dict)
        print(f"Evaluation data inserted with ID: {result.inserted_id}")
        return str(result.inserted_id)

    async def get_evaluation_data(self, evaluation_id: str) -> Optional[EvaluationData]:
        """Retrieves a single evaluation data record by its ID."""
        print(f"Attempting to get evaluation data with evaluation_id: {evaluation_id}")
        evaluation_data = await self.db.get_collection('evaluation_results').find_one({{"_id": ObjectId(evaluation_id)}})
        if evaluation_data:
            print(f"Found evaluation data: {evaluation_data.get('_id')}")
            return EvaluationData(**evaluation_data)
        print(f"Evaluation data with id: {evaluation_id} not found.")
        return None

    async def get_evaluation_data_for_run(self, run_id: str) -> List[EvaluationData]:
        """Retrieves all evaluation data records for a given run_id."""
        evaluation_data_list = await self.db.get_collection('evaluation_results').find({{"run_id": run_id}}).to_list(length=None)
        return [EvaluationData(**data) for data in evaluation_data_list]

    async def update_evaluation_data(self, evaluation_id: str, update_data: Dict[str, Any]) -> bool:
        """Updates an existing evaluation data record."""
        print(f"Attempting to update evaluation data {evaluation_id} with data: {update_data}")
        result = await self.db.get_collection('evaluation_results').update_one({{"_id": ObjectId(evaluation_id)}}, {{"$set": update_data}})
        if result.modified_count > 0:
            print(f"Evaluation data {evaluation_id} updated successfully.")
        else:
            print(f"Evaluation data {evaluation_id} not found or no changes made.")
        return result.modified_count > 0

    async def save_run_references(self, run_id: str, attack_ids: List[str], defense_ids: List[str], evaluation_ids: List[str]):
        """Updates the RunInDB document with references to the stored data."""
        print(f"Attempting to save references for run {run_id}: attack_ids={attack_ids}, defense_ids={defense_ids}, evaluation_ids={evaluation_ids}")
        update_data = {
            "attack_store_ref": attack_ids, # Assuming these are IDs, adjust if they are collection names or other refs
            "defense_store_ref": defense_ids,
            "evaluation_store_ref": evaluation_ids,
            "updated_at": datetime.utcnow()
        }
        result = await self.db.get_collection('runs').update_one({{"run_id": run_id}}, {{"$set": update_data}})
        if result.modified_count > 0:
            print(f"Run references for {run_id} updated successfully.")
        else:
            print(f"Run {run_id} not found for reference update or no changes made.")

    async def get_runs(self) -> List[Run]:
        """Retrieves all runs from the database."""
        runs_data = await self.db.get_collection('runs').find().to_list(length=None)
        return [RunInDB(**run) for run in runs_data]
    
    async def create_run(self, run_data: Dict[str, Any]) -> str:
        """Creates a new run document in the database."""
        run_id = run_data.get('run_id')
        if not run_id:
            raise ValueError("run_id is required")

        # Ensure the run_id is unique before inserting
        existing_run = await self.db.get_collection('runs').find_one({"run_id": run_id})
        if existing_run:
            raise ValueError(f"Run with id {run_id} already exists")

        # Convert run_data to RunInDB model and add timestamps
        if '_id' not in run_data:
            run_data['_id'] = None # Or handle this case as an error if _id is always expected
        run_in_db = RunInDB(
            **run_data,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        result = await self.db.get_collection('runs').insert_one(run_in_db.dict())
        return str(result.inserted_id)

    async def get_run(self, run_id: str) -> Optional[RunInDB]:
        """Retrieves a single run by its ID."""
        run_data = await self.db.get_collection('runs').find_one({"run_id": run_id})
        if run_data:
            return RunInDB(**run_data)
        return None

    async def update_run(self, run_id: str, update_data: Dict[str, Any]) -> bool:
        """Updates an existing run document."""
        # Add updated_at timestamp
        update_data['updated_at'] = datetime.utcnow()
        result = await self.db.get_collection('runs').update_one({'run_id': run_id}, {'$set': update_data})
        return result.modified_count > 0

    async def delete_run(self, run_id: str) -> bool:
        """Deletes a run document by its ID."""
        result = await self.db.get_collection('runs').delete_one({'run_id': run_id})
        return result.deleted_count > 0

    async def close(self):
        if self.client:
            self.client.close()
            print("MongoDB connection closed.")

 
    # async def create_run(self, run_data: Dict[str, Any]) -> str:
    #     """Creates a new run document in the database."""
    #     run_id = run_data.get('run_id')
    #     if not run_id:
    #         raise ValueError("run_id is required")

    #     # Ensure the run_id is unique before inserting
    #     existing_run = await self.runs_collection.find_one({{"run_id": run_id}})
    #     if existing_run:
    #         raise ValueError(f"Run with id {run_id} already exists")

    #     result = await self.runs_collection.insert_one(run_data)
    #     return str(result.inserted_id)

    # async def get_run(self, run_id: str) -> Optional[Run]:
    #     """Retrieves a single run by its ID."""
    #     run_data = await self.runs_collection.find_one({{"run_id": run_id}})
    #     if run_data:
    #         return Run(**run_data)
    #     return None

    # async def get_runs(self) -> List[Run]:
    #     """Retrieves all runs from the database."""
    #     runs_data = await self.runs_collection.find().to_list(length=None)
    #     return [Run(**run) for run in runs_data]

    # async def update_run(self, run_id: str, update_data: Dict[str, Any]) -> bool:
    #     """Updates an existing run document."""
    #     result = await self.runs_collection.update_one({{"run_id": run_id}}, {{"\$set": update_data}})
    #     return result.modified_count > 0

    # async def delete_run(self, run_id: str) -> bool:
    #     """Deletes a run document by its ID."""
    #     result = await self.runs_collection.delete_one({{"run_id": run_id}})
    #     return result.deleted_count > 0

    # async def save_arena_state(self, run_id: str, state: ArenaState):
    #     """Saves or updates the ArenaState for a given run_id."""
    #     # We can use update_one with upsert=True to either insert a new state or update an existing one
    #     await self.runs_collection.update_one(
    #         {{"run_id": run_id}},
    #         {{"\$set": state.dict()}},
    #         upsert=True
    #     )

    # async def get_arena_state(self, run_id: str) -> Optional[ArenaState]:
    #     """Retrieves the ArenaState for a given run_id."""
    #     run_data = await self.runs_collection.find_one({{"run_id": run_id}})
    #     if run_data:
    #         return ArenaState(**run_data)
    #     return None

    # async def create_attack_prompt(self, prompt_data: Dict[str, Any]) -> str:
    #     """Creates a new attack prompt document in the database."""
    #     result = await self.attack_prompts_collection.insert_one(prompt_data)
    #     return str(result.inserted_id)

    # async def get_attack_prompt(self, prompt_id: str) -> Optional[Dict[str, Any]]:
    #     """Retrieves a single attack prompt by its ID."""
    #     prompt_data = await self.attack_prompts_collection.find_one({{"_id": ObjectId(prompt_id)}})
    #     return prompt_data

    # async def update_attack_prompt(self, prompt_id: str, update_data: Dict[str, Any]) -> bool:
    #     """Updates an existing attack prompt document."""
    #     result = await self.attack_prompts_collection.update_one({{"_id": ObjectId(prompt_id)}}, {{"\$set": update_data}})
    #     return result.modified_count > 0

    # async def delete_attack_prompt(self, prompt_id: str) -> bool:
    #     """Deletes an attack prompt document by its ID."""
    #     result = await self.attack_prompts_collection.delete_one({{"_id": ObjectId(prompt_id)}})
    #     return result.deleted_count > 0

    # async def create_defense_response(self, response_data: Dict[str, Any]) -> str:
    #     """Creates a new defense response document in the database."""
    #     result = await self.defense_responses_collection.insert_one(response_data)
    #     return str(result.inserted_id)

    # async def get_defense_response(self, response_id: str) -> Optional[Dict[str, Any]]:
    #     """Retrieves a single defense response by its ID."""
    #     response_data = await self.defense_responses_collection.find_one({{"_id": ObjectId(response_id)}})
    #     return response_data

    # async def update_defense_response(self, response_id: str, update_data: Dict[str, Any]) -> bool:
    #     """Updates an existing defense response document."""
    #     result = await self.defense_responses_collection.update_one({{"_id": ObjectId(response_id)}}, {{"\$set": update_data}})
    #     return result.modified_count > 0

    # async def delete_defense_response(self, response_id: str) -> bool:
    #     """Deletes a defense response document by its ID."""
    #     result = await self.defense_responses_collection.delete_one({{"_id": ObjectId(response_id)}})
    #     return result.deleted_count > 0

    # async def create_evaluation_result(self, result_data: Dict[str, Any]) -> str:
    #     """Creates a new evaluation result document in the database."""
    #     result = await self.evaluation_results_collection.insert_one(result_data)
    #     return str(result.inserted_id)

    # async def get_evaluation_result(self, result_id: str) -> Optional[Dict[str, Any]]:
    #     """Retrieves a single evaluation result by its ID."""
    #     result_data = await self.evaluation_results_collection.find_one({{"_id": ObjectId(result_id)}})
    #     return result_data

    # async def update_evaluation_result(self, result_id: str, update_data: Dict[str, Any]) -> bool:
    #     """Updates an existing evaluation result document."""
    #     result = await self.evaluation_results_collection.update_one({{"_id": ObjectId(result_id)}}, {{"\$set": update_data}})
    #     return result.modified_count > 0

    # async def delete_evaluation_result(self, result_id: str) -> bool:
    #     """Deletes an evaluation result document by its ID."""
    #     result = await self.evaluation_results_collection.delete_one({{"_id": ObjectId(result_id)}})
    #     return result.deleted_count > 0

    # async def save_prompt(self, run_id: str, prompt: str, metadata: dict):
    #     """Saves a prompt for a run to the database."""
    #     prompt_data = {
    #         "run_id": run_id,
    #         "prompt": prompt,
    #         "metadata": metadata,
    #         "timestamp": datetime.utcnow()
    #     }
    #     try:
    #         # Use insert_one to save the prompt data
    #         # Note: This is a synchronous call. For async operations, use await self.prompts_collection.insert_one(prompt_data)
    #         # However, since this method is not async, we'll use the synchronous API.
    #         # If the orchestrator is running async, this might need adjustment.
    #         await self.prompts_collection.insert_one(prompt_data)
    #         print(f"Prompt saved successfully for run {run_id}.")
    #     except Exception as e:
    #         print(f"Error saving prompt for run {run_id}: {e}")

