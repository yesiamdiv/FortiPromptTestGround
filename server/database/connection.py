"""
Database Connection Module

Manages MongoDB connection for the adversarial testing engine.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from typing import Optional
from core.logging import checkpoint, debug, tracer, step
from core.env import get_settings


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
            debug("Database already connected")
            return cls._db
        
        settings = get_settings()
        mongo_url = mongo_url or settings.mongodb_uri
        database_name = database_name or settings.mongodb_db_name
        
        tracer("Connecting to MongoDB", mongo_url=mongo_url, database_name=database_name)
        
        # Create client
        cls._client = AsyncIOMotorClient(mongo_url)
        cls._db = cls._client[database_name]
        
        # Test connection
        await cls._client.admin.command('ping')
        
        step("Connected to MongoDB", database_name=database_name)
        
        # Create indexes
        await cls._create_indexes()
        
        return cls._db
    
    @classmethod
    async def _create_indexes(cls):
        """Create database indexes for performance"""
        tracer("Creating database indexes")
        
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
        
        checkpoint("Database indexes created")
    
    @classmethod
    def get_database(cls) -> Optional[AsyncIOMotorDatabase]:
        """
        Get the database instance.
        
        Returns:
            Database instance or None if not connected
        """
        debug("Getting database instance")
        return cls._db
    
    @classmethod
    async def disconnect(cls):
        """Close database connection"""
        tracer("Disconnecting from MongoDB")
        if cls._client:
            cls._client.close()
            cls._client = None
            cls._db = None
            debug("Disconnected from MongoDB")


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
    tracer("Initializing database")
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
    tracer("Closing database connection")
    await DatabaseConnection.disconnect()
