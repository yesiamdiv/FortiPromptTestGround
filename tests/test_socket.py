"""
Comprehensive WebSocket Test for Run and Attack Endpoints

This test verifies:
1. Run creation with empty config
2. WebSocket connection and room joining
3. Attack config update via API
4. Attack generation start via API
5. WebSocket events reception (attack_generated, attack_completed, etc.)
6. Proper event ordering and data structure
"""

import asyncio
import httpx
import socketio
from datetime import datetime
from typing import Dict, Any, List
import json

API_BASE_URL = "http://localhost:8000/api"
WEBSOCKET_URL = "http://localhost:8000"

# Track received events for verification
received_events = {
    "connect": False,
    "run_state_update": [],
    "attack_started": [],
    "attack_generated": [],
    "attack_completed": [],
    "attack_error": [],
    "attack_stopped": []
}

# ==========================================
# API HELPER FUNCTIONS
# ==========================================

async def create_new_run(name: str = "WebSocket Test Run"):
    """Create a new run with empty config"""
    run_data = {
        "name": name,
        "description": "Run for testing WebSocket broadcasts",
    }
    
    print(f"\n{'='*60}")
    print(f"📝 Creating new run: {name}")
    print(f"{'='*60}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{API_BASE_URL}/runs", json=run_data)
            response.raise_for_status()
            result = response.json()
            
            print(f"✅ Run created successfully!")
            print(f"   Run ID: {result.get('run_id')}")
            print(f"   Status: {result.get('status')}")
            print(f"   Config: {json.dumps(result.get('config', {}), indent=2)}")
            
            return result
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error creating run: {e.response.status_code}")
        print(f"   Response: {e.response.text}")
        return None
    except Exception as e:
        print(f"❌ Error creating run: {e}")
        return None


async def update_attack_config(run_id: str, config_data: Dict[str, Any]):
    """Update attack configuration for a run"""
    print(f"\n{'='*60}")
    print(f"⚙️  Updating attack config for run: {run_id}")
    print(f"{'='*60}")
    print(f"Config: {json.dumps(config_data, indent=2)}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.put(
                f"{API_BASE_URL}/runs/{run_id}/attack/config", 
                json=config_data
            )
            response.raise_for_status()
            result = response.json()
            
            print(f"✅ Attack config updated successfully!")
            return True
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error updating config: {e.response.status_code}")
        print(f"   Response: {e.response.text}")
        return False
    except Exception as e:
        print(f"❌ Error updating attack config: {e}")
        return False


async def start_attack_generation(run_id: str, resume: bool = False):
    """Start attack generation for a run"""
    start_payload = {"resumeFromLastSaved": resume}
    
    print(f"\n{'='*60}")
    print(f"🚀 Starting attack generation for run: {run_id}")
    print(f"{'='*60}")
    print(f"Resume from last saved: {resume}")
    
    try:
        async with httpx.AsyncClient() as client:
            print ("\n\nSTARTING NOW\n\n")
            response = await client.post(
                f"{API_BASE_URL}/runs/{run_id}/attack/start", 
                content=json.dumps(start_payload),
                headers={'Content-Type': 'application/json'}
            )
            print ("\n\nGOT RESPONSE BACK TO START ATTACK\n\n")

            response.raise_for_status()
            result = response.json()
            
            print(f"✅ Attack generation started!")
            print(f"   Message: {result.get('message')}")
            print(f"   Status: {result.get('status')}")
            
            return True
    except httpx.HTTPStatusError as e:
        print(f"❌ HTTP Error starting attack: {e.response.status_code}")
        print(f"   Response: {e.response.text}")
        return False
    except httpx.RequestError as e:
        print(f"❌ Request Error starting attack: {e}")
        return False
    except httpx.ConnectError as e:
        print(f"❌ Connection Error starting attack: {e}")
        return False


async def get_attack_stats(run_id: str):
    """Get attack statistics"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{API_BASE_URL}/runs/{run_id}/attack/stats")
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"❌ Error getting attack stats: {e}")
        return None


# ==========================================
# WEBSOCKET TEST
# ==========================================

async def test_websocket_flow():
    """Main WebSocket test flow"""
    sio_client = socketio.AsyncClient()
    current_run_id = None
    test_passed = True

    # ==========================================
    # WebSocket Event Handlers
    # ==========================================
    
    @sio_client.event
    async def connect():
        nonlocal current_run_id, test_passed
        
        print(f"\n{'='*60}")
        print(f"🔌 WebSocket connected!")
        print(f"{'='*60}")
        received_events["connect"] = True
        
        try:
            # Step 1: Create a new run
            run_info = await create_new_run()
            if not run_info:
                print("❌ Failed to create run")
                test_passed = False
                await sio_client.disconnect()
                return
            
            current_run_id = run_info.get("run_id")
            if not current_run_id:
                print("❌ No run_id in response")
                test_passed = False
                await sio_client.disconnect()
                return
            
            # Step 2: Join the run channel
            print(f"\n{'='*60}")
            print(f"📡 Joining run channel: {current_run_id}")
            print(f"{'='*60}")
            
            await sio_client.emit("join_run_channel", {"runId": current_run_id})
            
            # Wait a bit for initial state
            await asyncio.sleep(1)
            
            # Step 3: Update attack config
            attack_config = {
                "model": "dolphin-mistral:7b",
                "attackStrategy": "multi_turn",
                "domain": "cybersecurity",
                "modelUrl": "http://localhost:11434/api/generate",
                "iterations": 20,  # Small number for testing
                "parameters": {
                    "temperature": 0.7,
                    "engine": "ollama"
                }
            }
            
            config_updated = await update_attack_config(current_run_id, attack_config)
            if not config_updated:
                print("❌ Failed to update attack config")
                test_passed = False
                await sio_client.disconnect()
                return
            
            # Wait a bit for config update event
            await asyncio.sleep(1)
            
            # Step 4: Start attack generation
            attack_started = await start_attack_generation(current_run_id)
            if not attack_started:
                print("❌ Failed to start attack generation")
                test_passed = False
                await sio_client.disconnect()
                return
            
            print(f"\n{'='*60}")
            print(f"⏳ Waiting for attack generation to complete...")
            print(f"{'='*60}")
            
        except Exception as e:
            print(f"❌ Error in connect handler: {e}")
            test_passed = False
            await sio_client.disconnect()

    @sio_client.event
    async def disconnect():
        print(f"\n{'='*60}")
        print(f"🔌 WebSocket disconnected")
        print(f"{'='*60}")

    @sio_client.event
    async def run_state_update(data):
        """Receive run state updates"""
        received_events["run_state_update"].append(data)
        
        update_type = data.get("type", "unknown")
        print(f"\n📊 Run State Update ({update_type}):")
        
        if update_type == "initial_state":
            state = data.get("state", {})
            print(f"   Run ID: {state.get('run_id')}")
            print(f"   Status: {state.get('status')}")
            print(f"   Config keys: {list(state.get('config', {}).keys())}")
        elif update_type == "config_update":
            config = data.get("config", {})
            print(f"   Updated config: {list(config.keys())}")
        else:
            print(f"   Data: {json.dumps(data, indent=2)[:200]}...")

    @sio_client.event
    async def attack_started(data):
        """Attack generation started"""
        received_events["attack_started"].append(data)
        print(f"\n🚀 Attack Started:")
        print(f"   Run ID: {data.get('runId')}")
        print(f"   Message: {data.get('message')}")

    @sio_client.event
    async def attack_generated(data):
        """Individual attack prompt generated"""
        received_events["attack_generated"].append(data)
        
        stats = data.get("stats", {})
        current = stats.get("current", 0)
        total = stats.get("totalPrompts", 0)
        percentage = stats.get("percentage", 0)
        
        print(f"📝 Attack Generated [{current}/{total}] - {percentage}%")

    @sio_client.event
    async def attack_completed(data):
        """Attack generation completed"""
        received_events["attack_completed"].append(data)
        
        print(f"\n{'='*60}")
        print(f"✅ Attack Completed!")
        print(f"{'='*60}")
        print(f"   Run ID: {data.get('runId')}")
        print(f"   Message: {data.get('message')}")
        print(f"   Total Prompts: {data.get('totalPrompts')}")
        
        # Get final stats
        run_id = data.get('runId')
        if run_id:
            stats = await get_attack_stats(run_id)
            if stats:
                print(f"\n📊 Final Stats:")
                print(f"   {json.dumps(stats, indent=2)}")
        
        # Test complete, disconnect
        await asyncio.sleep(2)
        await sio_client.disconnect()

    @sio_client.event
    async def attack_error(data):
        """Attack generation error"""
        received_events["attack_error"].append(data)
        
        print(f"\n❌ Attack Error:")
        print(f"   Run ID: {data.get('runId')}")
        print(f"   Message: {data.get('message')}")
        print(f"   Error Type: {data.get('error')}")
        
        # Disconnect on error
        await asyncio.sleep(2)
        await sio_client.disconnect()

    @sio_client.event
    async def attack_stopped(data):
        """Attack generation stopped"""
        received_events["attack_stopped"].append(data)
        print(f"\n⏸️  Attack Stopped:")
        print(f"   Run ID: {data.get('runId')}")
        print(f"   Message: {data.get('message')}")

    # ==========================================
    # Run the test
    # ==========================================
    
    try:
        print(f"\n{'='*60}")
        print(f"🧪 Starting WebSocket Flow Test")
        print(f"{'='*60}")
        
        await sio_client.connect(WEBSOCKET_URL)
        
        # Wait for test to complete (will disconnect automatically)
        await sio_client.wait()
        
    except asyncio.CancelledError:
        print("⚠️  WebSocket test cancelled")
    except Exception as e:
        print(f"❌ WebSocket connection error: {e}")
        test_passed = False
    finally:
        if sio_client.connected:
            await sio_client.disconnect()
    
    # ==========================================
    # Print Test Results
    # ==========================================
    
    print(f"\n{'='*60}")
    print(f"📋 TEST RESULTS")
    print(f"{'='*60}")
    
    print(f"\n✓ Events Received:")
    print(f"   Connected: {received_events['connect']}")
    print(f"   Run State Updates: {len(received_events['run_state_update'])}")
    print(f"   Attack Started: {len(received_events['attack_started'])}")
    print(f"   Attack Generated: {len(received_events['attack_generated'])}")
    print(f"   Attack Completed: {len(received_events['attack_completed'])}")
    print(f"   Attack Errors: {len(received_events['attack_error'])}")
    
    # Verify test passed
    checks = [
        ("WebSocket connected", received_events['connect']),
        ("Received initial state", len(received_events['run_state_update']) > 0),
        ("Attack started event", len(received_events['attack_started']) > 0),
        ("Attack prompts generated", len(received_events['attack_generated']) > 0),
        ("Attack completed", len(received_events['attack_completed']) > 0),
        ("No errors", len(received_events['attack_error']) == 0)
    ]
    
    print(f"\n✓ Verification:")
    all_passed = True
    for check_name, check_result in checks:
        status = "✅" if check_result else "❌"
        print(f"   {status} {check_name}")
        if not check_result:
            all_passed = False
    
    print(f"\n{'='*60}")
    if all_passed and test_passed:
        print(f"✅ ALL TESTS PASSED!")
    else:
        print(f"❌ SOME TESTS FAILED")
    print(f"{'='*60}\n")


async def main():
    await test_websocket_flow()


if __name__ == "__main__":
    asyncio.run(main())