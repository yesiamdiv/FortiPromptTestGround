
"""
Default Node Implementations"""

from typing import Dict, Any
import random
from nodes.base import BaseAdversarialNode, StrategyProxyNode
from engine.domain_models import create_defence_response, create_eval_result
from engine.state_schema import update_turn_data, SystemState, RoutingSignals
from engine.debug_utils import debug, tracer, step, warn, err


class DefaultInitNode(StrategyProxyNode):
    """Delegates to strategy.initialize()"""
    def get_strategy_method(self) -> str:
        return "initialize"
    
    async def execute(self, state: SystemState, runtime_config: Dict[str, Any]) -> Dict[str, Any]:
        tracer("DefaultInitNode.execute")
        strategy = self.config.get('strategy')
        if not strategy:
            err("Strategy instance not found in node config")
            raise AttributeError("Strategy instance not found in node's self.config.")
            
        strategy_init_result = strategy.initialize(state)
        
        updated_state = state.copy()
        updated_state.update(strategy_init_result)
        
        if 'strategy_context' not in updated_state or not updated_state['strategy_context']:
            strategy_name = self.config.get("strategy_name", "unknown_strategy")
            updated_state['strategy_context'] = {
                "strategy_params": strategy.config.get("strategy_params", {}),
                "memory": {}, 
                "strategy_name": strategy_name
            }
        else:
            strategy_name = self.config.get("strategy_name", "unknown_strategy")
            updated_state['strategy_context']['strategy_name'] = strategy_name

        step("Strategy initialization complete", strategy_name=updated_state.get('strategy_context', {}).get('strategy_name'))
        return updated_state


class DefaultAttackNode(StrategyProxyNode):
    """Delegates to strategy.execute_generation()"""
    def get_strategy_method(self) -> str:
        return "execute_generation"

    async def execute(self, state: SystemState, runtime_config: Dict[str, Any]) -> Dict[str, Any]:
        tracer("DefaultAttackNode.execute")
        strategy = self.config.get('strategy')
        if not strategy:
            err("Strategy instance not found in node config")
            raise AttributeError("Strategy instance not found in node's self.config.")
            
        return await strategy.execute_generation(state, runtime_config)


class DefaultDefenceNode(BaseAdversarialNode):
    """Returns mock HTTP responses without actual API calls"""
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {"block_rate": 0.3, "latency_ms": 100}
        if config:
            default_config.update(config)
        super().__init__(default_config)
    
    async def execute(self, state: SystemState, runtime_config: Dict[str, Any]) -> Dict[str, Any]:
        tracer("DefaultDefenceNode.execute", block_rate=self.config.get("block_rate", 0.3))
        current_turn = state.get("current_turn", {})
        is_blocked = random.random() < self.config.get("block_rate", 0.3)
        
        if is_blocked:
            response_text = random.choice([
                "I cannot assist with that request as it violates our content policy.",
                "I'm designed to be helpful, harmless, and honest. I can't help with that.",
                "That request appears to be attempting to bypass safety guidelines."
            ])
            status_code = 403
            debug("Request blocked", status_code=status_code)
        else:
            response_text = random.choice([
                "Here's some information that might help...",
                "I'd be happy to assist with that.",
                "Let me provide a helpful response."
            ])
            status_code = 200
            debug("Request allowed", status_code=status_code)
        
        defence = create_defence_response(
            text=response_text,
            status_code=status_code,
            headers={"content-type": "application/json"},
            latency_ms=self.config.get("latency_ms", 100),
            simulated=True
        )
        
        updated_turn = update_turn_data(current_turn, defence=defence, node_name="defence")
        step("Default defence complete", blocked=is_blocked)
        return {"current_turn": updated_turn}


class DefaultEvalNode(BaseAdversarialNode):
    """Returns random evaluation results without LLM calls"""
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {"success_rate": 0.4, "strictness": 0.5}
        if config:
            default_config.update(config)
        super().__init__(default_config)
    
    async def execute(self, state: SystemState, runtime_config: Dict[str, Any]) -> Dict[str, Any]:
        tracer("DefaultEvalNode.execute", success_rate=self.config.get("success_rate", 0.4))
        current_turn = state.get("current_turn", {})
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
        step("Default eval complete", success=is_success, score=round(score, 2))
        return {"current_turn": updated_turn}


class RouterNode(StrategyProxyNode):
    """Delegates to strategy.route()"""
    def get_strategy_method(self) -> str:
        return "route"

    async def execute(self, state: SystemState, runtime_config: Dict[str, Any]) -> Dict[str, Any]:
        tracer("DefaultRouterNode.execute")
        try:
            strategy = self.config.get('strategy')
            if not strategy:
                err("Strategy instance not found in node config")
                raise AttributeError("Strategy instance not found in node's self.config.")
            
            routing_signal = strategy.route(state)
            
            if not isinstance(routing_signal, str):
                err("Strategy route method returned non-string signal", result_type=type(routing_signal).__name__)
                raise TypeError("Strategy's route method must return a string routing signal.")
            
            step("Routing complete", signal=routing_signal)
            return {"routing_signal": routing_signal}
            
        except AttributeError as e:
            err("Strategy error during routing", error=str(e))
            raise AttributeError(f"Strategy error: {e}")
        except TypeError as e:
            err("Error in strategy routing method", error=str(e))
            raise TypeError(f"Error in strategy routing method: {e}")
        except Exception as e:
            err("Unexpected routing error", error=str(e))
            return {"routing_signal": RoutingSignals.END}


def create_default_nodes(config: Dict[str, Any] = None) -> Dict[str, BaseAdversarialNode]:
    """Create a complete set of default nodes"""
    tracer("create_default_nodes")
    node_config = config or {}
    nodes = {
        "init": DefaultInitNode(node_config.get("init", {})),
        "attack": DefaultAttackNode(node_config.get("attack", {})),
        "defence": DefaultDefenceNode(node_config.get("defence", {})),
        "eval": DefaultEvalNode(node_config.get("eval", {})),
        "router": RouterNode(node_config.get("router", {}))
    }
    step("Default nodes created", nodes=list(nodes.keys()))
    return nodes
