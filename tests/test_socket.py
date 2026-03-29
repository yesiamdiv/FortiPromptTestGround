import asyncio
import httpx
import socketio
from datetime import datetime
from typing import Dict, Any, List

API_BASE_URL = "http://localhost:8000/api"
WEBSOCKET_URL = "http://localhost:8000"

async def get_current_time_iso():
    return datetime.utcnow().isoformat() + "Z"

async def create_new_run():
    run_data = {
        "name": "WebSocket Test Run",
        "description": "Run for testing WebSocket broadcasts",
        "components": {"attack": "ollama_attacker", "defender": "llm_defender"}
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_BASE_URL}/runs", json=run_data)
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        print(f"Error creating run: {e}")
        return None

async def update_attack_config(run_id: str, config_data: Dict[str, Any]):
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(f"{API_BASE_URL}/runs/{run_id}/attack/config", json=config_data)
            response.raise_for_status()
            print(f"Attack config updated for run {run_id}: {response.json()}")
            return True
    except httpx.RequestError as e:
        print(f"Error updating attack config for run {run_id}: {e}")
        return False


async def start_attack_generation(run_id: str):
    start_payload = {"resumeFromLastSaved": False}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_BASE_URL}/runs/{run_id}/attack/start", json=start_payload)
            response.raise_for_status()
            print(f"Attack generation started for run {run_id}: {response.json()}")
            return True
    except httpx.RequestError as e:
        print(f"Error starting attack generation for run {run_id}: {e}")
        return False

async def test_websocket_broadcasts():
    sio_client = socketio.AsyncClient()
    current_run_id = None

    @sio_client.event
    async def connect():
        nonlocal current_run_id
        print("WebSocket connected.")
        
        # Create a new run
        run_info = await create_new_run()
        if run_info:
            current_run_id = run_info.get("run_id")
            print(f"Created new run with ID: {current_run_id}")
            if current_run_id:
                print(f"Joining run channel: {current_run_id}")
                await sio_client.emit("join_run_channel", {"runId": current_run_id})
                # Start attack generation
                await start_attack_generation(current_run_id)

                # Update attack config after run creation
                attack_config_payload = {
                    "model": "claude-3-opus",
                    "attackStrategy": "multi_turn",
                    "domain": "data_exfiltration",
                    "modelUrl": "https://api.anthropic.com/v1/messages",
                    "iterations": 15,
                    "parameters": {"temperature": 0.7, "engine": "ollama"}
                }
                await update_attack_config(current_run_id, attack_config_payload)
            else:
                print("Failed to get run_id after creation.")
                await sio_client.disconnect()
        else:
            print("Failed to create a new run. Disconnecting.")
            await sio_client.disconnect()

    @sio_client.event
    async def disconnect():
        print("WebSocket disconnected.")

    @sio_client.event
    async def attack_generated(data):
        print(f"Received attack_generated: {data}")

    @sio_client.event
    async def attack_completed(data):
        print(f"Received attack_completed: {data}")
        # Optionally stop the client if attack is completed
        # await sio_client.disconnect()

    @sio_client.event
    async def attack_error(data):
        print(f"Received attack_error: {data}")
        # Optionally stop the client if an error occurs
        # await sio_client.disconnect()
        
    @sio_client.event
    async def run_state_update(data):
        print(f"Received run_state_update: {data}")

    try:
        await sio_client.connect(WEBSOCKET_URL)
        print("Connected to WebSocket server. Keeping connection alive...")
        # Keep the connection open indefinitely until manually stopped
        await asyncio.Future() 
    except asyncio.CancelledError:
        print("WebSocket test cancelled.")
    except Exception as e:
        print(f"WebSocket connection or event handling error: {e}")
    finally:
        if sio_client.connected:
            await sio_client.disconnect()

async def main():
    await test_websocket_broadcasts()

if __name__ == "__main__":
    asyncio.run(main())
