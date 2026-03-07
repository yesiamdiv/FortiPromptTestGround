# src/session_manager.py

from src.workflow_state import WorkflowState
from src.persistence.storage import SessionStorage, SessionStorageManager
import datetime

class SessionManager:
    def __init__(self, storage_manager: SessionStorageManager = None):
        # If no storage manager is provided, create a default one
        self.storage_manager = storage_manager if storage_manager else SessionStorageManager()
        self.sessions = {}  # In-memory cache for active sessions

    def create_session(self, session_id: str, config: dict = None, storage_type: str = "json", connection_string: str | None = None) -> WorkflowState:
        """
        Creates a new test session.
        If a session with the same ID already exists, it will be overwritten.
        """
        if session_id in self.sessions:
            print(f"Warning: Session '{session_id}' already exists and will be overwritten.")
            # Optionally, you might want to save the existing one before overwriting
            # self.save_session(session_id)

        # Ensure a storage instance is available for this session ID
        self.storage_manager.create_session_storage(session_id, storage_type, connection_string)

        # Initialize WorkflowState with current timestamp for creation
        if config is None:
            config = {}
        config.setdefault("general", {})["created_at"] = datetime.datetime.now().isoformat()
        config.setdefault("general", {})["updated_at"] = datetime.datetime.now().isoformat()

        new_state = WorkflowState(session_id=session_id, config=config)
        self.sessions[session_id] = new_state
        self.save_session(session_id) # Save immediately upon creation
        return new_state

    def load_session(self, session_id: str, storage_type: str = "json", connection_string: str | None = None) -> WorkflowState | None:
        """
        Loads an existing test session from storage.
        If the session is already in memory, it returns the in-memory version.
        """
        if session_id in self.sessions:
            return self.sessions[session_id]

        storage = self.storage_manager.get_session_storage(session_id, storage_type, connection_string)
        state_data = storage.load(session_id)

        if state_data:
            try:
                loaded_state = WorkflowState.from_dict(state_data)
                self.sessions[session_id] = loaded_state
                return loaded_state
            except ValueError as e:
                print(f"Error loading session '{session_id}': {e}")
                return None
        return None

    def save_session(self, session_id: str):
        """
        Saves the current state of a test session to storage.
        Updates the 'updated_at' timestamp.
        """
        if session_id not in self.sessions:
            print(f"Error: Session '{session_id}' not found for saving.")
            return

        state = self.sessions[session_id]
        state.update_config("general", "updated_at", datetime.datetime.now().isoformat())
        state_data = state.to_dict()

        storage = self.storage_manager.get_session_storage(session_id)
        storage.save(session_id, state_data)

    def delete_session(self, session_id: str):
        """
        Deletes a test session from both memory and storage.
        """
        if session_id in self.sessions:
            del self.sessions[session_id]
        
        # Delete from storage
        storage = self.storage_manager.get_session_storage(session_id) # Get storage to perform delete
        storage.delete(session_id)
        self.storage_manager.delete_session_storage(session_id) # Clean up storage manager's internal reference

    def list_sessions(self) -> list[str]:
        """
        Lists all available test session IDs from storage.
        This will include sessions that might not be currently loaded in memory.
        """
        return self.storage_manager.list_all()

    def get_session(self, session_id: str) -> WorkflowState | None:
        """
        Retrieves a session from memory. If not found, attempts to load it.
        """
        if session_id in self.sessions:
            return self.sessions[session_id]
        else:
            # Attempt to load it if it exists in storage
            return self.load_session(session_id)

    def update_session_config(self, session_id: str, section: str, key: str, value: any):
        """
        Updates a specific configuration parameter for a session and saves it.
        """
        session = self.get_session(session_id)
        if session:
            session.update_config(section, key, value)
            self.save_session(session_id)
        else:
            print(f"Error: Session '{session_id}' not found for config update.")

    def update_session_progress(self, session_id: str, step: str, data: any):
        """
        Updates the progress for a session and saves it.
        """
        session = self.get_session(session_id)
        if session:
            session.update_progress(step, data)
            self.save_session(session_id)
        else:
            print(f"Error: Session '{session_id}' not found for progress update.")

    def add_session_result(self, session_id: str, metric: str, value: any):
        """
        Adds a result for a session and saves it.
        """
        session = self.get_session(session_id)
        if session:
            session.add_result(metric, value)
            self.save_session(session_id)
        else:
            print(f"Error: Session '{session_id}' not found for result addition.")