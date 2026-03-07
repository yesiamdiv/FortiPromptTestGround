# src/workflow_state.py

class WorkflowState:
    def __init__(self, session_id: str, config: dict = None):
        self.session_id = session_id
        # Initialize with a default structure if no config is provided
        self.config = self._initialize_config(config)
        self.progress = {}  # Placeholder for test progress
        self.results = {}   # Placeholder for test results

    def _initialize_config(self, config: dict) -> dict:
        """Initializes the configuration with a default structure."""
        default_config = {
            "attack_generation": {
                "type": None,
                "model": None,
                "prompt_templates": [],
                "constraints": {},
                "budget": None,
            },
            "attack_testing": {
                "target_model": None,
                "environment": None,
                "num_test_cases": 100,
                "success_criteria": {},
            },
            "defense_response": {
                "strategy": None,
                "agent_model": None,
                "response_params": {},
                "confidence_threshold": 0.5,
            },
            "evaluation": {
                "metrics": [],
                "scoring_functions": {},
                "reporting_format": "json",
            },
            "general": {
                "description": "",
                "created_at": None, # Will be set on creation
                "updated_at": None, # Will be set on updates
            }
        }
        
        # Merge provided config with defaults
        if config:
            # Deep merge would be more robust, but for simplicity, a shallow merge for top-level keys
            # and then merging nested dictionaries.
            for key, value in config.items():
                if key in default_config and isinstance(default_config[key], dict) and isinstance(value, dict):
                    default_config[key].update(value)
                else:
                    default_config[key] = value
        
        return default_config

    def update_progress(self, step: str, data: any):
        """Updates the progress of the workflow."""
        self.progress[step] = data

    def add_result(self, metric: str, value: any):
        """Adds a result for a specific metric."""
        self.results[metric] = value

    def update_config(self, section: str, key: str, value: any):
        """Updates a specific configuration parameter."""
        if section in self.config and key in self.config[section]:
            self.config[section][key] = value
        else:
            # Optionally, create the section/key if it doesn't exist
            if section not in self.config:
                self.config[section] = {}
            self.config[section][key] = value

    def get_config_value(self, section: str, key: str, default: any = None) -> any:
        """Gets a specific configuration parameter, with a default."""
        return self.config.get(section, {}).get(key, default)

    def to_dict(self) -> dict:
        """Converts the WorkflowState to a dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "config": self.config,
            "progress": self.progress,
            "results": self.results,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'WorkflowState':
        """Creates a WorkflowState object from a dictionary."""
        session_id = data.get("session_id")
        config = data.get("config")
        
        if not session_id:
            raise ValueError("Session ID is required to create WorkflowState from dict.")
            
        state = cls(session_id=session_id, config=config)
        state.progress = data.get("progress", {})
        state.results = data.get("results", {})
        return state