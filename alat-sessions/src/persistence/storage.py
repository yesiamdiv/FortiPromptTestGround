# src/persistence/storage.py

import json
import os
from pymongo import MongoClient

class SessionStorage:
    def __init__(self, storage_type: str = "json", connection_string: str | None = None):
        self.storage_type = storage_type
        self.connection_string = connection_string
        if self.storage_type == "mongo":
            self.client = MongoClient(self.connection_string)
            self.db = self.client.sessions
            self.collection = self.db.session_data
        else:
            self.storage_dir = "sessions_data"
            os.makedirs(self.storage_dir, exist_ok=True)

    def _get_session_filepath(self, session_id: str) -> str:
        return os.path.join(self.storage_dir, f"{session_id}.json")

    def save(self, session_id: str, state_data: dict):
        """Saves session data to a file or MongoDB."""
        if self.storage_type == "mongo":
            self.collection.update_one({"_id": session_id}, {"$set": state_data}, upsert=True)
        else:
            filepath = self._get_session_filepath(session_id)
            with open(filepath, 'w') as f:
                json.dump(state_data, f, indent=4)

    def load(self, session_id: str) -> dict | None:
        """Loads session data from a file or MongoDB."""
        if self.storage_type == "mongo":
            data = self.collection.find_one({"_id": session_id})
            if data:
                del data["_id"]
            return data
        else:
            filepath = self._get_session_filepath(session_id)
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    return json.load(f)
        return None

    def delete(self, session_id: str):
        """Deletes session data from a file or MongoDB."""
        if self.storage_type == "mongo":
            self.collection.delete_one({"_id": session_id})
        else:
            filepath = self._get_session_filepath(session_id)
            if os.path.exists(filepath):
                os.remove(filepath)

    def list_all(self) -> list[str]:
        """Lists all saved session IDs."""
        if self.storage_type == "mongo":
            return [str(s["_id"]) for s in self.collection.find({}, {"_id": 1})]
        else:
            session_files = [f for f in os.listdir(self.storage_dir) if f.endswith(".json")]
            return [os.path.splitext(f)[0] for f in session_files]

class SessionStorageManager:
    def __init__(self):
        self.sessions = {}

    def get_session_storage(self, session_id: str, storage_type: str = "json", connection_string: str | None = None) -> SessionStorage:
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionStorage(storage_type, connection_string)
        return self.sessions[session_id]

    def delete_session_storage(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]

    def create_session_storage(self, session_id: str, storage_type: str = "json", connection_string: str | None = None) -> SessionStorage:
        return self.get_session_storage(session_id, storage_type, connection_string)