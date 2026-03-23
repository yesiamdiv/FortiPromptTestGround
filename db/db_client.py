from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from urllib.parse import quote_plus

class DatabaseClient:
    def __init__(self, config):
        self.config = config
        self.client = None
        self.db = None

    async def connect(self):
        try:
            mongo_uri = self.config.get('MONGO_URI')
            if not mongo_uri:
                raise ValueError("MONGO_URI not found in configuration.")

            # Ensure username and password are URL-encoded
            username = quote_plus(self.config.get('MONGO_USERNAME', ''))
            password = quote_plus(self.config.get('MONGO_PASSWORD', ''))
            host = self.config.get('MONGO_HOST', 'localhost')
            port = self.config.get('MONGO_PORT', '27017')
            db_name = self.config.get('MONGO_DB_NAME', 'agentic_testing_ground')

            # Construct the MongoDB URI with proper encoding
            if username and password:
                mongo_uri = f"mongodb://{username}:{password}@{host}:{port}/?retryWrites=true&w=majority"
            else:
                mongo_uri = f"mongodb://{host}:{port}/?retryWrites=true&w=majority"

            self.client = AsyncIOMotorClient(mongo_uri)
            # The ismaster command is cheap and does not require auth.
            await self.client.admin.command('ismaster')
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
        if not self.db:
            raise ConnectionError("Database not connected. Call connect() first.")
        return self.db

    async def close(self):
        if self.client:
            self.client.close()
            print("MongoDB connection closed.")

# Example of how to use this client (assuming config is loaded elsewhere):
# async def main():
#     # Load config from a file or environment variables
#     config = {
#         'MONGO_USERNAME': 'user', 
#         'MONGO_PASSWORD': 'password', 
#         'MONGO_HOST': 'localhost', 
#         'MONGO_PORT': '27017', 
#         'MONGO_DB_NAME': 'testdb'
#     }
#     db_client = DatabaseClient(config)
#     await db_client.connect()
#     db = db_client.get_db()
#     # Perform database operations here
#     await db_client.close()

# if __name__ == "__main__":
#     import asyncio
#     asyncio.run(main())
