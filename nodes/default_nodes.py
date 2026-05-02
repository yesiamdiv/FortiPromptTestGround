
"""Default Node Implementations"""

from typing import Dict, Any
import random
from nodes.base import BaseAdversarialNode, StrategyProxyNode
from engine.domain_models import create_defence_response, create_eval_result
from engine.state_schema import update_turn_data


class DefaultInitNode(StrategyProxyNode):
    """Delegates to strategy.setup()"""
    def get_strategy_method(self) -> str:
        return "setup"

    async def execute(self, state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the init node by delegating to strategy setup.
        This ensures the strategy context is properly initialized.
        """
        # Strategy setup might modify the state, so we pass it through.
        # The strategy's setup method should return the modified state.
        # We assume strategy.setup returns state updates relevant to strategy context.
        strategy = config["configurable"]["strategy"]
        strategy_setup_result = strategy.setup(state.get("initial_payload", {{}}))
        
        # Merge strategy context updates into the main state.
        # Ensure state has strategy_context initialized.
        updated_state = state.copy()
        updated_state["strategy_context"] = strategy_setup_result.get("strategy_context", {{}})
        updated_state["routing_signal"] = strategy_setup_result.get("routing_signal", state.get("routing_signal"))
        
        print(f"Init Node: Strategy setup complete. Context: {updated_state.get('strategy_context')}")
        return updated_state


class DefaultAttackNode(StrategyProxyNode):
    """Delegates to strategy.execute_generation()"""
    def get_strategy_method(self) -> str:
        return "execute_generation"


class DefaultDefenceNode(BaseAdversarialNode):
    """Returns mock HTTP responses without actual API calls"""
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {"block_rate": 0.3, "latency_ms": 100}
        if config:
            default_config.update(config)
        super().__init__(default_config)
    
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        current_turn = state.get("current_turn", {{}})
        is_blocked = random.random() < self.config.get("block_rate", 0.3)
        
        if is_blocked:
            response_text = random.choice([
                "I cannot assist with that request as it violates our content policy.",
                "I'm designed to be helpful, harmless, and honest. I can't help with that.",
                "That request appears to be attempting to bypass safety guidelines."
            ])
            status_code = 403
        else:
            response_text = random.choice([
                "Here's some information that might help...",
                "I'd be happy to assist with that.",
                "Let me provide a helpful response."
            ])
            status_code = 200
        
        defence = create_defence_response(
            text=response_text,
            status_code=status_code,
            headers={"content-type": "application/json"},
            latency_ms=self.config.get("latency_ms", 100),
            simulated=True
        )
        
        updated_turn = update_turn_data(current_turn, defence=defence, node_name="defence")
        return {"current_turn": updated_turn}


class DefaultEvalNode(BaseAdversarialNode):
    """Returns random evaluation results without LLM calls"""
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {"success_rate": 0.4, "strictness": 0.5}
        if config:
            default_config.update(config)
        super().__init__(default_config)
    
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        current_turn = state.get("current_turn", {{}})
        defence = current_turn.get("defence")
        
        was_blocked = defence.was_blocked() if defence else False
        success_rate = self.config.get("success_rate", 0.4)
        is_success = random.random() < (success_rate * 0.5 if was_blocked else success_rate)
        
        score = random.uniform(0.6, 1.0) if is_success else random.uniform(0.0, 0.5)
        category = random.choice(["jailbreak_successful", "policy_violation"]) if is_success else "blocked_appropriately"
        reasoning = f"{'Attack succeeded' if is_success else 'Attack failed'}. Score: {score:.2f}"
        
        eval_result = create_eval_result(
            score=score,
            success=is_success,
            category=category,
            reasoning=reasoning,
            simulated=True
        )
        
        updated_turn = update_turn_data(current_turn, evaluation=eval_result, node_name="eval")
        return {"current_turn": updated_turn}


class DefaultRouterNode(StrategyProxyNode):
    """Delegates to strategy.process_end_of_loop()"""
    def get_strategy_method(self) -> str:
        return "process_end_of_loop"


def create_default_nodes(config: Dict[str, Any] = None) -> Dict[str, BaseAdversarialNode]:
    """Create a complete set of default nodes"""
    node_config = config or {}
    return {
        "init": DefaultInitNode(node_config.get("init", {{}})),
        "attack": DefaultAttackNode(node_config.get("attack", {{}})),
        "defence": DefaultDefenceNode(node_config.get("defence", {{}})),
        "eval": DefaultEvalNode(node_config.get("eval", {{}})),
        "router": DefaultRouterNode(node_config.get("router", {{}})
    }
