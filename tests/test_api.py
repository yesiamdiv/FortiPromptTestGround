# test_api.py

import asyncio
import json
import httpx
import socketio
from datetime import datetime
from typing import Dict, Any, List

# Assuming the API is running on http://localhost:8000
API_BASE_URL = "http://localhost:8000/api"
WEBSOCKET_URL = "http://localhost:8000"

# --- Helper Functions ---

def get_current_time_iso():
    return datetime.utcnow().isoformat() + "Z"

# --- HTTP Endpoint Tests ---

async def test_create_run():
    print("\n--- Testing POST /api/runs ---")
    run_data = {
        "run_id": "test-run-123",
        "name": "My Test Run",
        "status": "initialized",
        "description":"some description",
        "components": {"component1": "something1", "component2": "something2"},
        "config": {
            "attack_config": {
                "iterations": 5,
                "domain": "cybersecurity",
                "parameters": {"engine": "ollama", "model": "dolphin-mistral:7b-v2.6"}
            }
        },
        "created_at": get_current_time_iso(),
        "updated_at": get_current_time_iso()
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_BASE_URL}/runs", json=run_data)
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.json()}")
            return response.json()
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r} : {e}")
        return None

async def test_get_runs():
    print("\n--- Testing GET /api/runs ---")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE_URL}/runs")
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.json()}")
            return response.json()
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r} : {e}")
        return None

async def test_update_run(run_id: str):
    print(f"\n--- Testing PATCH /api/runs/{{runId}} ---")
    update_data = {
        "status": "running",
        "config": {
            "attack_config": {
                "iterations": 10,
                "model": "dolphin-mistral:7b-v2.6",
                "attackStrategy": "single_turn",
                "domain": "cybersecurity",
                "modelUrl": "http://localhost:11434/api/generate",
                "parameters": {"temperature": 0.7}
            }
        }
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.patch(f"{API_BASE_URL}/runs/{run_id}", json=update_data)
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.json()}")
            return response.json()
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r} : {e}")
        return None

async def test_delete_run(run_id: str):
    print(f"\n--- Testing DELETE /api/runs/{{runId}} ---")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.delete(f"{API_BASE_URL}/runs/{run_id}")
            print(f"Status Code: {response.status_code}")
            return response.status_code
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r} : {e}")
        return None

async def test_attack_config(run_id: str):
    print(f"\n--- Testing Attack Config for Run: {run_id} ---")
    # Test GET attack config
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE_URL}/runs/{run_id}/attack/config")
            print(f"GET /attack/config Status Code: {response.status_code}")
            print(f"GET /attack/config Response: {response.json()}")
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r} : {e}")

    # Test PUT attack config
    new_config = {
        "model": "claude-3-opus",
        "attackStrategy": "multi_turn",
        "domain": "data_exfiltration",
        "modelUrl": "https://api.anthropic.com/v1/messages",
        "iterations": 15,
        "parameters": {"temperature": 0.7}
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(f"{API_BASE_URL}/runs/{run_id}/attack/config", json=new_config)
            print(f"PUT /attack/config Status Code: {response.status_code}")
            print(f"PUT /attack/config Response: {response.json()}")
            return response.json()
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r} : {e}")
        return None

async def test_attack_prompts(run_id: str):
    print(f"\n--- Testing Attack Prompts for Run: {run_id} ---")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE_URL}/runs/{run_id}/attack/prompts")
            print(f"GET /attack/prompts Status Code: {response.status_code}")
            print(f"GET /attack/prompts Response: {response.json()}")
            return response.json()
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r} : {e}")
        return None

async def test_attack_stats(run_id: str):
    print(f"\n--- Testing Attack Stats for Run: {run_id} ---")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE_URL}/runs/{run_id}/attack/stats")
            print(f"GET /attack/stats Status Code: {response.status_code}")
            print(f"GET /attack/stats Response: {response.json()}")
            return response.json()
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r} : {e}")
        return None

async def test_start_stop_attack(run_id: str):
    print(f"\n--- Testing Start/Stop Attack for Run: {run_id} ---")
    # Test POST start attack
    start_payload = {"resumeFromLastSaved": False}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_BASE_URL}/runs/{run_id}/attack/start", json=start_payload)
            print(f"POST /attack/start Status Code: {response.status_code}")
            print(f"POST /attack/start Response: {response.json()}")
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r} : {e}")

    # Give some time for the background task to potentially run and broadcast
    await asyncio.sleep(5) # Adjust sleep time as needed

    # Test POST stop attack
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_BASE_URL}/runs/{run_id}/attack/stop")
            print(f"POST /attack/stop Status Code: {response.status_code}")
            print(f"POST /attack/stop Response: {response.json()}")
    except httpx.RequestError as e:
        print(f"An error occurred while requesting {e.request.url!r} : {e}")

# --- WebSocket Handler Tests ---

async def test_websocket_connection(run_id: str):
    print(f"\n--- Testing WebSocket Connection for Run: {run_id} ---")
    sio_client = socketio.AsyncClient()

    @sio_client.event
    async def connect():
        print(f"WebSocket connected. Joining room: {run_id}")
        await sio_client.emit("join_run_channel", {"runId": run_id})

    @sio_client.event
    async def disconnect():
        print("WebSocket disconnected.")

    @sio_client.event
    async def attack_generated(data):
        print(f"Received attack_generated: {data}")

    @sio_client.event
    async def attack_completed(data):
        print(f"Received attack_completed: {data}")

    @sio_client.event
    async def attack_error(data):
        print(f"Received attack_error: {data}")
        
    @sio_client.event
    async def run_state_update(data):
        print(f"Received run_state_update: {data}")

    try:
        await sio_client.connect(WEBSOCKET_URL)
        # Keep the connection open for a short period to receive events
        await asyncio.sleep(10) # Adjust sleep time as needed
        await sio_client.disconnect()
    except Exception as e:
        print(f"WebSocket connection or event handling error: {e}")

# --- Main Test Execution ---

async def main():
    # Test the run lifecycle
    created_run = await test_create_run()
    print(f"Type of run_id returned by test_create_run: {type(created_run.get('run_id'))}")
    run_id = created_run.get("run_id") if created_run else None
    if run_id and isinstance(run_id, dict):
        run_id = run_id.get('run_id') # Ensure run_id is a string

    if run_id:
        await test_get_runs()
        await test_update_run(run_id)
        await test_attack_config(run_id)
        await test_attack_prompts(run_id)
        await test_attack_stats(run_id)
        await test_start_stop_attack(run_id)
        await test_websocket_connection(run_id)
        # await test_delete_run(run_id) # Uncomment to test delete run
    else:
        print("Failed to create run, skipping further tests.")

if __name__ == "__main__":
    asyncio.run(main())
