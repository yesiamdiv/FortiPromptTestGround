# Configuration loader for FortiPrompt

import yaml
from typing import Dict, Any

from .settings import RunConfig, AttackerSettings, DefenderSettings, EvaluatorSettings

def load_config(config_path: str) -> RunConfig:
    """Loads run configuration from a YAML file."""
    with open(config_path, 'r') as f:
        config_data = yaml.safe_load(f)

    attacker_cfg = config_data.get('attacker', {{}})
    defender_cfg = config_data.get('defender', {{}})
    evaluator_cfg = config_data.get('evaluator', {{}})

    attacker_settings = AttackerSettings(
        model_name=attacker_cfg.get('model_name', 'default_attacker_model'),
        strategy=attacker_cfg.get('strategy', 'single_turn'),
        max_turns=attacker_cfg.get('max_turns', 10),
        strategy_params=attacker_cfg.get('strategy_params', {{}})
    )

    defender_settings = DefenderSettings(
        model_name=defender_cfg.get('model_name', 'default_defender_model'),
        filters=defender_cfg.get('filters', [])
    )

    evaluator_settings = EvaluatorSettings(
        model_name=evaluator_cfg.get('model_name', 'default_evaluator_model'),
        evaluation_criteria=evaluator_cfg.get('evaluation_criteria', {{}})
    )

    run_config = RunConfig(
        run_id=config_data.get('run_id', 'default_run'),
        goal=config_data.get('goal', 'default_goal'),
        attacker_settings=attacker_settings,
        defender_settings=defender_settings,
        evaluator_settings=evaluator_settings
    )

    return run_config

# Example of how you might use this (e.g., in main.py):
# if __name__ == "__main__":
#     # Assuming you have a config.yaml file
#     config = load_config('path/to/your/config.yaml')
#     print(config)
