# tests/test_session_manager.py

import unittest
import os
import shutil

# Assuming your src directory is accessible, e.g., by adding it to sys.path
# or by installing the package. For simplicity in this example, we'll assume
# it's importable.
from src.session_manager import SessionManager
from src.workflow_state import WorkflowState
from src.persistence.storage import Storage

class TestSessionManager(unittest.TestCase):

    def setUp(self):
        """Set up for test methods."""
        self.storage_dir = "test_sessions_data"
        self.storage = Storage(storage_dir=self.storage_dir)
        self.session_manager = SessionManager(storage=self.storage) # Assuming SessionManager will take storage as an argument

        # Clean up any previous test data
        if os.path.exists(self.storage_dir):
            shutil.rmtree(self.storage_dir)
        os.makedirs(self.storage_dir)

    def tearDown(self):
        """Tear down for test methods."""
        # Clean up the test storage directory
        if os.path.exists(self.storage_dir):
            shutil.rmtree(self.storage_dir)

    def test_create_and_load_session(self):
        session_id = "test_session_1"
        config = {"attacker": "random", "defender": "fixed"}
        
        # Mocking the SessionManager to accept a storage object
        # In a real scenario, SessionManager would be initialized with Storage
        # For this test, we'll simulate that.
        # Let's adjust SessionManager to accept storage in its constructor
        
        # Re-initialize SessionManager with storage for this test
        session_manager_instance = SessionManager(storage=self.storage)
        
        session_manager_instance.create_session(session_id, config)
        
        # Verify session file exists
        self.assertTrue(os.path.exists(self.storage._get_session_filepath(session_id)))
        
        loaded_session_state = session_manager_instance.load_session(session_id)
        
        self.assertIsNotNone(loaded_session_state)
        self.assertEqual(loaded_session_state.session_id, session_id)
        self.assertEqual(loaded_session_state.config, config)

    def test_save_session(self):
        session_id = "test_session_2"
        config = {"attacker": "adversarial", "defender": "robust"}
        
        session_manager_instance = SessionManager(storage=self.storage)
        session_manager_instance.create_session(session_id, config)
        
        # Simulate some progress
        workflow_state = session_manager_instance.sessions[session_id] # Accessing internal state for test
        workflow_state.update_progress("step1", "completed")
        workflow_state.add_result("accuracy", 0.95)
        
        session_manager_instance.save_session(session_id)
        
        # Load directly from storage to verify saved state
        saved_data = self.storage.load(session_id)
        self.assertIsNotNone(saved_data)
        self.assertEqual(saved_data['progress']['step1'], "completed")
        self.assertEqual(saved_data['results']['accuracy'], 0.95)

    def test_delete_session(self):
        session_id = "test_session_3"
        config = {"attacker": "fuzzing", "defender": "detection"}
        
        session_manager_instance = SessionManager(storage=self.storage)
        session_manager_instance.create_session(session_id, config)
        
        self.assertTrue(os.path.exists(self.storage._get_session_filepath(session_id)))
        
        session_manager_instance.delete_session(session_id)
        
        self.assertFalse(os.path.exists(self.storage._get_session_filepath(session_id)))
        self.assertNotIn(session_id, session_manager_instance.sessions) # Assuming sessions are stored in memory

    def test_list_sessions(self):
        session_id_1 = "session_a"
        session_id_2 = "session_b"
        config_1 = {"param": 1}
        config_2 = {"param": 2}
        
        session_manager_instance = SessionManager(storage=self.storage)
        session_manager_instance.create_session(session_id_1, config_1)
        session_manager_instance.create_session(session_id_2, config_2)
        
        session_ids = session_manager_instance.list_sessions()
        self.assertIn(session_id_1, session_ids)
        self.assertIn(session_id_2, session_ids)
        self.assertEqual(len(session_ids), 2)

# Note: The SessionManager class in src/session_manager.py needs to be
# adjusted to accept a storage object and manage sessions in memory.
# The tests above assume such adjustments.