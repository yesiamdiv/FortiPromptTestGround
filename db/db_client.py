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
from .manual_models import ManualRunInDB, ChatSession, ChatTurn

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
        attack_data = await self.db.get_collection('attack_prompts').find_one({"_id": ObjectId(attack_id)})
        if attack_data:
            print(f"Found attack data: {attack_data.get('_id')}")
            return AttackData(**attack_data)
        print(f"Attack data with id: {attack_id} not found.")
        return None

    async def get_attack_data_for_run(self, run_id: str) -> List[AttackData]:
        """Retrieves all attack data records for a given run_id."""
        attack_data_list = await self.db.get_collection('attack_prompts').find({"run_id": run_id}).to_list(length=None)
        return [AttackData(**data, id=str(data.pop('_id'))) for data in attack_data_list]

    async def update_attack_data(self, attack_id: str, update_data: Dict[str, Any]) -> bool:
        """Updates an existing attack data record."""
        print(f"Attempting to update attack data {attack_id} with data: {update_data}")
        result = await self.db.get_collection('attack_prompts').update_one({"_id": ObjectId(attack_id)}, {"$set": update_data})
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
        defense_data = await self.db.get_collection('defense_responses').find_one({"_id": ObjectId(defense_id)})
        if defense_data:
            print(f"Found defense data: {defense_data.get('_id')}")
            return DefenseData(**defense_data)
        print(f"Defense data with id: {defense_id} not found.")
        return None

    async def get_defense_data_for_run(self, run_id: str) -> List[DefenseData]:
        """Retrieves all defense data records for a given run_id."""
        defense_data_list = await self.db.get_collection('defense_responses').find({"run_id": run_id}).to_list(length=None)
        return [
            DefenseData(**{**data, "_id": str(data["_id"])})
            for data in defense_data_list
        ]

    async def update_defense_data(self, defense_id: str, update_data: Dict[str, Any]) -> bool:
        """Updates an existing defense data record."""
        result = await self.db.get_collection('defense_responses').update_one(
            {"_id": ObjectId(defense_id)},
            {"$set": update_data}
        )
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
        evaluation_data = await self.db.get_collection('evaluation_results').find_one({"_id": ObjectId(evaluation_id)})
        if evaluation_data:
            print(f"Found evaluation data: {evaluation_data.get('_id')}")
            return EvaluationData(**evaluation_data)
        print(f"Evaluation data with id: {evaluation_id} not found.")
        return None

    async def get_evaluation_data_for_run(self, run_id: str) -> List[EvaluationData]:
        """Retrieves all evaluation data records for a given run_id."""
        evaluation_data_list = await self.db.get_collection('evaluation_results').find({"run_id": run_id}).to_list(length=None)
        return [
            EvaluationData(**{**data, "_id": str(data["_id"])})
            for data in evaluation_data_list
        ]

    async def update_evaluation_data(self, evaluation_id: str, update_data: Dict[str, Any]) -> bool:
        """Updates an existing evaluation data record."""
        result = await self.db.get_collection('evaluation_results').update_one(
            {"_id": ObjectId(evaluation_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0

    # --- Run CRUD Operations ---

    async def create_run(self, run: RunInDB) -> str:
        """Creates a new run document in the database."""
        run_dict = run.dict(by_alias=True)
        
        # Ensure timestamps are set
        if 'created_at' not in run_dict or run_dict['created_at'] is None:
            run_dict['created_at'] = datetime.utcnow()
        if 'updated_at' not in run_dict or run_dict['updated_at'] is None:
            run_dict['updated_at'] = datetime.utcnow()
        
        print(f"Attempting to create run with data: {run_dict}")
        result = await self.db.get_collection('runs').insert_one(run_dict)
        print(f"Run inserted with ID: {result.inserted_id}")
        return str(result.inserted_id)

    async def get_runs(self) -> List[RunInDB]:
        """Retrieves all runs from the database."""
        runs_data = await self.db.get_collection('runs').find().to_list(length=None)
        return [RunInDB(**run) for run in runs_data]

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

 
    # ── Collection helpers ────────────────────────────────────────────────────

    def _manual_runs_col(self):
        return self.db.get_collection("manual_runs")

    def _manual_sessions_col(self):
        return self.db.get_collection("manual_sessions")

    # ── Manual Run CRUD ───────────────────────────────────────────────────────

    async def create_manual_run(self, manual_run: ManualRunInDB) -> str:
        """Insert a new ManualRunInDB document. Returns run_id."""
        doc = manual_run.dict()
        await self._manual_runs_col().insert_one(doc)
        print(f"[DB] Created manual run: {manual_run.run_id}")
        return manual_run.run_id

    async def get_manual_run(self, run_id: str) -> Optional[ManualRunInDB]:
        """Fetch manual run by run_id."""
        doc = await self._manual_runs_col().find_one({"run_id": run_id})
        if doc:
            doc.pop("_id", None)
            return ManualRunInDB(**doc)
        return None

    async def update_manual_run(self, run_id: str, update: Dict[str, Any]) -> bool:
        """Partial update on a manual run document."""
        update["updated_at"] = datetime.utcnow()
        result = await self._manual_runs_col().update_one(
            {"run_id": run_id}, {"$set": update}
        )
        return result.modified_count > 0

    # ── Chat Session CRUD ─────────────────────────────────────────────────────

    async def create_chat_session(self, session: ChatSession) -> str:
        """Insert a new ChatSession document. Returns session_id."""
        doc = session.dict()
        await self._manual_sessions_col().insert_one(doc)
        # Also push session_id into the manual_run's sessions list
        await self._manual_runs_col().update_one(
            {"run_id": session.run_id},
            {"$addToSet": {"sessions": session.session_id},
             "$set": {"updated_at": datetime.utcnow()}}
        )
        print(f"[DB] Created chat session: {session.session_id} for run: {session.run_id}")
        return session.session_id

    async def get_chat_session(self, session_id: str) -> Optional[ChatSession]:
        """Fetch a single ChatSession by session_id."""
        doc = await self._manual_sessions_col().find_one({"session_id": session_id})
        if doc:
            doc.pop("_id", None)
            return ChatSession(**doc)
        return None

    async def get_sessions_for_run(self, run_id: str) -> List[ChatSession]:
        """Fetch all ChatSession documents for a run, newest first."""
        cursor = self._manual_sessions_col().find(
            {"run_id": run_id}
        ).sort("created_at", -1)
        docs = await cursor.to_list(length=None)
        sessions = []
        for doc in docs:
            doc.pop("_id", None)
            sessions.append(ChatSession(**doc))
        return sessions

    async def append_turn_to_session(self, session_id: str, turn: ChatTurn) -> bool:
        """Push a single ChatTurn into the session's turns array."""
        result = await self._manual_sessions_col().update_one(
            {"session_id": session_id},
            {"$push": {"turns": turn.dict()}}
        )
        return result.modified_count > 0

    async def update_chat_session(self, session_id: str, update: Dict[str, Any]) -> bool:
        """Partial update on a chat session document."""
        result = await self._manual_sessions_col().update_one(
            {"session_id": session_id}, {"$set": update}
        )
        return result.modified_count > 0

    async def save_and_evaluate_session(
        self,
        session_id: str,
        evaluation_score: float,
        evaluation_label: str,
        evaluation_reasoning: str,
        label: Optional[str] = None,
    ) -> bool:
        """
        Marks a session as saved + evaluated in a single atomic update.
        Called after the user clicks 'Save Session'.
        """
        now = datetime.utcnow()
        update: Dict[str, Any] = {
            "status": "evaluated",
            "saved_at": now,
            "evaluated_at": now,
            "evaluation_score": evaluation_score,
            "evaluation_label": evaluation_label,
            "evaluation_reasoning": evaluation_reasoning,
        }
        if label is not None:
            update["label"] = label
        result = await self._manual_sessions_col().update_one(
            {"session_id": session_id}, {"$set": update}
        )
        return result.modified_count > 0