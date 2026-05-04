# test_iterative_improvement_strategy.py

import pytest
from unittest.mock import MagicMock, patch

from strategies.iterative_improvement_strategy import IterativeImprovementStrategy
from engine.state_schema import SystemState, RoutingSignals


@pytest.fixture
def iterative_strategy_config():
    return {
        "max_iterations": 3,
        "target_score": 0.7,
        "temperature": 0.8,
        "max_tokens": 400,
        "llm_provider_name": "ollama"
    }

@pytest.pytest.fixture
def iterative_strategy(iterative_strategy_config):
    # Mock the provider registry and its get method
    mock_provider_registry = MagicMock()
    mock_provider_instance = MagicMock()
    mock_provider_instance.get_model_name.return_value = "llama3"
    mock_provider_instance.generate.return_value = "Generated prompt"
    mock_provider_registry.get.return_value = mock_provider_instance
    
    # Mock the get_provider_registry function to return our mock
    with patch("strategies.iterative_improvement_strategy.get_provider_registry", return_value=mock_provider_registry):
        strategy = IterativeImprovementStrategy(config=iterative_strategy_config)
        strategy.provider = mock_provider_instance # Directly assign mock for simplicity in tests
        return strategy

def test_iterative_improvement_strategy_init(iterative_strategy):
    assert iterative_strategy.config["max_iterations"] == 3
    assert iterative_strategy.config["target_score"] == 0.7
    assert iterative_strategy.provider is not None
    assert iterative_strategy.provider.get_model_name() == "llama3"

def test_iterative_improvement_strategy_initialize(iterative_strategy):
    initial_state = {
        "run_id": "test_run_456",
        "payload": {"intent": "find vulnerability", "initial_attack_prompt": "Start here"},
        "config": {
            "strategy_config": {"strategy_name": "iterative_improvement"}
        }
    }
    updated_state = iterative_strategy.initialize(initial_state)
    
    assert updated_state["strategy_context"]["intent"] == "find vulnerability"
    assert updated_state["strategy_context"]["iteration_count"] == 0
    assert updated_state["strategy_context"]["max_iterations"] == 3
    assert updated_state["strategy_context"]["target_score"] == 0.7
    assert updated_state["strategy_context"]["initial_attack_prompt"] == "Start here"
    assert updated_state["routing_signal"] == RoutingSignals.CONTINUE

@pytest.mark.asyncio
async def test_iterative_improvement_strategy_execute_generation_initial(iterative_strategy):
    initial_state = {
        "strategy_context": {
            "iteration_count": 0,
            "max_iterations": 3,
            "max_tokens": 400,
            "target_score": 0.7,
            "attack_history": [],
            "session_id": "test_session_1",
            "intent": "test intent"
        },
        "current_turn": { "turn_id": "turn_1" }
    }
    
    # Mock the internal generation method to return a specific value
    with patch.object(iterative_strategy, '_generate_initial_attack', return_value="Initial Attack Prompt") as mock_gen:
        result = await iterative_strategy.execute_generation(initial_state, config={})
        
        mock_gen.assert_called_once()
        assert "current_turn" in result
        assert result["current_turn"]["attack"].prompt == "Initial Attack Prompt"
        assert result["strategy_context"]["iteration_count"] == 1
        assert len(result["strategy_context"]["attack_history"]) == 1
        assert result["strategy_context"]["attack_history"][0]["attack_text"] == "Initial Attack Prompt"

@pytest.mark.asyncio
async def test_iterative_improvement_strategy_execute_generation_improved(iterative_strategy):
    initial_state = {
        "strategy_context": {
            "iteration_count": 1,
            "max_iterations": 3,
            "max_tokens": 400,
            "target_score": 0.7,
            "attack_history": [{"iteration": 1, "attack_text": "Previous Attack", "turn_id": "turn_1"}],
            "session_id": "test_session_1",
            "intent": "test intent"
        },
        "current_turn": {"turn_id": "turn_2", "evaluation": MagicMock(score=0.5, success=False, reasoning="Needs improvement"), "defence": MagicMock(text="Defense response")}
    }
    
    # Mock the internal generation method for improvement
    with patch.object(iterative_strategy, '_generate_improved_attack', return_value="Improved Attack Prompt") as mock_improve:
        result = await iterative_strategy.execute_generation(initial_state, config={})
        
        mock_improve.assert_called_once()
        assert "current_turn" in result
        assert result["current_turn"]["attack"].prompt == "Improved Attack Prompt"
        assert result["strategy_context"]["iteration_count"] == 2
        assert len(result["strategy_context"]["attack_history"]) == 2
        assert result["strategy_context"]["attack_history"][1]["attack_text"] == "Improved Attack Prompt"

def test_iterative_improvement_strategy_route_manual_end():
    strategy = IterativeImprovementStrategy(config={"max_iterations": 3, "target_score": 0.8})
    
    # Mock evaluation data
    mock_evaluation = MagicMock()
    mock_evaluation.get_score.return_value = 0.5
    mock_evaluation.is_success.return_value = False
    mock_evaluation.get_reasoning.return_value = "Needs improvement"
    
    state = {
        "strategy_context": {
            "iteration_count": 0,
            "max_iterations": 3,
            "target_score": 0.8,
            "best_score": 0.0,
            "attack_history": [{"attack_text": "Some attack"}]
        },
        "current_turn": {"evaluation": mock_evaluation}
    }
    
    route_result = strategy.route(state)
    assert route_result["routing_signal"] == RoutingSignals.ATTACK
    assert route_result["strategy_context"]["best_score"] == 0.5
    assert route_result["strategy_context"]["iteration_count"] == 1
    assert route_result["strategy_context"]["target_achieved"] == False

def test_iterative_improvement_strategy_route_target_achieved():
    strategy = IterativeImprovementStrategy(config={"max_iterations": 3, "target_score": 0.8})
    
    mock_evaluation = MagicMock()
    mock_evaluation.get_score.return_value = 0.9
    mock_evaluation.is_success.return_value = True # Target score met AND success

    state = {
        "strategy_context": {
            "iteration_count": 1,
            "max_iterations": 3,
            "target_score": 0.8,
            "best_score": 0.5,
            "attack_history": [{"attack_text": "Previous Attack"}]
        },
        "current_turn": {"evaluation": mock_evaluation}
    }
    
    route_result = strategy.route(state)
    assert route_result["routing_signal"] == RoutingSignals.END
    assert route_result["strategy_context"]["target_achieved"] == True

def test_iterative_improvement_strategy_route_max_iterations_reached():
    strategy = IterativeImprovementStrategy(config={"max_iterations": 1, "target_score": 0.8})
    
    mock_evaluation = MagicMock()
    mock_evaluation.get_score.return_value = 0.5
    mock_evaluation.is_success.return_value = False

    state = {
        "strategy_context": {
            "iteration_count": 1, # Max iterations reached
            "max_iterations": 1,
            "target_score": 0.8,
            "best_score": 0.5,
            "attack_history": [{"attack_text": "Previous Attack"}]
        },
        "current_turn": {"evaluation": mock_evaluation}
    }
    
    route_result = strategy.route(state)
    assert route_result["routing_signal"] == RoutingSignals.END
    assert route_result["strategy_context"]["target_achieved"] == False

def test_iterative_improvement_strategy_get_dependency_schema():
    schema = IterativeImprovementStrategy.get_dependency_schema()
    assert schema["type"] == "object"
    assert "llm_provider_name" in schema["properties"]
    assert schema["properties"]["llm_provider_name"]["enum"] == ["ollama", "gemini", "openai"]
    assert schema["required"] == ["llm_provider_name"] 
