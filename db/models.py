# models.py

from pymongo import MongoClient
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from typing import Optional, List

# Configuration
from config import MONGO_URI, MONGO_DB_NAME

# Async client for asynchronous operations
async_client = AsyncIOMotorClient(MONGO_URI)
async_db = async_client[MONGO_DB_NAME]

# Synchronous client for synchronous operations (if needed)
sync_client = MongoClient(MONGO_URI)
sync_db = sync_client[MONGO_DB_NAME]

# --- Pydantic Models (for data validation and structure) ---

class ArenaState(BaseModel):
    run_id: str
    goal: str
    strategy: str
    max_turns: int
    turn_count: int
    chat_history: list[dict] = Field(default_factory=list)
    current_prompt: Optional[str] = None
    current_response: Optional[str] = None
    evaluation_result: Optional[str] = None
    evaluation_reasoning: Optional[str] = None
    strategy_metadata: dict = Field(default_factory=dict)
    final_outcome: Optional[str] = None

class Run(BaseModel):
    run_id: str
    goal: str
    strategy: str
    max_turns: int
    turn_count: int
    chat_history: list[dict] = Field(default_factory=list)
    current_prompt: Optional[str] = None
    current_response: Optional[str] = None
    evaluation_result: Optional[str] = None
    evaluation_reasoning: Optional[str] = None
    strategy_metadata: dict = Field(default_factory=dict)
    final_outcome: Optional[str] = None
    timestamp: float = Field(default=0.0)

# --- MongoDB Collection Definitions (using Pydantic models for structure) ---

# Example: Runs collection
# You would typically interact with these collections via the async_db or sync_db objects
# For example: async_db.runs.insert_one(run_data)

# Define a function to get the runs collection
def get_runs_collection():
    return async_db.runs

# Define a function to get the sessions collection (if needed)
def get_sessions_collection():
    return async_db.sessions

# Add more collection functions as needed for other data entities
