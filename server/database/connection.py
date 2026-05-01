"""
Database Connection Module

Manages MongoDB connection for the adversarial testing engine.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
import os


class DatabaseConnection:
    """
    Singleton database connection manager.
    
    Uses Motor for async MongoDB operations.
    """
    
    _client: Optional[AsyncIOMotorClient] = None
    _db: Optional[AsyncIOMotorDatabase] = None
    
    @classmethod
    async def connect(cls, mongo_url: str = None, database_name: str = None):
        """
        Initialize database connection.
        
        Args:
            mongo_url: MongoDB connection string (defaults to env var)
            database_name: Database name (defaults to env var)
        """
        if cls._client is not None:
            return cls._db
        
        # Get connection details from env if not provided
        mongo_url = mongo_url or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        database_name = database_name or os.getenv("MONGO_DB_NAME", "adversarial_testing")
        
        # Create client
        cls._client = AsyncIOMotorClient(mongo_url)
        cls._db = cls._client[database_name]
        
        # Test connection
        await cls._client.admin.command('ping')
        
        print(f"Connected to MongoDB: {database_name}")
        
        # Create indexes
        await cls._create_indexes()
        
        return cls._db
    
    @classmethod
    async def _create_indexes(cls):
        """Create database indexes for performance"""
        if cls._db is None:
            return
        
        # Runs collection indexes
        await cls._db.runs.create_index("run_id", unique=True)
        await cls._db.runs.create_index("status")
        await cls._db.runs.create_index("started_at")
        await cls._db.runs.create_index([("user_id", 1), ("started_at", -1)])
        
        # Steps collection indexes
        await cls._db.steps.create_index([("run_id", 1), ("turn_id", 1)])
        await cls._db.steps.create_index("run_id")
        await cls._db.steps.create_index("timestamp")
        
        # Evaluations collection indexes
        await cls._db.evaluations.create_index("run_id")
        await cls._db.evaluations.create_index([("run_id", 1), ("score", -1)])
        await cls._db.evaluations.create_index("category")
        
        print("Database indexes created")
    
    @classmethod
    def get_database(cls) -> Optional[AsyncIOMotorDatabase]:
        """
        Get the database instance.
        
        Returns:
            Database instance or None if not connected
        """
        return cls._db
    
    @classmethod
    async def disconnect(cls):
        """Close database connection"""
        if cls._client:
            cls._client.close()
            cls._client = None
            cls._db = None
            print("Disconnected from MongoDB")


# Convenience function for getting database
async def init_db(mongo_uri: str = None, database_name: str = None) -> AsyncIOMotorDatabase:
    """
    Initialize and return database connection.
    
    Args:
        mongo_url: MongoDB connection string
        database_name: Database name
    
    Returns:
        Database instance
    """
    return await DatabaseConnection.connect(mongo_uri, database_name)


def get_db() -> Optional[AsyncIOMotorDatabase]:
    """
    Get current database instance.
    
    Returns:
        Database instance or None
    """
    return DatabaseConnection.get_database()


async def close_db():
    """Close database connection"""
    await DatabaseConnection.disconnect()
