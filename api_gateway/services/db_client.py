# db_client.py

from motor.motor_asyncio import AsyncIOMotorClient
from typing import List, Dict, Any, Optional

from config import MONGO_URI, MONGO_DB_NAME
from db.models import Run, ArenaState

class DBClient:
    def __init__(self):
        self.client = AsyncIOMotorClient(MONGO_URI)
        self.db = self.client[MONGO_DB_NAME]
        self.runs_collection = self.db.runs

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
        result = await self.runs_collection.update_one({{"run_id": run_id}}, {{"$set": update_data}})
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
            {{"$set": state.dict()}},
            upsert=True
        )

    async def get_arena_state(self, run_id: str) -> Optional[ArenaState]:
        """Retrieves the ArenaState for a given run_id."""
        run_data = await self.runs_collection.find_one({{"run_id": run_id}})
        if run_data:
            return ArenaState(**run_data)
        return None

    async def close(self):
        """Closes the database connection."""
        self.client.close()
