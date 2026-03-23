from pydantic import BaseModel, Field
from typing import Optional, List

class RunState(BaseModel):
    run_id: str
    goal: str
    strategy: str
    max_turns: int
    turn_count: int
    chat_history: List[dict]
    current_prompt: str
    current_response: str
    evaluation_result: str
    evaluation_reasoning: str
    strategy_metadata: dict
    final_outcome: str

class ArenaState(BaseModel):
    run_id: str
    goal: str
    strategy: str
    max_turns: int
    turn_count: int
    chat_history: List[dict]
    current_prompt: str
    current_response: str
    evaluation_result: str
    evaluation_reasoning: str
    strategy_metadata: dict
    final_outcome: str

# Note: These Pydantic models can be used to validate data before inserting into MongoDB.
# For MongoDB schema definition with Mongoose, you would typically define Mongoose schemas separately.
# Example using Mongoose (requires mongoose to be installed and imported):
#
# from pymongo import MongoClient
# from motor.motor_asyncio import AsyncIOMotorClient
# import mongoose
#
# async def get_mongoose_db():
#     # Ensure you have loaded your config and have MONGO_URI
#     # For example:
#     # config = {...}
#     # mongo_uri = config.get('MONGO_URI')
#     mongo_uri = "mongodb://localhost:27017/"
#     await mongoose.connect(mongo_uri)
#     return mongoose.connection
#
# async def define_schemas():
#     db = await get_mongoose_db()
#     run_schema = {
#         "run_id": str,
#         "goal": str,
#         "strategy": str,
#         "max_turns": int,
#         "turn_count": int,
#         "chat_history": list,
#         "current_prompt": str,
#         "current_response": str,
#         "evaluation_result": str,
#         "evaluation_reasoning": str,
#         "strategy_metadata": dict,
#         "final_outcome": str
#     }
#     # Define Mongoose models here
#     # Example:
#     # RunModel = db.model('Run', run_schema)
#     # return RunModel
