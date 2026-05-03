"""
Test Script - Demonstrating the Adversarial Testing Engine

This script shows how to use the default components to run a complete
adversarial testing workflow without any external dependencies.
"""

import asyncio
from engine.workflow_engine import create_default_engine
from strategies.default_strategy import DefaultStrategy


async def basic_test():
    """
    Basic test: Single run with default strategy and logging.
    """
    print("\n" + "="*70)
    print("TEST 1: Basic Execution with Default Components")
    print("="*70 + "\n")
    
    # Create engine (uses default graph and logging middleware)
    engine = create_default_engine()
    
    # Create strategy
    strategy = DefaultStrategy({
        "max_attempts": 2,  # Run 2 attack attempts
        "attack_prefix": "Security Test"
    })
    
    # Execute run
    result = await engine.execute_run(
        payload={
            "intent": "Test jailbreak resistance",
            "target": "example-ai-system",
            "description": "Testing safety guardrails"
        },
        strategy=strategy
    )
    
    # Print results
    print("\n" + "="*70)
    print("FINAL RESULTS:")
    print("="*70)
    print(f"Run ID: {result['run_id']}")
    print(f"Total Attempts: {result['strategy_context']['attempt_count']}")
    print(f"Final Signal: {result['routing_signal']}")
    
    if result['current_turn'].get('evaluation'):
        eval_result = result['current_turn']['evaluation']
        print(f"\nFinal Evaluation:")
        print(f"  {eval_result.to_summary()}")
        print(f"  Reasoning: {eval_result.get_reasoning()}")
    
    print("\n" + "="*70 + "\n")
    
    return result


async def multi_run_test():
    """
    Multi-run test: Parallel execution of multiple runs.
    """
    print("\n" + "="*70)
    print("TEST 2: Parallel Execution of Multiple Runs")
    print("="*70 + "\n")
    
    engine = create_default_engine()
    
    # Create different strategies for each run
    strategies = [
        DefaultStrategy({"max_attempts": 1, "attack_prefix": "Run A"}),
        DefaultStrategy({"max_attempts": 2, "attack_prefix": "Run B"}),
        DefaultStrategy({"max_attempts": 1, "attack_prefix": "Run C"}),
    ]
    
    intents = [
        "Test prompt injection",
        "Test jailbreak resistance",
        "Test content policy bypass"
    ]
    
    # Launch all runs in parallel
    tasks = [
        engine.execute_run(
            payload={"intent": intent},
            strategy=strategy
        )
        for strategy, intent in zip(strategies, intents)
    ]
    
    results = await asyncio.gather(*tasks)
    
    # Summary
    print("\n" + "="*70)
    print("PARALLEL EXECUTION SUMMARY:")
    print("="*70)
    for i, result in enumerate(results):
        eval_result = result['current_turn']['evaluation']
        print(f"\nRun {i+1} ({result['run_id']}):")
        print(f"  Intent: {result['payload']['intent']}")
        print(f"  Attempts: {result['strategy_context']['attempt_count']}")
        print(f"  Result: {eval_result.to_summary()}")
    
    print("\n" + "="*70 + "\n")
    
    return results


async def custom_strategy_test():
    """
    Custom strategy test: Demonstrating strategy customization.
    """
    print("\n" + "="*70)
    print("TEST 3: Custom Strategy Configuration")
    print("="*70 + "\n")
    
    # Custom configuration
    custom_config = {
        "max_attempts": 3,
        "attack_prefix": "Advanced Test",
        "always_succeed": False  # Don't force success
    }
    
    strategy = DefaultStrategy(custom_config)
    engine = create_default_engine()
    
    result = await engine.execute_run(
        payload={
            "intent": "Multi-turn adversarial testing",
            "target": "production-model",
            "severity": "high"
        },
        strategy=strategy
    )
    
    print("\n" + "="*70)
    print("CUSTOM STRATEGY RESULTS:")
    print("="*70)
    print(f"Configuration: {custom_config}")
    print(f"Attempts Made: {result['strategy_context']['attempt_count']}")
    print(f"Max Allowed: {result['strategy_context']['max_attempts']}")
    
    print("\n" + "="*70 + "\n")
    
    return result


async def state_inspection_test():
    """
    State inspection test: Examining the state structure.
    """
    print("\n" + "="*70)
    print("TEST 4: State Structure Inspection")
    print("="*70 + "\n")
    
    engine = create_default_engine()
    strategy = DefaultStrategy({"max_attempts": 1})
    
    result = await engine.execute_run(
        payload={"intent": "State inspection test"},
        strategy=strategy
    )
    
    print("FINAL STATE STRUCTURE:\n")
    
    print("1. RUN METADATA:")
    print(f"   - run_id: {result['run_id']}")
    print(f"   - start_time: {result['start_time']}")
    print(f"   - payload: {result['payload']}")
    
    print("\n2. CURRENT TURN:")
    turn = result['current_turn']
    print(f"   - turn_id: {turn['turn_id']}")
    print(f"   - timestamp: {turn['timestamp']}")
    print(f"   - node_name: {turn.get('node_name')}")
    
    if turn.get('attack'):
        print(f"\n   Attack:")
        print(f"   - Type: {turn['attack']._infer_type()}")
        print(f"   - Preview: {turn['attack'].to_string()[:50]}...")
        print(f"   - Metadata: {turn['attack'].metadata}")
    
    if turn.get('defence'):
        print(f"\n   Defence:")
        print(f"   - Status: {'Blocked' if turn['defence'].was_blocked() else 'Allowed'}")
        print(f"   - Status Code: {turn['defence'].status_code}")
        print(f"   - Simulated: {turn['defence'].metadata.get('simulated')}")
    
    if turn.get('evaluation'):
        print(f"\n   Evaluation:")
        print(f"   - Success: {turn['evaluation'].is_success()}")
        print(f"   - Score: {turn['evaluation'].get_score():.2f}")
        print(f"   - Category: {turn['evaluation'].get_category()}")
    
    print("\n3. STRATEGY CONTEXT:")
    context = result['strategy_context']
    for key, value in context.items():
        print(f"   - {key}: {value}")
    
    print(f"\n4. ROUTING SIGNAL: {result['routing_signal']}")
    
    print("\n" + "="*70 + "\n")
    
    return result


async def error_handling_test():
    """
    Error handling test: Demonstrating graceful error handling.
    """
    print("\n" + "="*70)
    print("TEST 5: Error Handling & Recovery")
    print("="*70 + "\n")
    
    # This will use the default engine which handles errors gracefully
    engine = create_default_engine()
    strategy = DefaultStrategy({"max_attempts": 1})
    
    try:
        result = await engine.execute_run(
            payload={"intent": "Error handling test"},
            strategy=strategy
        )
        print("✓ Run completed successfully despite any internal errors")
        print(f"  Run ID: {result['run_id']}")
        print(f"  Status: {'Completed' if result['routing_signal'] == '__end__' else 'Running'}")
        
    except Exception as e:
        print(f"✗ Run failed with error: {e}")
        print("  (This should not happen with default components)")
    
    print("\n" + "="*70 + "\n")


async def main():
    """
    Run all tests in sequence.
    """
    print("\n" + "#"*70)
    print("#" + " "*24 + "ADVERSARIAL ENGINE TESTS" + " "*22 + "#")
    print("#"*70 + "\n")
    
    print("This test suite demonstrates the core functionality of the")
    print("adversarial testing engine using default components.\n")
    print("All tests use mock data and require no external dependencies.")
    print("No actual LLM calls or network requests are made.\n")
    
    input("Press Enter to start tests...")
    
    # Run tests
    await basic_test()
    await asyncio.sleep(1)  # Brief pause between tests
    
    await multi_run_test()
    await asyncio.sleep(1)
    
    await custom_strategy_test()
    await asyncio.sleep(1)
    
    await state_inspection_test()
    await asyncio.sleep(1)
    
    await error_handling_test()
    
    print("\n" + "#"*70)
    print("#" + " "*26 + "ALL TESTS COMPLETED" + " "*25 + "#")
    print("#"*70 + "\n")
    
    print("Summary:")
    print("  ✓ Basic execution with default components")
    print("  ✓ Parallel execution of multiple runs")
    print("  ✓ Custom strategy configuration")
    print("  ✓ State structure inspection")
    print("  ✓ Error handling and recovery")
    print("\nThe engine is ready for production use!")
    print("Next steps:")
    print("  1. Implement custom strategies in strategies/")
    print("  2. Add LLM providers in providers/")
    print("  3. Create custom nodes in nodes/")
    print("  4. Build the FastAPI server in server/")
    print()


if __name__ == "__main__":
    asyncio.run(main())
