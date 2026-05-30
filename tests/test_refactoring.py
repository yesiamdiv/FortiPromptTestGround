#!/usr/bin/env python3
"""
Test Script: Validate Architectural Refactoring

This script tests the separation of concerns in the run execution lifecycle.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from server.database.connection import init_db, close_db, get_db
from server.database.operations import get_db_ops
from server.run_manager import get_run_manager, RunStatus
from core.config import GraphConfig
from datetime import datetime


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.message = ""
    
    def success(self, message: str = ""):
        self.passed = True
        self.message = message
    
    def failure(self, message: str):
        self.passed = False
        self.message = message
    
    def __str__(self):
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status}: {self.name}\n  {self.message}"


async def test_zombie_cleanup_automatic():
    """Test that automatic zombie runs are marked as FAILED"""
    result = TestResult("Zombie Cleanup - Automatic Run")
    
    try:
        db = get_db()
        if not db:
            result.failure("Database not connected")
            return result
        
        db_ops = get_db_ops(db)
        
        # Create a test automatic run stuck in RUNNING
        test_run_id = f"test_zombie_auto_{datetime.utcnow().timestamp()}"
        graph_config = GraphConfig(
            graph_type="automatic",
            attack_node_config={"node_type": "default_attack"},
            defense_node_config={"node_type": "default_defense"},
            evaluation_node_config={"node_type": "default_eval"},
            strategy_config={
                "strategy_name": "default",
                "strategy_params": {}
            }
        )
        
        await db_ops.create_run({
            "run_id": test_run_id,
            "name": "Test Zombie Auto",
            "status": "running",  # Simulate zombie state
            "description": "Test automatic zombie cleanup",
            "graph_config": graph_config.dict(),
            "created_at": datetime.utcnow().isoformat()
        })
        
        # Run cleanup
        run_manager = get_run_manager()
        cleanup_result = await run_manager.cleanup_zombie_runs()
        
        # Verify the run was marked as FAILED
        updated_run = await db_ops.get_run(test_run_id)
        
        if updated_run.status == "failed":
            if "Server restarted" in updated_run.error:
                result.success(f"Automatic zombie run correctly marked as FAILED with error message")
            else:
                result.failure(f"Run marked as FAILED but error message incorrect: {updated_run.error}")
        else:
            result.failure(f"Expected status='failed', got status='{updated_run.status}'")
        
        # Cleanup
        await db.runs.delete_one({"run_id": test_run_id})
        
    except Exception as e:
        result.failure(f"Exception: {str(e)}")
    
    return result


async def test_zombie_cleanup_manual():
    """Test that manual zombie runs are reverted to IDLE"""
    result = TestResult("Zombie Cleanup - Manual Run")
    
    try:
        db = get_db()
        if not db:
            result.failure("Database not connected")
            return result
        
        db_ops = get_db_ops(db)
        
        # Create a test manual run stuck in RUNNING
        test_run_id = f"test_zombie_manual_{datetime.utcnow().timestamp()}"
        graph_config = GraphConfig(
            graph_type="manual",
            attack_node_config={"node_type": "default_attack"},
            defense_node_config={"node_type": "default_defense"},
            evaluation_node_config={"node_type": "default_eval"},
            strategy_config={
                "strategy_name": "manual",
                "strategy_params": {}
            }
        )
        
        await db_ops.create_run({
            "run_id": test_run_id,
            "name": "Test Zombie Manual",
            "status": "running",  # Simulate zombie state
            "description": "Test manual zombie cleanup",
            "graph_config": graph_config.dict(),
            "created_at": datetime.utcnow().isoformat()
        })
        
        # Run cleanup
        run_manager = get_run_manager()
        cleanup_result = await run_manager.cleanup_zombie_runs()
        
        # Verify the run was reverted to IDLE
        updated_run = await db_ops.get_run(test_run_id)
        
        if updated_run.status == "idle":
            result.success(f"Manual zombie run correctly reverted to IDLE")
        else:
            result.failure(f"Expected status='idle', got status='{updated_run.status}'")
        
        # Cleanup
        await db.runs.delete_one({"run_id": test_run_id})
        
    except Exception as e:
        result.failure(f"Exception: {str(e)}")
    
    return result


async def test_run_executor_no_status_updates():
    """Test that RunExecutor._update_db_status only handles infrastructure states"""
    result = TestResult("RunExecutor Status Updates")
    
    try:
        # This is a code inspection test - verify that _update_db_status
        # only handles RUNNING, STOPPED, FAILED
        from server.run_manager import RunExecutor
        import inspect
        
        source = inspect.getsource(RunExecutor._update_db_status)
        
        # Check that COMPLETED is NOT in the method
        if "RunStatus.COMPLETED" in source or "status.COMPLETED" in source:
            result.failure("RunExecutor._update_db_status still handles COMPLETED status")
            return result
        
        # Check that it only handles infrastructure states
        if "RunStatus.FAILED" in source and "RunStatus.STOPPED" in source:
            result.success("RunExecutor._update_db_status correctly handles only infrastructure states (RUNNING, STOPPED, FAILED)")
        else:
            result.failure("RunExecutor._update_db_status doesn't handle expected infrastructure states")
        
    except Exception as e:
        result.failure(f"Exception: {str(e)}")
    
    return result


async def test_middleware_responsibility():
    """Test that middlewares have after_run methods that update status"""
    result = TestResult("Middleware Responsibility")
    
    try:
        from middlewares.automatic_database_middleware import AutomaticDatabaseMiddleware
        from middlewares.manual_database_middleware import ManualDatabaseMiddleware
        import inspect
        
        # Check AutomaticDatabaseMiddleware.after_run
        auto_source = inspect.getsource(AutomaticDatabaseMiddleware.after_run)
        if '"completed"' in auto_source or "'completed'" in auto_source:
            auto_ok = True
        else:
            result.failure("AutomaticDatabaseMiddleware.after_run doesn't set status to 'completed'")
            return result
        
        # Check ManualDatabaseMiddleware.after_run
        manual_source = inspect.getsource(ManualDatabaseMiddleware.after_run)
        if '"idle"' in manual_source or "'idle'" in manual_source:
            manual_ok = True
        else:
            result.failure("ManualDatabaseMiddleware.after_run doesn't set status to 'idle'")
            return result
        
        if auto_ok and manual_ok:
            result.success("Both middlewares correctly handle Happy Path status updates in after_run")
        
    except Exception as e:
        result.failure(f"Exception: {str(e)}")
    
    return result


async def main():
    """Run all tests"""
    print("="*70)
    print("Architectural Refactoring Validation Tests")
    print("="*70)
    print()
    
    # Connect to database
    try:
        import os
        mongo_url = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        db_name = os.getenv("MONGODB_DB_NAME", "adversarial_testing_test")
        await init_db(mongo_url, db_name)
        print(f"✓ Connected to test database: {db_name}")
        print()
    except Exception as e:
        print(f"✗ Failed to connect to database: {e}")
        print("  Some tests will be skipped.")
        print()
    
    # Run tests
    tests = [
        test_run_executor_no_status_updates(),
        test_middleware_responsibility(),
        test_zombie_cleanup_automatic(),
        test_zombie_cleanup_manual(),
    ]
    
    results = await asyncio.gather(*tests, return_exceptions=True)
    
    # Print results
    passed = 0
    failed = 0
    
    for r in results:
        if isinstance(r, Exception):
            print(f"✗ FAIL: Test crashed with exception: {r}")
            failed += 1
        else:
            print(r)
            if r.passed:
                passed += 1
            else:
                failed += 1
        print()
    
    # Summary
    print("="*70)
    print(f"Test Summary: {passed} passed, {failed} failed out of {passed + failed} total")
    print("="*70)
    
    # Cleanup
    await close_db()
    
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)