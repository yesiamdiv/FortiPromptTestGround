import asyncio

import uvicorn

from api_gateway import APIGateway  # Import APIGateway
from db.db_client import DatabaseClient
from db import initialize_database
from limited_engine.orchestrator import LimitedOrchestrator

async def main():
    # Initialize database client
    db_client = await initialize_database()

    api_gateway = APIGateway(db_client=db_client )
    # You can add other initializations here if needed, for example:
    orchestrator = LimitedOrchestrator(db_client=db_client, api_gateway=api_gateway)
    
    # Instantiate APIGateway with the database client
    app = api_gateway.get_app() # Get the ASGI app from APIGateway

    # Run the ASGI application
    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())