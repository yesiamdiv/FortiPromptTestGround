from typing import Any, Dict

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from bson import ObjectId

from db.db_client import DatabaseClient
from db.models import Run, RunInDB, AttackData, DefenseData, EvaluationData, RunConfig

# --- Helper Functions ---

def create_mock_config():
    """Creates a mock database configuration."""
    return {
        'MONGO_URI': 'mongodb://localhost:27017/',
        'MONGO_DB_NAME': 'test_agentic_testing_ground',
        'MONGO_USERNAME': '',
        'MONGO_PASSWORD': '',
        'MONGO_HOST': 'localhost',
        'MONGO_PORT': 27017
    }

def create_mock_run_data(run_id: str = None, name: str = "Test Run", status: str = "running") -> dict:
    """Creates mock data for a RunInDB object."""
    if run_id is None:
        run_id = str(ObjectId())
    return {
        "run_id": run_id,
        "name": name,
        "status": status,
        "config": RunConfig().dict(),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow()
    }

def create_mock_attack_data(index: int = 0, prompt: str = "Test prompt") -> AttackData:
    """Creates a mock AttackData object."""
    return AttackData(index=index, prompt=prompt)

def create_mock_defense_data(index: int = 0, response: str = "Test response") -> DefenseData:
    """Creates a mock DefenseData object."""
    return DefenseData(index=index, response=response)

def create_mock_evaluation_data(index: int = 0, score: float = 0.9) -> EvaluationData:
    """Creates a mock EvaluationData object."""
    return EvaluationData(index=index, score=score)

# --- Fixtures ---

@pytest.fixture
def mock_db_client_instance():
    """Fixture to provide a DatabaseClient instance with mocked MongoDB operations."""
    with patch('motor.motor_asyncio.AsyncIOMotorClient') as MockMotorClient:
        mock_motor_client_instance = AsyncMock()
        mock_db = MagicMock()
        
        MockMotorClient.return_value = mock_motor_client_instance
        mock_motor_client_instance.__getitem__.return_value = mock_db # For client[db_name]
        
        # Mock collections
        mock_db.get_collection.side_effect = lambda name: MagicMock(name=f"mock_{name}_collection")
        
        # Mock insert_one, update_one, find_one, find, delete_one for collections
        for collection_name in ['runs', 'attack_prompts', 'defense_responses', 'evaluation_results']:
            mock_collection = mock_db.get_collection(collection_name)
            mock_collection.insert_one = AsyncMock()
            mock_collection.find_one = AsyncMock()
            mock_collection.find = AsyncMock()
            mock_collection.update_one = AsyncMock()
            mock_collection.delete_one = AsyncMock()
            
            # Configure find to return an iterable for .to_list()
            mock_collection.find.return_value.to_list = AsyncMock(return_value=[])

        # Mock ObjectId generation for insert operations
        mock_db.get_collection('runs').insert_one.return_value.inserted_id = ObjectId()
        mock_db.get_collection('attack_prompts').insert_one.return_value.inserted_id = ObjectId()
        mock_db.get_collection('defense_responses').insert_one.return_value.inserted_id = ObjectId()
        mock_db.get_collection('evaluation_results').insert_one.return_value.inserted_id = ObjectId()

        db_client = DatabaseClient(create_mock_config())
        db_client.client = mock_motor_client_instance # Manually set for easier assertion if needed
        db_client.db = mock_db # Manually set for easier assertion if needed
        yield db_client


# --- Test Cases ---

@pytest.mark.asyncio
async def test_connect_and_get_db(mock_db_client_instance):
    """Tests the connect and get_db methods."""
    await mock_db_client_instance.connect()
    assert mock_db_client_instance.client is not None
    assert mock_db_client_instance.db is not None
    
    # Test get_db after connection
    db = mock_db_client_instance.get_db()
    assert db is not None
    
    # Test get_db before connection (should raise error)
    disconnected_client = DatabaseClient(create_mock_config())
    with pytest.raises(ConnectionError, match="Database not connected. Call connect() first."):
        disconnected_client.get_db()
    
    # Test close method
    mock_db_client_instance.client.close = MagicMock()
    await mock_db_client_instance.close()
    mock_db_client_instance.client.close.assert_called_once()

@pytest.mark.asyncio
async def test_create_and_get_run(mock_db_client_instance):
    """Tests create_run and get_run methods."""
    run_data = create_mock_run_data(run_id="test_run_1")
    
    # Mock insert_one to return a mock inserted_id
    inserted_object_id = ObjectId()
    mock_db_client_instance.db.get_collection('runs').insert_one.return_value.inserted_id = inserted_object_id
    
    created_id = await mock_db_client_instance.create_run(run_data)
    assert created_id == str(inserted_object_id)
    
    # Mock the find_one result for get_run
    mock_run_doc = run_data.copy()
    mock_run_doc['_id'] = inserted_object_id # Ensure _id is present for RunInDB
    mock_db_client_instance.db.get_collection('runs').find_one.return_value = mock_run_doc
    
    retrieved_run = await mock_db_client_instance.get_run("test_run_1")
    assert retrieved_run is not None
    assert retrieved_run.run_id == "test_run_1"
    assert retrieved_run.name == run_data["name"]

@pytest.mark.asyncio
async def test_create_run_duplicate_id(mock_db_client_instance):
    """Tests that create_run raises an error for duplicate run_ids."""
    run_data = create_mock_run_data(run_id="duplicate_run")
    
    # Simulate an existing run
    mock_db_client_instance.db.get_collection('runs').find_one.return_value = {"run_id": "duplicate_run"}
    
    with pytest.raises(ValueError, match="Run with id duplicate_run already exists"):
        await mock_db_client_instance.create_run(run_data)

@pytest.mark.asyncio
async def test_get_runs(mock_db_client_instance):
    """Tests the get_runs method."""
    run_data1 = create_mock_run_data(run_id="run1")
    run_data2 = create_mock_run_data(run_id="run2")
    
    # Mock the find().to_list() result
    mock_runs_docs = [
        RunInDB(**run_data1, id=str(ObjectId())).dict(by_alias=True),
        RunInDB(**run_data2, id=str(ObjectId())).dict(by_alias=True)
    ]
    mock_db_client_instance.db.get_collection('runs').find.return_value.to_list.return_value = mock_runs_docs
    
    runs = await mock_db_client_instance.get_runs()
    assert len(runs) == 2
    assert runs[0].run_id == "run1"
    assert runs[1].run_id == "run2"

@pytest.mark.asyncio
async def test_update_run(mock_db_client_instance):
    """Tests the update_run method."""
    run_id = "test_run_id_update"
    update_data = {"status": "completed", "name": "Updated Run Name"}
    
    # Mock update_one to return a successful modification count
    mock_db_client_instance.db.get_collection('runs').update_one.return_value.modified_count = 1
    
    success = await mock_db_client_instance.update_run(run_id, update_data)
    assert success is True
    
    # Verify that update_one was called with the correct arguments
    mock_db_client_instance.db.get_collection('runs').update_one.assert_called_once()
    # Check the filter and update document
    call_args, _ = mock_db_client_instance.db.get_collection('runs').update_one.call_args
    assert call_args[0] == {'run_id': run_id}
    assert '$set' in call_args[1]
    assert call_args[1]['$set']['status'] == "completed"
    assert call_args[1]['$set']['name'] == "Updated Run Name"
    assert 'updated_at' in call_args[1]['$set'] # Ensure timestamp is added

@pytest.mark.asyncio
async def test_update_run_not_found(mock_db_client_instance):
    """Tests update_run when the run is not found."""
    run_id = "non_existent_run_id"
    update_data = {"status": "completed"}
    
    # Mock update_one to return 0 modified count
    mock_db_client_instance.db.get_collection('runs').update_one.return_value.modified_count = 0
    
    success = await mock_db_client_instance.update_run(run_id, update_data)
    assert success is False

@pytest.mark.asyncio
async def test_delete_run(mock_db_client_instance):
    """Tests the delete_run method."""
    run_id = "test_run_id_delete"
    
    # Mock delete_one to return a successful deletion count
    mock_db_client_instance.db.get_collection('runs').delete_one.return_value.deleted_count = 1
    
    success = await mock_db_client_instance.delete_run(run_id)
    assert success is True
    
    # Verify that delete_one was called with the correct arguments
    mock_db_client_instance.db.get_collection('runs').delete_one.assert_called_once_with({'run_id': run_id})

@pytest.mark.asyncio
async def test_delete_run_not_found(mock_db_client_instance):
    """Tests delete_run when the run is not found."""
    run_id = "non_existent_run_id"
    
    # Mock delete_one to return 0 deleted count
    mock_db_client_instance.db.get_collection('runs').delete_one.return_value.deleted_count = 0
    
    success = await mock_db_client_instance.delete_run(run_id)
    assert success is False

# --- Attack Data Tests ---

@pytest.mark.asyncio
async def test_create_and_get_attack_data(mock_db_client_instance):
    """Tests create_attack_data and get_attack_data."""
    run_id = "run_for_attack_data"
    attack_data = create_mock_attack_data()
    
    # Mock insert_one to return a mock inserted_id
    inserted_id = ObjectId()
    mock_db_client_instance.db.get_collection('attack_prompts').insert_one.return_value.inserted_id = inserted_id
    
    attack_id = await mock_db_client_instance.create_attack_data(run_id, attack_data)
    assert attack_id == str(inserted_id)
    
    # Mock find_one result for get_attack_data
    mock_attack_doc = attack_data.dict()
    mock_attack_doc['_id'] = inserted_id
    mock_attack_doc['run_id'] = run_id
    mock_db_client_instance.db.get_collection('attack_prompts').find_one.return_value = mock_attack_doc
    
    retrieved_attack_data = await mock_db_client_instance.get_attack_data(attack_id)
    assert retrieved_attack_data is not None
    assert retrieved_attack_data.index == attack_data.index
    assert retrieved_attack_data.prompt == attack_data.prompt

@pytest.mark.asyncio
async def test_get_attack_data_not_found(mock_db_client_instance):
    """Tests get_attack_data when the data is not found."""
    attack_id = "non_existent_attack_id"
    mock_db_client_instance.db.get_collection('attack_prompts').find_one.return_value = None
    
    retrieved_attack_data = await mock_db_client_instance.get_attack_data(attack_id)
    assert retrieved_attack_data is None

@pytest.mark.asyncio
async def test_get_attack_data_for_run(mock_db_client_instance):
    """Tests get_attack_data_for_run."""
    run_id = "test_run_id_for_attack_data"
    attack_data1 = create_mock_attack_data(index=0, prompt="Prompt 1")
    attack_data2 = create_mock_attack_data(index=1, prompt="Prompt 2")
    
    mock_attack_docs = [
        {**attack_data1.dict(), '_id': ObjectId(), 'run_id': run_id},
        {**attack_data2.dict(), '_id': ObjectId(), 'run_id': run_id}
    ]
    mock_db_client_instance.db.get_collection('attack_prompts').find.return_value.to_list.return_value = mock_attack_docs
    
    attack_data_list = await mock_db_client_instance.get_attack_data_for_run(run_id)
    assert len(attack_data_list) == 2
    assert attack_data_list[0].prompt == "Prompt 1"
    assert attack_data_list[1].prompt == "Prompt 2"

@pytest.mark.asyncio
async def test_update_attack_data(mock_db_client_instance):
    """Tests update_attack_data."""
    attack_id = str(ObjectId())
    update_data = {"prompt": "Updated prompt"}
    
    mock_db_client_instance.db.get_collection('attack_prompts').update_one.return_value.modified_count = 1
    
    success = await mock_db_client_instance.update_attack_data(attack_id, update_data)
    assert success is True
    mock_db_client_instance.db.get_collection('attack_prompts').update_one.assert_called_once_with(
        {"_id": ObjectId(attack_id)},
        {"$set": update_data}
    )

@pytest.mark.asyncio
async def test_update_attack_data_not_found(mock_db_client_instance):
    """Tests update_attack_data when the data is not found."""
    attack_id = "non_existent_attack_id"
    update_data = {"prompt": "Updated prompt"}
    
    mock_db_client_instance.db.get_collection('attack_prompts').update_one.return_value.modified_count = 0
    
    success = await mock_db_client_instance.update_attack_data(attack_id, update_data)
    assert success is False

# --- Defense Data Tests ---

@pytest.mark.asyncio
async def test_create_and_get_defense_data(mock_db_client_instance):
    """Tests create_defense_data and get_defense_data."""
    run_id = "run_for_defense_data"
    defense_data = create_mock_defense_data()
    
    inserted_id = ObjectId()
    mock_db_client_instance.db.get_collection('defense_responses').insert_one.return_value.inserted_id = inserted_id
    
    defense_id = await mock_db_client_instance.create_defense_data(run_id, defense_data)
    assert defense_id == str(inserted_id)
    
    mock_defense_doc = defense_data.dict()
    mock_defense_doc['_id'] = inserted_id
    mock_defense_doc['run_id'] = run_id
    mock_db_client_instance.db.get_collection('defense_responses').find_one.return_value = mock_defense_doc
    
    retrieved_defense_data = await mock_db_client_instance.get_defense_data(defense_id)
    assert retrieved_defense_data is not None
    assert retrieved_defense_data.index == defense_data.index
    assert retrieved_defense_data.response == defense_data.response

@pytest.mark.asyncio
async def test_get_defense_data_not_found(mock_db_client_instance):
    """Tests get_defense_data when the data is not found."""
    defense_id = "non_existent_defense_id"
    mock_db_client_instance.db.get_collection('defense_responses').find_one.return_value = None
    
    retrieved_defense_data = await mock_db_client_instance.get_defense_data(defense_id)
    assert retrieved_defense_data is None

@pytest.mark.asyncio
async def test_get_defense_data_for_run(mock_db_client_instance):
    """Tests get_defense_data_for_run."""
    run_id = "test_run_id_for_defense_data"
    defense_data1 = create_mock_defense_data(index=0, response="Response 1")
    defense_data2 = create_mock_defense_data(index=1, response="Response 2")
    
    mock_defense_docs = [
        {**defense_data1.dict(), '_id': ObjectId(), 'run_id': run_id},
        {**defense_data2.dict(), '_id': ObjectId(), 'run_id': run_id}
    ]
    mock_db_client_instance.db.get_collection('defense_responses').find.return_value.to_list.return_value = mock_defense_docs
    
    defense_data_list = await mock_db_client_instance.get_defense_data_for_run(run_id)
    assert len(defense_data_list) == 2
    assert defense_data_list[0].response == "Response 1"
    assert defense_data_list[1].response == "Response 2"

@pytest.mark.asyncio
async def test_update_defense_data(mock_db_client_instance):
    """Tests update_defense_data."""
    defense_id = str(ObjectId())
    update_data = {"response": "Updated response"}
    
    mock_db_client_instance.db.get_collection('defense_responses').update_one.return_value.modified_count = 1
    
    success = await mock_db_client_instance.update_defense_data(defense_id, update_data)
    assert success is True
    mock_db_client_instance.db.get_collection('defense_responses').update_one.assert_called_once_with(
        {"_id": ObjectId(defense_id)},
        {"$set": update_data}
    )

@pytest.mark.asyncio
async def test_update_defense_data_not_found(mock_db_client_instance):
    """Tests update_defense_data when the data is not found."""
    defense_id = "non_existent_defense_id"
    update_data = {"response": "Updated response"}
    
    mock_db_client_instance.db.get_collection('defense_responses').update_one.return_value.modified_count = 0
    
    success = await mock_db_client_instance.update_defense_data(defense_id, update_data)
    assert success is False

# --- Evaluation Data Tests ---

@pytest.mark.asyncio
async def test_create_and_get_evaluation_data(mock_db_client_instance):
    """Tests create_evaluation_data and get_evaluation_data."""
    run_id = "run_for_evaluation_data"
    evaluation_data = create_mock_evaluation_data()
    
    inserted_id = ObjectId()
    mock_db_client_instance.db.get_collection('evaluation_results').insert_one.return_value.inserted_id = inserted_id
    
    evaluation_id = await mock_db_client_instance.create_evaluation_data(run_id, evaluation_data)
    assert evaluation_id == str(inserted_id)
    
    mock_evaluation_doc = evaluation_data.dict()
    mock_evaluation_doc['_id'] = inserted_id
    mock_evaluation_doc['run_id'] = run_id
    mock_db_client_instance.db.get_collection('evaluation_results').find_one.return_value = mock_evaluation_doc
    
    retrieved_evaluation_data = await mock_db_client_instance.get_evaluation_data(evaluation_id)
    assert retrieved_evaluation_data is not None
    assert retrieved_evaluation_data.index == evaluation_data.index
    assert retrieved_evaluation_data.score == evaluation_data.score

@pytest.mark.asyncio
async def test_get_evaluation_data_not_found(mock_db_client_instance):
    """Tests get_evaluation_data when the data is not found."""
    evaluation_id = "non_existent_evaluation_id"
    mock_db_client_instance.db.get_collection('evaluation_results').find_one.return_value = None
    
    retrieved_evaluation_data = await mock_db_client_instance.get_evaluation_data(evaluation_id)
    assert retrieved_evaluation_data is None

@pytest.mark.asyncio
async def test_get_evaluation_data_for_run(mock_db_client_instance):
    """Tests get_evaluation_data_for_run."""
    run_id = "test_run_id_for_evaluation_data"
    evaluation_data1 = create_mock_evaluation_data(index=0, score=0.8)
    evaluation_data2 = create_mock_evaluation_data(index=1, score=0.95)
    
    mock_evaluation_docs = [
        {**evaluation_data1.dict(), '_id': ObjectId(), 'run_id': run_id},
        {**evaluation_data2.dict(), '_id': ObjectId(), 'run_id': run_id}
    ]
    mock_db_client_instance.db.get_collection('evaluation_results').find.return_value.to_list.return_value = mock_evaluation_docs
    
    evaluation_data_list = await mock_db_client_instance.get_evaluation_data_for_run(run_id)
    assert len(evaluation_data_list) == 2
    assert evaluation_data_list[0].score == 0.8
    assert evaluation_data_list[1].score == 0.95

@pytest.mark.asyncio
async def test_update_evaluation_data(mock_db_client_instance):
    """Tests update_evaluation_data."""
    evaluation_id = str(ObjectId())
    update_data = {"score": 0.75, "feedback": "Improved"}
    
    mock_db_client_instance.db.get_collection('evaluation_results').update_one.return_value.modified_count = 1
    
    success = await mock_db_client_instance.update_evaluation_data(evaluation_id, update_data)
    assert success is True
    mock_db_client_instance.db.get_collection('evaluation_results').update_one.assert_called_once_with(
        {"_id": ObjectId(evaluation_id)},
        {"$set": update_data}
    )

@pytest.mark.asyncio
async def test_update_evaluation_data_not_found(mock_db_client_instance):
    """Tests update_evaluation_data when the data is not found."""
    evaluation_id = "non_existent_evaluation_id"
    update_data = {"score": 0.75}
    
    mock_db_client_instance.db.get_collection('evaluation_results').update_one.return_value.modified_count = 0
    
    success = await mock_db_client_instance.update_evaluation_data(evaluation_id, update_data)
    assert success is False

@pytest.mark.asyncio
async def test_save_run_references(mock_db_client_instance):
    """Tests save_run_references."""
    run_id = "run_with_references"
    attack_ids = [str(ObjectId()), str(ObjectId())]
    defense_ids = [str(ObjectId())]
    evaluation_ids = [str(ObjectId()), str(ObjectId()), str(ObjectId())]
    
    mock_db_client_instance.db.get_collection('runs').update_one.return_value.modified_count = 1
    
    await mock_db_client_instance.save_run_references(run_id, attack_ids, defense_ids, evaluation_ids)
    
    mock_db_client_instance.db.get_collection('runs').update_one.assert_called_once()
    call_args, _ = mock_db_client_instance.db.get_collection('runs').update_one.call_args
    assert call_args[0] == {"run_id": run_id}
    assert call_args[1]['$set']['attack_store_ref'] == attack_ids
    assert call_args[1]['$set']['defense_store_ref'] == defense_ids
    assert call_args[1]['$set']['evaluation_store_ref'] == evaluation_ids
    assert 'updated_at' in call_args[1]['$set']

@pytest.mark.asyncio
async def test_close_connection(mock_db_client_instance):
    """Tests the close method for the database connection."""
    # Ensure client is mocked and has a close method
    mock_db_client_instance.client = AsyncMock() 
    await mock_db_client_instance.close()
    mock_db_client_instance.client.close.assert_called_once()

    # Test closing when client is None (no connection was ever established)
    disconnected_client = DatabaseClient(create_mock_config())
    await disconnected_client.close() # Should not raise an error
    assert disconnected_client.client is None # Should still be None

