#!/usr/bin/env python3
"""
Test script to verify all fixes for the adversarial testing engine
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_node_execution_signatures():
    """Test that all nodes have correct execute signatures"""
    print("\n=== Testing Node Execute Signatures ===")
    
    from nodes.default_nodes import DefaultAttackNode, DefaultDefenceNode, DefaultEvalNode, RouterNode
    from nodes.multilayer_defense_node import MultilayerDefenseNode
    from nodes.ensemble_defence_node import EnsembleDefenceNode
    from nodes.server_eval_node import ServerEvalNode
    from nodes.llm_eval_node import LLMEvalNode
    from engine.state_schema import create_initial_state
    
    nodes_to_test = [
        ("DefaultAttackNode", DefaultAttackNode, {}),
        ("DefaultDefenceNode", DefaultDefenceNode, {}),
        ("DefaultEvalNode", DefaultEvalNode, {}),
        ("MultilayerDefenseNode", MultilayerDefenseNode, {}),
        ("EnsembleDefenceNode", EnsembleDefenceNode, {}),
        ("ServerEvalNode", ServerEvalNode, {}),
        ("LLMEvalNode", LLMEvalNode, {})
    ]
    
    state = create_initial_state("test_run", {}, {})
    
    for name, node_class, config in nodes_to_test:
        try:
            node = node_class(config)
            # Test with no runtime_config (LangGraph pattern)
            result = await node.execute(state)
            print(f"✓ {name}: execute() accepts state-only argument")
        except Exception as e:
            print(f"✗ {name}: {e}")
            return False
    
    return True


async def test_node_schemas():
    """Test that all nodes have get_node_schema methods"""
    print("\n=== Testing Node Schemas ===")
    
    from nodes.default_nodes import DefaultAttackNode, DefaultDefenceNode, DefaultEvalNode, RouterNode
    from nodes.multilayer_defense_node import MultilayerDefenseNode
    from nodes.ensemble_defence_node import EnsembleDefenceNode
    from nodes.server_eval_node import ServerEvalNode
    from nodes.llm_eval_node import LLMEvalNode
    
    nodes_to_test = [
        ("DefaultAttackNode", DefaultAttackNode),
        ("DefaultDefenceNode", DefaultDefenceNode),
        ("DefaultEvalNode", DefaultEvalNode),
        ("RouterNode", RouterNode),
        ("MultilayerDefenseNode", MultilayerDefenseNode),
        ("EnsembleDefenceNode", EnsembleDefenceNode),
        ("ServerEvalNode", ServerEvalNode),
        ("LLMEvalNode", LLMEvalNode)
    ]
    
    for name, node_class in nodes_to_test:
        try:
            schema = node_class.get_node_schema()
            if not isinstance(schema, dict):
                print(f"✗ {name}: get_node_schema() must return dict, got {type(schema)}")
                return False
            if "type" not in schema:
                print(f"✗ {name}: schema missing 'type' field")
                return False
            print(f"✓ {name}: has valid get_node_schema()")
        except Exception as e:
            print(f"✗ {name}: {e}")
            return False
    
    return True


async def test_strategy_schemas():
    """Test that all strategies have get_strategy_schema methods"""
    print("\n=== Testing Strategy Schemas ===")
    
    from strategies.default_strategy import DefaultStrategy
    from strategies.manual_strategy import ManualStrategy
    
    strategies_to_test = [
        ("DefaultStrategy", DefaultStrategy),
        ("ManualStrategy", ManualStrategy)
    ]
    
    for name, strategy_class in strategies_to_test:
        try:
            schema = strategy_class.get_strategy_schema()
            if not isinstance(schema, dict):
                print(f"✗ {name}: get_strategy_schema() must return dict, got {type(schema)}")
                return False
            print(f"✓ {name}: has valid get_strategy_schema()")
        except Exception as e:
            print(f"✗ {name}: {e}")
            return False
    
    return True


async def test_registry():
    """Test registry functions"""
    print("\n=== Testing Registry ===")
    
    from engine.registry import get_node_registry, get_strategy_registry, register_all_components
    
    try:
        # Register all components
        register_all_components()
        print("✓ Components registered successfully")
        
        # Test node registry
        node_registry = get_node_registry()
        node_names = node_registry.list_nodes()
        print(f"✓ Found {len(node_names)} registered nodes: {', '.join(node_names[:5])}...")
        
        # Test strategy registry
        strategy_registry = get_strategy_registry()
        strategy_names = strategy_registry.list_strategies()
        print(f"✓ Found {len(strategy_names)} registered strategies: {', '.join(strategy_names)}")
        
        return True
    except Exception as e:
        print(f"✗ Registry error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_graph_builder():
    """Test that graph builder works with wrapper functions"""
    print("\n=== Testing Graph Builder ===")
    
    from server.config.models import GraphConfig, AttackNodeConfig, DefenseNodeConfig, EvaluationNodeConfig, StrategyConfig
    from engine.graph_builder import ConfigurableGraphBuilder
    
    try:
        # Create a minimal config
        config = GraphConfig(
            attack_node_config=AttackNodeConfig(
                node_type="default_attack",
                node_params={}
            ),
            defense_node_config=DefenseNodeConfig(
                node_type="default_defense",
                node_params={"block_rate": 0.5}
            ),
            evaluation_node_config=EvaluationNodeConfig(
                node_type="default_eval",
                node_params={"success_rate": 0.4}
            ),
            strategy_config=StrategyConfig(
                strategy_name="default",
                strategy_params={"max_turns": 5}
            ),
            graph_type="automatic"
        )
        
        builder = ConfigurableGraphBuilder(config)
        graph = builder.compile()
        print("✓ Graph built successfully")
        print(f"✓ Graph type: {type(graph)}")
        
        return True
    except Exception as e:
        print(f"✗ Graph builder error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_config_models():
    """Test that config models support node_params"""
    print("\n=== Testing Config Models ===")
    
    from server.config.models import AttackNodeConfig, DefenseNodeConfig, EvaluationNodeConfig
    
    try:
        # Test AttackNodeConfig
        attack_config = AttackNodeConfig(
            node_type="default_attack",
            node_params={"test_param": "value"}
        )
        assert attack_config.node_params == {"test_param": "value"}
        print("✓ AttackNodeConfig supports node_params")
        
        # Test DefenseNodeConfig
        defense_config = DefenseNodeConfig(
            node_type="default_defense",
            node_params={"block_rate": 0.5}
        )
        assert defense_config.node_params == {"block_rate": 0.5}
        print("✓ DefenseNodeConfig supports node_params")
        
        # Test EvaluationNodeConfig
        eval_config = EvaluationNodeConfig(
            node_type="default_eval",
            node_params={"success_rate": 0.4}
        )
        assert eval_config.node_params == {"success_rate": 0.4}
        print("✓ EvaluationNodeConfig supports node_params")
        
        return True
    except Exception as e:
        print(f"✗ Config models error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("  ADVERSARIAL TESTING ENGINE - FIX VERIFICATION")
    print("="*60)
    
    tests = [
        ("Config Models", test_config_models),
        ("Node Execute Signatures", test_node_execution_signatures),
        ("Node Schemas", test_node_schemas),
        ("Strategy Schemas", test_strategy_schemas),
        ("Registry", test_registry),
        ("Graph Builder", test_graph_builder)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ {test_name} crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, False))
    
    print("\n" + "="*60)
    print("  TEST SUMMARY")
    print("="*60)
    
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(result for _, result in results)
    
    print("\n" + "="*60)
    if all_passed:
        print("  ✓ ALL TESTS PASSED")
    else:
        print("  ✗ SOME TESTS FAILED")
    print("="*60 + "\n")
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)