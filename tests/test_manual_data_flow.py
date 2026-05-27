#!/usr/bin/env python3
"""
Diagnostic Script: Manual Turn Data Flow

This script checks if attack/defence/evaluation data is being saved correctly for manual runs.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from server.database.connection import init_db, close_db, get_db
from server.database.operations import get_db_ops


async def test_manual_turn_data_retrieval():
    """Test manual turn data retrieval"""
    print("="*70)
    print("Manual Turn Data Flow Diagnostic")
    print("="*70)
    print()
    
    try:
        import os
        mongo_url = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        db_name = os.getenv("MONGODB_DB_NAME", "adversarial_testing")
        await init_db(mongo_url, db_name)
        print(f"✓ Connected to database: {db_name}")
        print()
    except Exception as e:
        print(f"✗ Failed to connect to database: {e}")
        return
    
    db = get_db()
    if db == None:
        print("✗ Database connection not available")
        return
    
    db_ops = get_db_ops(db)
    
    # Find a manual run
    manual_runs = await db.runs.find({
        "graph_config.graph_type": "manual"
    }).limit(5).to_list(length=None)
    
    if not manual_runs:
        print("⚠ No manual runs found in database")
        return
    
    print(f"Found {len(manual_runs)} manual run(s)")
    print()
    
    for run_doc in manual_runs:
        run_id = run_doc.get("run_id", str(run_doc.get("_id")))
        print(f"Checking Run: {run_id}")
        print(f"  Status: {run_doc.get('status')}")
        print()
        
        # Find sessions for this run
        sessions = await db.manual_sessions.find({"run_id": run_id}).to_list(length=None)
        print(f"  Sessions: {len(sessions)}")
        
        for session in sessions:
            session_id = session.get("session_id")
            print(f"    Session: {session_id}")
            print(f"      Total turns: {session.get('total_turns', 0)}")
            print(f"      Turn IDs: {session.get('turn_ids', [])}")
            
            # Get turns for this session
            turns = await db_ops.get_manual_turns_for_session(session_id)
            print(f"      Found {len(turns)} turn documents")
            
            for i, turn in enumerate(turns):
                print(f"        Turn {i}: {turn.turn_id}")
                print(f"          Index: {turn.index}")
                print(f"          attack_data_id: {turn.attack_data_id}")
                print(f"          defence_data_id: {turn.defence_data_id}")
                print(f"          evaluation_data_id: {turn.evaluation_data_id}")
                
                # Try to retrieve the actual data
                if turn.attack_data_id:
                    attack_data = await db_ops.get_attack_by_id(turn.attack_data_id)
                    if attack_data:
                        print(f"            ✓ Attack data found: {attack_data.prompt[:50]}...")
                    else:
                        print(f"            ✗ Attack data NOT FOUND (ID: {turn.attack_data_id})")
                
                if turn.defence_data_id:
                    defence_data = await db_ops.get_defence_by_id(turn.defence_data_id)
                    if defence_data:
                        print(f"            ✓ Defence data found: {defence_data.response[:50]}...")
                    else:
                        print(f"            ✗ Defence data NOT FOUND (ID: {turn.defence_data_id})")
                
                if turn.evaluation_data_id:
                    eval_data = await db_ops.get_evaluation_by_id(turn.evaluation_data_id)
                    if eval_data:
                        print(f"            ✓ Evaluation data found: score={eval_data.score}")
                    else:
                        print(f"            ✗ Evaluation data NOT FOUND (ID: {turn.evaluation_data_id})")
                
                print()
        
        print()
    
    # Check raw collections
    print("="*70)
    print("Raw Collection Counts:")
    print("="*70)
    attack_count = await db.attacks.count_documents({})
    defence_count = await db.defences.count_documents({})
    eval_count = await db.evaluations.count_documents({})
    
    print(f"  Attacks: {attack_count}")
    print(f"  Defences: {defence_count}")
    print(f"  Evaluations: {eval_count}")
    print()
    
    # Check some sample attack data
    if attack_count > 0:
        print("Sample Attack Documents:")
        sample_attacks = await db.attacks.find().limit(3).to_list(length=None)
        for attack in sample_attacks:
            print(f"  - ID: {attack.get('_id')}")
            print(f"    Run ID: {attack.get('run_id')}")
            print(f"    Turn ID: {attack.get('turn_id')}")
            print(f"    Prompt: {attack.get('prompt', '')[:50]}...")
            print()
    
    await close_db()


if __name__ == "__main__":
    asyncio.run(test_manual_turn_data_retrieval())