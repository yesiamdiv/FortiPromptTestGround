"""
Updated Engine Tests - Async Strategies

Tests for the workflow engine with async strategy interface.
"""

import asyncio
from engine.workflow_engine import create_default_engine
from strategies.default_strategy import DefaultStrategy
from engine.domain_models import create_simple_attack


async def test_basic_execution():
    """Test basic engine execution with async strategy"""
    print("\n" + "="*70)
    print("TEST: Basic Engine Execution (Async)")
    print("="*70 + "\n")
    
    # Create engine
    engine = create_default_engine()
    
    # Create strategy
    strategy = DefaultStrategy({"max_attempts": 2})
    
    # Execute
    result = await engine.execute_run(
        initial_payload={"intent": "Test basic execution"},
        strategy=strategy
    )
    
    # Verify
    assert result is not None
    assert "run_id" in result
    assert "strategy_context" in result
    assert result["strategy_context"]["attempt_count"] == 2
    
    print("✅ Basic execution test passed")
    return result


async def test_with_custom_config():
    """Test engine with custom configuration"""
    print("\n" + "="*70)
    print("TEST: Custom Configuration")
    print("="*70 + "\n")
    
    engine = create_default_engine()
    
    strategy = DefaultStrategy({
        "max_attempts": 3,
        "attack_prefix": "CUSTOM_TEST"
    })
    
    result = await engine.execute_run(
        initial_payload={
            "intent": "Test with custom config",
            "target": "test-system"
        },
        strategy=strategy
    )
    
    assert result["strategy_context"]["attempt_count"] == 3
    
    print("✅ Custom configuration test passed")
    return result


async def test_early_stopping():
    """Test that engine stops when strategy signals END"""
    print("\n" + "="*70)
    print("TEST: Early Stopping")
    print("="*70 + "\n")
    
    engine = create_default_engine()
    
    # Strategy with low max attempts
    strategy = DefaultStrategy({"max_attempts": 1})
    
    result = await engine.execute_run(
        initial_payload={"intent": "Test early stopping"},
        strategy=strategy
    )
    
    # Should stop after 1 attempt
    assert result["strategy_context"]["attempt_count"] == 1
    assert result["routing_signal"] == "__end__"
    
    print("✅ Early stopping test passed")
    return result


async def test_evaluation_flow():
    """Test that evaluation data flows correctly"""
    print("\n" + "="*70)
    print("TEST: Evaluation Data Flow")
    print("="*70 + "\n")
    
    engine = create_default_engine()
    strategy = DefaultStrategy({"max_attempts": 1})
    
    result = await engine.execute_run(
        initial_payload={"intent": "Test evaluation"},
        strategy=strategy
    )
    
    # Check evaluation exists
    current_turn = result.get("current_turn", {})
    assert "evaluation" in current_turn
    
    evaluation = current_turn["evaluation"]
    assert evaluation is not None
    assert hasattr(evaluation, "get_score")
    assert hasattr(evaluation, "is_success")
    assert hasattr(evaluation, "get_category")
    
    print(f"Evaluation Score: {evaluation.get_score():.2f}")
    print(f"Success: {evaluation.is_success()}")
    print(f"Category: {evaluation.get_category()}")
    
    print("✅ Evaluation flow test passed")
    return result


async def test_multiple_runs():
    """Test multiple sequential runs"""
    print("\n" + "="*70)
    print("TEST: Multiple Runs")
    print("="*70 + "\n")
    
    engine = create_default_engine()
    
    results = []
    for i in range(3):
        strategy = DefaultStrategy({"max_attempts": 1})
        result = await engine.execute_run(
            initial_payload={"intent": f"Test run {i+1}"},
            strategy=strategy
        )
        results.append(result)
        print(f"  Run {i+1} completed: {result['run_id']}")
    
    # Verify all runs completed
    assert len(results) == 3
    assert all(r["routing_signal"] == "__end__" for r in results)
    
    print("✅ Multiple runs test passed")
    return results


async def test_strategy_context_persistence():
    """Test that strategy context persists across turns"""
    print("\n" + "="*70)
    print("TEST: Strategy Context Persistence")
    print("="*70 + "\n")
    
    engine = create_default_engine()
    strategy = DefaultStrategy({"max_attempts": 3})
    
    result = await engine.execute_run(
        initial_payload={"intent": "Test context"},
        strategy=strategy
    )
    
    context = result["strategy_context"]
    
    # Verify context accumulated correctly
    assert "attempt_count" in context
    assert context["attempt_count"] == 3
    assert "intent" in context
    
    print(f"Final context: {context}")
    print("✅ Context persistence test passed")
    return result


async def run_all_tests():
    """Run all test cases"""
    print("\n🧪 Running All Engine Tests (Async)")
    print("="*70)
    
    try:
        await test_basic_execution()
        await test_with_custom_config()
        await test_early_stopping()
        await test_evaluation_flow()
        await test_multiple_runs()
        await test_strategy_context_persistence()
        
        print("\n" + "="*70)
        print("✅ ALL TESTS PASSED")
        print("="*70 + "\n")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        raise


if __name__ == "__main__":
    asyncio.run(run_all_tests())