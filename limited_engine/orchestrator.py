# Limited Engine Orchestrator

import asyncio
from typing import Dict, Any, List
from bson import ObjectId
from fastapi import APIRouter, HTTPException, status
from api_gateway import APIGateway
from db import DatabaseClient
# Import API schemas
from api_gateway.schemas import RunCreateRequest, RunResponse, AttackConfig, DefenseConfig 
# Import DB models
from db.models import Run as DBRun, RunInDB as DBRunInDB, AttackData, RunConfig # Import necessary schemas
from datetime import datetime
from db import initialize_database
from limited_engine.redgen.generator import TestCaseGenerator
import os
import datetime
from fastapi import HTTPException

# Assume ArenaState and other necessary components are defined elsewhere or will be mocked for this limited version.
# For now, we'll use simple dictionaries to represent state.

class LimitedOrchestrator:
    def __init__(self, db_client:DatabaseClient, api_gateway:APIGateway):
        self.db_client = db_client
        self.api_gateway = api_gateway
        self.runs: Dict[str, Dict[str, Any]] = {}
        self.run_counter = 0
        self.test_case_generator = TestCaseGenerator(
            n=10,  # Example: generate 10 prompts
            domain="cybersecurity", # Example domain
            paraphrase=True,
            engine="ollama", # or "groq"
            ollama_model="dolphin-mistral:7b-v2.6", # if using ollama
            output_dir="./limited_engine_prompts", # Directory to save prompts
            seed=self.run_counter, # Use run_counter for varied seeds
            api_gateway= self.api_gateway
        )
        self.register_routes()

    def register_routes(self):
        # Runs Routes
        @self.api_gateway.app.get("/api/runs", response_model=List[RunResponse]) # Changed to List[RunResponse]
        async def get_runs():
            runs = await self.db_client.get_runs()
            # Convert DBRunInDB objects to RunResponse schema
            return [RunResponse(
                run_id=run.run_id,
                name=run.name,
                status=run.status,
                config=run.config.dict(), # Convert RunConfig to dict
                created_at=run.created_at,
                updated_at=run.updated_at
            ) for run in runs]


        @self.api_gateway.app.post("/api/runs", status_code=status.HTTP_201_CREATED, response_model=RunResponse) # Changed to RunResponse
        async def create_run(run_data: RunCreateRequest): # Changed to RunCreateRequest
            self.run_counter += 1
            run_id = str(ObjectId()) # Generate a new ObjectId for run_id
            
            # Initialize run with default values, config will be updated later
            new_run = DBRunInDB(
                run_id=run_id,
                name=run_data.name,
                status="initialized", # Default status
                description=run_data.description,
                components=run_data.components,
                config={}, # Initialize config as empty dict
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            await self.db_client.create_run(new_run)
            
            # Store in memory for quick access (optional, depends on orchestrator's needs)
            self.runs[run_id] = new_run.dict(by_alias=True)
            
            # Return the created run response
            return RunResponse(
                run_id=new_run.run_id,
                name=new_run.name,
                status=new_run.status,
                config=new_run.config, # Return the empty config
                created_at=new_run.created_at,
                updated_at=new_run.updated_at
            )

        @self.api_gateway.app.patch("/api/runs/{runId}", response_model=RunResponse) # Changed to RunResponse
        async def update_run(runId: str, run_update: Dict[str, Any]):
            # Fetch the existing run from DB
            existing_run_db_data = await self.db_client.get_run(runId)
            if not existing_run_db_data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

            # Convert fetched data to DBRunInDB model for easier manipulation
            existing_run_db = existing_run_db_data # It's already a DBRunInDB object or similar structure


            # Update fields based on run_update
            for key, value in run_update.items():
                if hasattr(existing_run_db, key):
                    setattr(existing_run_db, key, value)
                # Handle nested config updates
                elif key.startswith("config."):
                    config_key = key.split(".")[1]
                    if hasattr(existing_run_db.config, config_key):
                        setattr(existing_run_db.config, config_key, value)
                    config_key = key.split(".")[1]
                    if hasattr(existing_run_db.config, config_key):
                        setattr(existing_run_db.config, config_key, value)
                    else:
                        # Ensure attack_config is a dict before trying to access keys
                        if config_key == 'attack_config' and not isinstance(value, dict):
                            existing_run_db.config.attack_config = {{}} # Initialize as empty dict if not a dict
                        elif config_key == 'defense_config' and not isinstance(value, dict):
                            existing_run_db.config.defense_config = {{}}
                        elif config_key == 'evaluation_config' and not isinstance(value, dict):
                            existing_run_db.config.evaluation_config = {{}}
                        elif config_key == 'global_config' and not isinstance(value, dict):
                            existing_run_db.config.global_config = {{}}
                        else:
                            existing_run_db.config.global_config[config_key] = value # Assuming updates go to global_config if not specific

            existing_run_db.updated_at = datetime.datetime.utcnow()

            # Update the run in the database
            updated = await self.db_client.update_run(runId, existing_run_db.dict(by_alias=True)) # Use by_alias=True for _id
            if not updated:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update run")

            # Fetch the updated run to return
            updated_run_in_db = await self.db_client.get_run(runId)
            if not updated_run_in_db:
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found after update")
            
            # Map DBRunInDB model to RunResponse for API response
            return RunResponse(
                run_id=updated_run_in_db.run_id,
                name=updated_run_in_db.name,
                status=updated_run_in_db.status,
                config=updated_run_in_db.config.dict(),
                created_at=updated_run_in_db.created_at,
                updated_at=updated_run_in_db.updated_at
            )

        @self.api_gateway.app.delete("/api/runs/{runId}", status_code=status.HTTP_204_NO_CONTENT) # Fixed path parameter
        async def delete_run(runId: str):
            deleted = await self.db_client.delete_run(runId)
            if not deleted:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

        # Attack Routes
        @self.api_gateway.app.get("/api/runs/{runId}/attack/config", response_model=AttackConfig)
        async def get_attack_config(runId: str):
            run_db_data = await self.db_client.get_run(runId)
            if not run_db_data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
            
            run_db = run_db_data # It's already a DBRunInDB object or similar structure
            if not run_db.config or not run_db.config.attack_config:
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attack config not found for this run")
            return AttackConfig(**run_db.config.attack_config)

        @self.api_gateway.app.put("/api/runs/{runId}/attack/config", response_model=AttackConfig)
        async def update_attack_config(runId: str, config: AttackConfig):
            # Fetch the existing run to update its config
            existing_run_db_data = await self.db_client.get_run(runId)
            if not existing_run_db_data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

            existing_run_db = existing_run_db_data # It's already a DBRunInDB object or similar structure
            
            # Ensure config and attack_config are dictionaries before updating
            if existing_run_db.config is None:
                existing_run_db.config = {}
            if 'attack_config' not in existing_run_db.config:
                existing_run_db.config['attack_config'] = {}

            # Update the attack_config within the run's config
            existing_run_db.config['attack_config'] = config.dict()
            existing_run_db.updated_at = datetime.datetime.utcnow()

            # Update the run in the database
            updated = await self.db_client.update_run(runId, existing_run_db.dict(by_alias=True))
            if not updated:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update run")

            # Update the generator's config if it's re-initialized or re-configured
            self.test_case_generator.n = config.iterations
            self.test_case_generator.domain = config.domain
            self.test_case_generator.engine = config.parameters.get("engine", "ollama")
            self.test_case_generator.ollama_model = config.model # Correctly setting the ollama_model from attack_config.model
            self.test_case_generator.seed = self.run_counter # Use run_counter for varied seeds

            return config

        @self.api_gateway.app.get("/api/runs/{runId}/attack/prompts", response_model=List[AttackData])
        async def get_attack_prompts(runId: str):
            run_db_data = await self.db_client.get_run(runId)
            if not run_db_data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
            
            # Fetch attack data using the run_id
            attack_data_list = await self.db_client.get_attack_data_for_run(runId)
            return attack_data_list

        @self.api_gateway.app.get("/api/runs/{runId}/attack/stats", response_model=Dict[str, Any])
        async def get_attack_stats(runId: str):
            run_db_data = await self.db_client.get_run(runId)
            if not run_db_data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
            
            # Get all attack data for the run to calculate stats
            attack_data_list = await self.db_client.get_attack_data_for_run(runId)
            total_prompts = len(attack_data_list)
            # Add more stats calculation as needed
            return {"totalPrompts": total_prompts}

        @self.api_gateway.app.post("/api/runs/{runId}/attack/start", response_model=Dict[str, str])
        async def start_attack_generation(runId: str, payload: Dict[str, bool]):
            run_db_data = await self.db_client.get_run(runId)
            if not run_db_data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

            run_db = run_db_data # It's already a DBRunInDB object or similar structure
            resume = payload.get("resumeFromLastSaved", False)
            
            # Update run status in DB
            run_db.status = "running"
            run_db.updated_at = datetime.datetime.utcnow()
            await self.db_client.update_run(runId, run_db.dict(by_alias=True))

            # Re-configure generator based on run config
            attack_config = AttackConfig(**run_db.config.attack_config)
            self.test_case_generator.n = attack_config.iterations
            self.test_case_generator.domain = attack_config.domain
            self.test_case_generator.engine = attack_config.parameters.get("engine", "ollama")
            self.test_case_generator.ollama_model = attack_config.model # Correctly setting the ollama_model from attack_config.model
            self.test_case_generator.seed = self.run_counter # Use run_counter for varied seeds
            self.test_case_generator.output_dir = f"./output/{runId}" # Set output directory per run
            self.test_case_generator.run_id = runId # Set the run_id

            # Start the generation process on a separate thread
            # This allows the API endpoint to return immediately
            generation_task = asyncio.create_task(
                self.run_generation_process(runId, run_db, attack_config, resume)
            )

            return {"message": "Attack generation started in background.", "status": "running"}

    async def run_generation_process(self, run_id: str, run_db: DBRunInDB, attack_config: AttackConfig, resume: bool): # Changed run_db type to DBRunInDB
        """Runs the prompt generation process in a background task."""
        try:
            # Re-configure generator based on run config
            self.test_case_generator.n = attack_config.iterations
            self.test_case_generator.domain = attack_config.domain
            self.test_case_generator.engine = attack_config.parameters.get("engine", "ollama")
            self.test_case_generator.ollama_model = attack_config.model # Correctly setting the ollama_model from attack_config.model
            self.test_case_generator.seed = self.run_counter # Use run_counter for varied seeds

            # Generate prompts
            generated_prompts_df = await self.test_case_generator.generate(
                run_id=run_id, # Pass run_id to the generator
                run_counter=self.run_counter, # Pass run_counter to the generator
            )

            # Save generated prompts to DB and broadcast
            new_attack_ids = []
            for index, row in generated_prompts_df.iterrows():
                # Create AttackData object
                attack_record = AttackData(
                    index=index,
                    prompt=row["prompt"],
                    metadata=row.to_dict()
                )
                # Save to DB and get the ID
                attack_id = await self.db_client.create_attack_data(run_id, attack_record)
                new_attack_ids.append(attack_id)

                # Broadcast to frontend using the correct room (run_id)
                await self.api_gateway.sio.emit("attack_generated", {
                    "runId": run_id,
                    "prompt": attack_record.dict(),
                    "stats": {"totalPrompts": len(generated_prompts_df), "current": index + 1}
                }, room=run_id)
            
            # Update DBRunInDB with the new attack IDs and status
            # run_db.attack_ids.extend(new_attack_ids) # attack_ids is not in DBRunInDB
            # DBRunInDB uses attack_store_ref, so we might need a separate update for that or a different approach
            # For now, let's assume we update the run status and the attack data is linked via run_id in its own collection.
            run_db.status = "attack_phase_complete"
            run_db.updated_at = datetime.datetime.utcnow()
            await self.db_client.update_run(run_id, run_db.dict(by_alias=True))
            await self.api_gateway.sio.emit("attack_completed", {"runId": run_id, "message": "Attack phase completed."}, room=run_id)

        except Exception as e:
            # Handle exceptions during generation
            run_db.status = "attack_error"
            run_db.updated_at = datetime.datetime.utcnow()
            await self.db_client.update_run(run_id, run_db.dict(by_alias=True))
            await self.api_gateway.sio.emit("attack_error", {"runId": run_id, "message": str(e)}, room=run_id)
        finally:
            # Clean up or reset any generator states if necessary
            pass

        @self.api_gateway.app.post("/api/runs/{runId}/attack/stop", response_model=Dict[str, str])
        async def stop_attack_generation(runId: str):
            run_db_data = await self.db_client.get_run(runId)
            if not run_db_data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

            run_db_data = await self.db_client.get_run(runId)
            if not run_db_data:
                raise HTTPException(status_code=404, detail=f"Run with id {runId} not found")
            run_db = DBRunInDB(**run_db_data.dict()) # Convert to DBRunInDB
            run_db.status = "paused"
            run_db.updated_at = datetime.datetime.utcnow()
            await self.db_client.update_run(runId, run_db.dict(by_alias=True))

            await self.api_gateway.sio.emit("attack_stopped", {"runId": runId, "message": "Attack phase stopped."}, room=run_id)
            return {"message": "Attack phase stopped.", "status": "paused"}

        # WebSocket Event Handlers
        @self.api_gateway.sio.on("join_run_channel")
        async def handle_join_run_channel(sid, data):
            run_id = data.get("runId")
            if run_id:
                await self.api_gateway.sio.enter_room(sid, run_id)
                print(f"Client {sid} joined run channel: {run_id}")
                # Optionally, send current state of the run upon joining
                run_db_data = await self.db_client.get_run(run_id)
                if run_db_data:
                    run = DBRunInDB(**run_db_data)
                    await self.api_gateway.sio.emit("run_state_update", {"runId": run_id, "state": run.dict(by_alias=True)}, room=run_id)

        @self.api_gateway.sio.on("leave_run_channel")
        async def handle_leave_run_channel(sid, data):
            run_id = data.get("runId")
            if run_id:
                await self.api_gateway.sio.leave_room(sid, run_id)
                print(f"Client {sid} left run channel: {run_id}")

    def run(self):
        print("Registering routes...")
        self.register_routes()
        print("Routes registered.")

# Example of how to initialize and use the orchestrator
# async def main():
#     db_client = DatabaseClient()
#     await db_client.connect()
#     # Assuming APIGateway is initialized elsewhere and passed here
#     # api_gateway = APIGateway(db_client, None) # orchestrator is None here
#     # orchestrator = LimitedOrchestrator(db_client, api_gateway)
#     # orchestrator.run()
#     # await db_client.close()

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(APIGateway(DatabaseClient(), None).get_app(), host="0.0.0.0", port=8000)
