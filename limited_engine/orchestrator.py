# Limited Engine Orchestrator

import asyncio
from typing import Dict, Any, List
from bson import ObjectId
from fastapi import APIRouter, HTTPException, status
from api_gateway import APIGateway
from db import DatabaseClient
# Import API schemas
from api_gateway.schemas import AttackPrompt, AttackStats, RunCreateRequest, RunResponse, AttackConfig, DefenseConfig, RunUpdateRequest, StartAttackResponse, StopAttackResponse 
# Import DB models
from db.models import Run as DBRun, RunInDB as DBRunInDB, AttackData, RunConfig # Import necessary schemas
from datetime import datetime, timezone
from db import initialize_database
from limited_engine.redgen.generator import TestCaseGenerator
import os
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
        # ==========================================
        # RUNS ROUTES
        # ==========================================
        
        @self.api_gateway.app.get("/api/runs", response_model=List[RunResponse])
        async def get_runs():
            """Get all runs"""
            runs = await self.db_client.get_runs()
            # Convert DBRunInDB objects to RunResponse schema
            return [RunResponse(
                run_id=run.run_id,
                name=run.name,
                description=run.description,
                status=run.status,
                components=run.components,
                config=run.config.dict() if hasattr(run.config, 'dict') else run.config,
                created_at=run.created_at,
                updated_at=run.updated_at
            ) for run in runs]


        @self.api_gateway.app.post("/api/runs", status_code=status.HTTP_201_CREATED, response_model=RunResponse)
        async def create_run(run_data: RunCreateRequest):
            """
            Create a new run with EMPTY config.
            Config (attack_config, defense_config, evaluation_config) will be updated later via separate endpoints.
            """
            self.run_counter += 1
            run_id = str(ObjectId()) # Generate a new ObjectId for run_id
            
            # Initialize run with EMPTY config - no attack/defense/eval config yet
            # Those will be set later via PUT endpoints
            new_run = DBRunInDB(
                run_id=run_id,
                name=run_data.name,
                status="initialized",
                description=run_data.description or "",
                components=run_data.components or [],
                config=RunConfig(
                    global_config={},
                    attack_config={},
                    defense_config={},
                    evaluation_config={}
                ),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            
            await self.db_client.create_run(new_run)
            
            # Store in memory for quick access (optional, depends on orchestrator's needs)
            self.runs[run_id] = new_run.dict(by_alias=True)
            
            print(f"✅ Created new run: {run_id} with name: {run_data.name}")
            
            # Return the created run response
            return RunResponse(
                run_id=new_run.run_id,
                name=new_run.name,
                status=new_run.status,
                description=new_run.description or "",
                components=new_run.components or [],
                config=new_run.config.dict(),
                created_at=new_run.created_at,
                updated_at=new_run.updated_at
            )

        # @self.api_gateway.app.patch("/api/runs/{runId}", response_model=RunResponse)
        # async def update_run(runId: str, run_update: RunUpdateRequest):
        #     """
        #     Update run fields (status, name, etc.)
        #     For config updates, use specific config endpoints instead.
        #     """
        #     # Fetch the existing run from DB
        #     existing_run_db = await self.db_client.get_run(runId)
        #     if not existing_run_db:
        #         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

        #     # Update only top-level fields (status, name, etc.)
        #     # Don't update config here - use specific endpoints for that
        #     allowed_fields = ['status', 'name']
        #     for key, value in run_update.items():
        #         if key in allowed_fields and hasattr(existing_run_db, key):
        #             setattr(existing_run_db, key, value)

        #     existing_run_db.updated_at = datetime.now(timezone.utc)

        #     # Update the run in the database
        #     updated = await self.db_client.update_run(runId, existing_run_db.dict(by_alias=True))
        #     if not updated:
        #         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update run")

        #     # Fetch the updated run to return
        #     updated_run_in_db = await self.db_client.get_run(runId)
        #     if not updated_run_in_db:
        #          raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found after update")
            
        #     print(f"✅ Updated run: {runId} - Status: {updated_run_in_db.status}")
            
        #     # Map DBRunInDB model to RunResponse for API response
        #     return RunResponse(
        #         run_id=updated_run_in_db.run_id,
        #         name=updated_run_in_db.name,
        #         status=updated_run_in_db.status,
        #         description=updated_run_in_db.description,
        #         components=updated_run_in_db.components,
        #         config=updated_run_in_db.config.dict() if hasattr(updated_run_in_db.config, 'dict') else updated_run_in_db.config,
        #         created_at=updated_run_in_db.created_at,
        #         updated_at=updated_run_in_db.updated_at
        #     )

        @self.api_gateway.app.patch("/api/runs/{runId}", response_model=RunResponse)
        async def update_run(runId: str, run_update: RunUpdateRequest):
            """
            Update run fields (status, name, description).
            For config updates, use specific config endpoints instead.
            """
            existing_run_db = await self.db_client.get_run(runId)
            if not existing_run_db:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

            # Extract only provided fields
            update_data = run_update.dict(exclude_unset=True)

            # Apply updates safely
            for key, value in update_data.items():
                if hasattr(existing_run_db, key):
                    setattr(existing_run_db, key, value)

            existing_run_db.updated_at = datetime.now(timezone.utc)

            # Save to DB
            updated = await self.db_client.update_run(runId, existing_run_db.dict(by_alias=True))
            if not updated:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update run")

            # Fetch updated run
            updated_run = await self.db_client.get_run(runId)
            if not updated_run:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found after update")

            return RunResponse(
                run_id=updated_run.run_id,
                name=updated_run.name,
                status=updated_run.status,
                description=updated_run.description or "",
                components=updated_run.components or [],
                config=updated_run.config.dict() if hasattr(updated_run.config, 'dict') else updated_run.config,
                created_at=updated_run.created_at,
                updated_at=updated_run.updated_at
            )


        @self.api_gateway.app.delete("/api/runs/{runId}", status_code=status.HTTP_204_NO_CONTENT)
        async def delete_run(runId: str):
            """Delete a run"""
            deleted = await self.db_client.delete_run(runId)
            if not deleted:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
            print(f"✅ Deleted run: {runId}")

        # ==========================================
        # ATTACK CONFIG ROUTES
        # ==========================================
        
        @self.api_gateway.app.get("/api/runs/{runId}/attack/config", response_model=AttackConfig)
        async def get_attack_config(runId: str):
            """Get attack configuration for a run"""
            run_db = await self.db_client.get_run(runId)
            if not run_db:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
            
            # Get attack_config from run's config
            # Handle both dict and object formats
            if hasattr(run_db.config, 'attack_config'):
                attack_config_dict = run_db.config.attack_config
            elif isinstance(run_db.config, dict):
                attack_config_dict = run_db.config.get('attack_config', {})
            else:
                attack_config_dict = {}
            
            # If empty, return default AttackConfig
            if not attack_config_dict:
                return AttackConfig(
                    model="",
                    attackStrategy="",
                    domain="",
                    modelUrl="",
                    iterations=0,
                    parameters={}
                )
            
            return AttackConfig(**attack_config_dict)

        @self.api_gateway.app.put("/api/runs/{runId}/attack/config", response_model=AttackConfig)
        async def update_attack_config(runId: str, config_data: AttackConfig):
            """
            Update attack configuration for a run.
            This is called AFTER run creation to set up attack parameters.
            """
            print('RUN_ID : ',runId)
            run_db = await self.db_client.get_run(runId)
            if not run_db:
                print('\n\n',run_db,'\n\n')
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

            # Update the attack_config
            # Handle both Pydantic model and dict
            if hasattr(run_db.config, 'attack_config'):
                run_db.config.attack_config = config_data.dict()
            elif isinstance(run_db.config, dict):
                run_db.config['attack_config'] = config_data.dict()
            else:
                # If config is somehow not initialized properly, recreate it
                run_db.config = RunConfig(
                    global_config={},
                    attack_config=config_data.dict(),
                    defense_config={},
                    evaluation_config={}
                )
            
            run_db.updated_at = datetime.now(timezone.utc)
            
            # Update in database
            await self.db_client.update_run(runId, run_db.dict(by_alias=True))

            print(f"✅ Updated attack config for run: {runId}")
            print(f"   Model: {config_data.model}, Strategy: {config_data.attackStrategy}, Iterations: {config_data.iterations}")

            # Broadcast config update to frontend via WebSocket
            await self.api_gateway.sio.emit("run_state_update", {
                "runId": runId,
                "type": "config_update",
                "config": {
                    "attack_config": config_data.dict()
                }
            }, room=runId)

            return config_data

        # @self.api_gateway.app.get("/api/runs/{runId}/attack/prompts", response_model=List[Dict[str, Any]])
        # async def get_attack_prompts(runId: str):
        #     """Get all attack prompts for a run"""
        #     run_db = await self.db_client.get_run(runId)
        #     if not run_db:
        #         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
            
        #     # Get all attack data for the run
        #     attack_data_list = await self.db_client.get_attack_data_for_run(runId)
        #     return [attack.dict() for attack in attack_data_list]


        @self.api_gateway.app.get(
            "/api/runs/{runId}/attack/prompts",
            response_model=List[AttackPrompt]
        )
        async def get_attack_prompts(runId: str):
            """Get all attack prompts for a run"""
            run_db = await self.db_client.get_run(runId)
            if not run_db:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

            attack_data_list = await self.db_client.get_attack_data_for_run(runId)

            return [
                AttackPrompt(
                    promptId=f"prompt-{attack.index}",
                    content=attack.prompt,
                    status="generated",  # You can enhance this later
                    timestamp=datetime.now(timezone.utc).isoformat() + "Z"
                )
                for attack in attack_data_list
            ]
        
        
        # @self.api_gateway.app.get("/api/runs/{runId}/attack/stats", response_model=Dict[str, Any])
        # async def get_attack_stats(runId: str):
        #     """Get attack statistics for a run"""
        #     run_db = await self.db_client.get_run(runId)
        #     if not run_db:
        #         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
            
        #     # Get all attack data for the run to calculate stats
        #     attack_data_list = await self.db_client.get_attack_data_for_run(runId)
        #     total_prompts = len(attack_data_list)
            
        #     # Calculate more detailed stats
        #     stats = {
        #         "totalPrompts": total_prompts,
        #         "pendingAttacks": 0,
        #         "attacksGenerated": total_prompts
        #     }
            
        #     return stats

        @self.api_gateway.app.get(
            "/api/runs/{runId}/attack/stats",
            response_model=AttackStats
        )
        async def get_attack_stats(runId: str):
            """Get attack statistics for a run"""
            run_db = await self.db_client.get_run(runId)
            if not run_db:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

            attack_data_list = await self.db_client.get_attack_data_for_run(runId)
            total_prompts = len(attack_data_list)

            return AttackStats(
                totalPrompts=total_prompts,
                pendingAttacks=0,  # can improve later
                attacksGenerated=total_prompts
            )


        # ==========================================
        # ATTACK CONTROL ROUTES
        # ==========================================
        
        @self.api_gateway.app.post("/api/runs/{runId}/attack/start",response_model=StartAttackResponse)
        async def start_attack_generation(runId: str, payload: Dict[str, bool]):
            """
            Start attack generation for a run.
            Requires attack_config to be set first via PUT /attack/config endpoint.
            """
            run_db = await self.db_client.get_run(runId)
            if not run_db:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

            # Check if attack_config is set
            attack_config_dict = {}
            if hasattr(run_db.config, 'attack_config'):
                attack_config_dict = run_db.config.attack_config
            elif isinstance(run_db.config, dict):
                attack_config_dict = run_db.config.get('attack_config', {})
            
            if not attack_config_dict or not attack_config_dict.get('model'):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, 
                    detail="Attack config not set. Please set attack config first using PUT /api/runs/{runId}/attack/config"
                )

            resume = payload.get("resumeFromLastSaved", False)
            
            # Update run status in DB
            run_db.status = "running"
            run_db.updated_at = datetime.now(timezone.utc)
            await self.db_client.update_run(runId, run_db.dict(by_alias=True))

            print(f"✅ Starting attack generation for run: {runId}")
            print(f"   Resume from last saved: {resume}")

            # Parse attack config
            attack_config = AttackConfig(**attack_config_dict)
            
            # generation_task = asyncio.create_task(
            #     asyncio.to_thread(
            #         self.run_generation_sync,
            #         runId,
            #         run_db,
            #         attack_config,
            #         resume
            #     )
            # )

            asyncio.create_task(
                self.run_generation_process(runId, run_db, attack_config, resume)
            )

            # Broadcast start event
            await self.api_gateway.sio.emit("attack_started", {
                "runId": runId,
                "message": "Attack generation started",
                "config": attack_config.dict()
            }, room=runId)

            print("\n\nSTARED GENREATION THREAD SENDING RESPONSE")

            return StartAttackResponse(
                message="Attack generation started in background.",
                runId=runId,
                status="running"
            )
        

        @self.api_gateway.app.post("/api/runs/{runId}/attack/stop",response_model=StopAttackResponse)
        async def stop_attack_generation(runId: str):

            """Stop attack generation for a run"""
            run_db = await self.db_client.get_run(runId)
            if not run_db:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

            run_db.status = "paused"
            run_db.updated_at = datetime.now(timezone.utc)
            await self.db_client.update_run(runId, run_db.dict(by_alias=True))

            print(f"✅ Stopped attack generation for run: {runId}")

            # Broadcast stop event
            await self.api_gateway.sio.emit("attack_stopped", {
                "runId": runId, 
                "message": "Attack phase stopped."
            }, room=runId)
            
            return {"message": "Attack phase stopped.", "status": "paused"}

        # ==========================================
        # WEBSOCKET EVENT HANDLERS
        # ==========================================
        
        @self.api_gateway.sio.on("join_run_channel")
        async def handle_join_run_channel(sid, data):
            """
            Handle client joining a run channel.
            Client will receive all updates for this specific run.
            """
            run_id = data.get("runId")
            if not run_id:
                print(f"⚠️  Client {sid} tried to join without runId")
                return
            
            # Use socket_manager to handle room joining
            await self.api_gateway.socket_manager.join_room(sid, run_id)
            print(f"✅ Client {sid} joined run channel: {run_id}")
            
            # Send current state of the run upon joining
            run_db = await self.db_client.get_run(run_id)
            if run_db:
                # Send initial state
                await self.api_gateway.sio.emit("run_state_update", {
                    "runId": run_id,
                    "type": "initial_state",
                    "state": {
                        "run_id": run_db.run_id,
                        "name": run_db.name,
                        "status": run_db.status,
                        "config": run_db.config.dict() if hasattr(run_db.config, 'dict') else run_db.config,
                        "created_at": run_db.created_at.isoformat() if run_db.created_at else None,
                        "updated_at": run_db.updated_at.isoformat() if run_db.updated_at else None
                    }
                }, to=sid)  # Send only to this specific client
                
                print(f"   Sent initial state to client {sid}")
            else:
                print(f"⚠️  Run {run_id} not found when client {sid} joined")

        @self.api_gateway.sio.on("leave_run_channel")
        async def handle_leave_run_channel(sid, data):
            """
            Handle client leaving a run channel.
            """
            run_id = data.get("runId")
            if not run_id:
                print(f"⚠️  Client {sid} tried to leave without runId")
                return
            
            # Use socket_manager to handle room leaving
            await self.api_gateway.socket_manager.leave_room(sid, run_id)
            print(f"✅ Client {sid} left run channel: {run_id}")

        @self.api_gateway.sio.on("disconnect")
        async def handle_disconnect(sid):
            """
            Handle client disconnection.
            Remove from all rooms.
            """
            print(f"🔌 Client {sid} disconnected")
            await self.api_gateway.socket_manager.remove_sid_from_all_rooms(sid)

    # ==========================================
    # BACKGROUND TASK: ATTACK GENERATION
    # ==========================================
    
    async def run_generation_process(self, run_id: str, run_db: DBRunInDB, attack_config: AttackConfig, resume: bool):
        """
        Runs the prompt generation process in a background task.
        Broadcasts progress via WebSocket to all clients in the run's channel.
        """
        try:
            print(f"\n🚀 Starting generation process for run: {run_id}")
            print(f"   Iterations: {attack_config.iterations}")
            print(f"   Domain: {attack_config.domain}")
            print(f"   Model: {attack_config.model}")
            
            # Re-configure generator based on run config
            self.test_case_generator.n = attack_config.iterations
            self.test_case_generator.domain = attack_config.domain
            self.test_case_generator.engine = attack_config.parameters.get("engine", "ollama")
            self.test_case_generator.ollama_model = attack_config.model
            self.test_case_generator.seed = self.run_counter
            self.test_case_generator.output_dir = f"./output/{run_id}"
            self.test_case_generator.run_id = run_id

            print("\n\nACTUAL GENERATION STARTS\n\n")

            # Generate prompts
            # generated_prompts_df = await self.test_case_generator.generate(
            #     run_id=run_id,
            #     run_counter=self.run_counter,
            # )

            generated_prompts_df = await asyncio.to_thread(self.test_case_generator.generate_sync_wrapper,run_id, self.run_counter)

            print(f"✅ Generated {len(generated_prompts_df)} prompts")

            # Save generated prompts to DB and broadcast
            new_attack_ids = []
            for index, row in generated_prompts_df.iterrows():
                # Create AttackData object
                attack_record = AttackData(
                    index=int(index),
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
                    "stats": {
                        "totalPrompts": len(generated_prompts_df), 
                        "current": int(index) + 1,
                        "percentage": int(((int(index) + 1) / len(generated_prompts_df)) * 100)
                    }
                }, room=run_id)
                
                print(f"   📝 Prompt {int(index) + 1}/{len(generated_prompts_df)} generated and broadcast")
            
            # Update run status to completed
            run_db.status = "attack_phase_complete"
            run_db.updated_at = datetime.now(timezone.utc)
            await self.db_client.update_run(run_id, run_db.dict(by_alias=True))
            
            # Broadcast completion
            await self.api_gateway.sio.emit("attack_completed", {
                "runId": run_id, 
                "message": "Attack phase completed.",
                "totalPrompts": len(generated_prompts_df)
            }, room=run_id)
            
            print(f"✅ Attack generation completed for run: {run_id}")

        except Exception as e:
            # Handle exceptions during generation
            print(f"❌ Error in generation process for run {run_id}: {str(e)}")
            
            run_db.status = "attack_error"
            run_db.updated_at = datetime.now(timezone.utc)
            await self.db_client.update_run(run_id, run_db.dict(by_alias=True))
            
            # Broadcast error
            await self.api_gateway.sio.emit("attack_error", {
                "runId": run_id, 
                "message": str(e),
                "error": type(e).__name__
            }, room=run_id)

    def run_generation_sync(self, runId, run_db, attack_config, resume):
        asyncio.run(
            self.run_generation_process(runId, run_db, attack_config, resume)
        )

    def run(self):
        """Initialize and register all routes"""
        print("🔧 Registering routes...")
        self.register_routes()
        print("✅ Routes registered.")