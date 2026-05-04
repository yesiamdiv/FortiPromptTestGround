"""
API Endpoints for Run Management and Discovery"""

from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Dict, Any, Optional
import uuid

from server.api.schemas import (
    CreateRunRequest, UpdateRunRequest, RunResponse, RunDetailsResponse, ListRunsResponse,
    MessageResponse, ErrorResponse, StrategySchemaResponse, ListStrategiesResponse,
    ProviderInfoResponse, ListProvidersResponse, NodeSchemaResponse, ListNodeSchemasResponse
)
from server.run_manager import get_run_manager, RunManager, RunStatus
from server.database.connection import get_db
from server.database.operations import DatabaseOperations, get_db_ops
from engine.registry import get_strategy_registry, get_node_registry
from engine.provider_registry import get_provider_registry # Import provider registry
from server.config.models import GraphConfig, AttackNodeConfig, DefenseNodeConfig, EvaluationNodeConfig # For GraphConfig validation
from datetime import datetime


router = APIRouter()

async def _get_db_ops_dependency():
    db = get_db()
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database not connected.")
    return get_db_ops(db)

@router.post("/runs", response_model=RunResponse, status_code=status.HTTP_201_CREATED)
async def create_new_run(
    request: CreateRunRequest,
    run_manager: RunManager = Depends(get_run_manager),
    db_ops:DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """
    Create a new adversarial run.
    
    This initializes a run record in the database but does not start execution.
    """
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    try:
        run_data = {
            "run_id": run_id,
            "name": request.name,
            "description": request.description,
            "graph_config": {
                **request.config.model_dump(exclude_unset=True), # Exclude unset fields
                "strategy_config": {
                    "strategy_name": request.config.strategy_config.strategy_name,
                    "strategy_params": request.config.strategy_config.strategy_params or {}
                }
            },
            "created_at": datetime.utcnow().isoformat(),
            "status": RunStatus.IDLE.value # New runs are initially idle
        }
        
        await db_ops.create_run(run_data)
        
        return RunResponse(run_id=run_id, status=RunStatus.IDLE.value, message="Run created successfully.")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create run: {str(e)}")

@router.patch("/runs/{run_id}", response_model=RunDetailsResponse)
async def update_run_config(
    run_id: str,
    request: UpdateRunRequest,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """
    Update configuration for an existing run (e.g., strategy parameters).
    This allows dynamic adjustment of run settings before or during idle states.
    """
    try:
        run = await db_ops.get_run(run_id)
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run with ID {run_id} not found.")

        updates = {}
        if request.name is not None:
            updates["name"] = request.name
        if request.description is not None:
            updates["description"] = request.description
        if request.strategy_params is not None:
            updates["graph_config.strategy_config.strategy_params"] = request.strategy_params
        
        if updates:
            await db_ops.update_run(run_id, updates)
            updated_run = await db_ops.get_run(run_id) # Fetch updated run
            if not updated_run:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve updated run.")
            return RunDetailsResponse(**updated_run.dict())
        else:
            return RunDetailsResponse(**run.dict()) # No updates provided, return original run

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update run {run_id}: {str(e)}")

@router.post("/runs/{run_id}/start", response_model=RunResponse)
async def start_existing_run(
    run_id: str,
    payload: Dict[str, Any] = {}, # Optional payload for runtime config or initial prompt
    run_manager: RunManager = Depends(get_run_manager),
    db_ops: Any = Depends(_get_db_ops_dependency)
):
    """
    Start an existing adversarial run. For automatic runs, this begins the loop.
    For manual runs, this initiates the first turn or resumes from a waiting state.
    """
    try:
        run_response = await run_manager.start_run(run_id, input_payload=payload)
        return RunResponse(**run_response)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to start run: {str(e)}")

@router.post("/runs/{run_id}/stop", response_model=RunResponse)
async def stop_running_run(
    run_id: str,
    run_manager: RunManager = Depends(get_run_manager)
):
    """
    Stop a currently running adversarial run.
    """
    try:
        response = await run_manager.stop_run(run_id)
        return RunResponse(**response)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to stop run: {str(e)}")

@router.get("/runs", response_model=ListRunsResponse)
async def list_all_runs(db_ops: Any = Depends(_get_db_ops_dependency)):
    """
    Retrieve a list of all adversarial runs.
    """
    try:
        runs = await db_ops.list_runs()
        return ListRunsResponse(runs=runs)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list runs: {str(e)}")

@router.get("/runs/{run_id}", response_model=RunDetailsResponse)
async def get_run_details(
    run_id: str,
    db_ops: Any = Depends(_get_db_ops_dependency)
):
    """
    Retrieve detailed information about a specific adversarial run.
    """
    try:
        run = await db_ops.get_run(run_id)
        if not run:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run with ID {run_id} not found.")
        return RunDetailsResponse(**run.dict())
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get run details: {str(e)}")

@router.get("/strategies", response_model=ListStrategiesResponse)
async def list_available_strategies():
    """
    List all available attack strategies and their configuration schemas.
    This allows the frontend to dynamically build forms for strategy configuration.
    """
    strategy_registry = get_strategy_registry()
    strategies_info = []
    for name, strategy_class in strategy_registry._registry.items():
        try:
            description = getattr(strategy_class, '__doc__', '').strip().split('\n')[0] or name
            schema = strategy_class.get_dependency_schema()
            strategies_info.append(StrategySchemaResponse(
                strategy_name=name,
                schema_definition=schema
            ))
        except Exception as e:
            print(f"Warning: Could not get schema for strategy {name}: {e}")
            strategies_info.append(StrategySchemaResponse(
                strategy_name=name,
                schema_definition={"error": f"Could not load schema: {str(e)}"}
            ))
    return ListStrategiesResponse(strategies=strategies_info)

@router.get("/providers", response_model=ListProvidersResponse)
async def list_available_providers():
    """
    List all available LLM providers.
    """
    provider_registry = get_provider_registry()
    providers_info = []
    for name, _ in provider_registry._registry.items(): # Iterate over registered provider names
        providers_info.append(ProviderInfoResponse(name=name))
    return ListProvidersResponse(providers=providers_info)

# Node Discovery Endpoints

# Helper to get node schema (similar to strategy schema)
def _get_node_schema(node_type: str, node_name: str, node_class: Any) -> Dict[str, Any]:
    # Implement logic to get schema for a given node class
    # This might involve a class method on the node or a lookup table
    # For now, return a placeholder
    if hasattr(node_class, 'get_node_schema'): # Assuming nodes might have a schema method
        return node_class.get_node_schema() 
    return {"type": "object", "properties": {}, "description": f"Schema for {node_name} node of type {node_type}"}

@router.get("/nodes/attack", response_model=ListNodeSchemasResponse)
async def list_attack_nodes():
    """
    List available attack node types and their configuration schemas.
    """
    node_registry = get_node_registry()
    nodes_info = []
    # This part assumes a way to filter nodes by type (e.g., attack, defense, eval)
    # The registry currently has generic factories. We need a way to know node's *type*.
    # For now, manually filter based on registered names if convention allows, or enhance registry.
    # For this example, we'll list all registered nodes and assume relevant ones are 'attack' related.
    for name, factory in node_registry._registry.items():
        # Heuristic: If node name contains 'attack' or is default_attack
        if "attack" in name or name == "default_attack":
            try:
                # To get the schema, we might need to instantiate the node, or have a classmethod.
                # For now, we'll create a dummy instance or assume a schema method exists.
                # A better registry design would allow querying schema without instantiation.
                dummy_instance = factory(config={}) # Might require dummy config
                schema = {} # Replace with actual schema retrieval if node has get_schema()
                if hasattr(dummy_instance, 'get_node_schema'):
                    schema = dummy_instance.get_node_schema()
                
                nodes_info.append(NodeSchemaResponse(
                    node_type="attack", # Hardcoded for this endpoint
                    node_name=name,
                    schema_definition=schema
                ))
            except Exception as e:
                print(f"Warning: Could not get schema for attack node {name}: {e}")
                nodes_info.append(NodeSchemaResponse(
                    node_type="attack",
                    node_name=name,
                    schema_definition={"error": f"Could not load schema: {str(e)}"}
                ))
    return ListNodeSchemasResponse(nodes=nodes_info)

@router.get("/nodes/defense", response_model=ListNodeSchemasResponse)
async def list_defense_nodes():
    """
    List available defense node types and their configuration schemas.
    """
    node_registry = get_node_registry()
    nodes_info = []
    for name, factory in node_registry._registry.items():
        if "defense" in name or name == "default_defense" or name == "defence" or name == "ensemble_defense" or name == "multilayer_defense":
            try:
                dummy_instance = factory(config={})
                schema = {}
                if hasattr(dummy_instance, 'get_node_schema'):
                    schema = dummy_instance.get_node_schema()
                nodes_info.append(NodeSchemaResponse(
                    node_type="defense",
                    node_name=name,
                    schema_definition=schema
                ))
            except Exception as e:
                print(f"Warning: Could not get schema for defense node {name}: {e}")
                nodes_info.append(NodeSchemaResponse(
                    node_type="defense",
                    node_name=name,
                    schema_definition={"error": f"Could not load schema: {str(e)}"}
                ))
    return ListNodeSchemasResponse(nodes=nodes_info)

@router.get("/nodes/evaluation", response_model=ListNodeSchemasResponse)
async def list_evaluation_nodes():
    """
    List available evaluation node types and their configuration schemas.
    """
    node_registry = get_node_registry()
    nodes_info = []
    for name, factory in node_registry._registry.items():
        if "eval" in name or name == "default_eval" or name == "llm_eval" or name == "server_eval":
            try:
                dummy_instance = factory(config={})
                schema = {}
                if hasattr(dummy_instance, 'get_node_schema'):
                    schema = dummy_instance.get_node_schema()
                nodes_info.append(NodeSchemaResponse(
                    node_type="evaluation",
                    node_name=name,
                    schema_definition=schema
                ))
            except Exception as e:
                print(f"Warning: Could not get schema for evaluation node {name}: {e}")
                nodes_info.append(NodeSchemaResponse(
                    node_type="evaluation",
                    node_name=name,
                    schema_definition={"error": f"Could not load schema: {str(e)}"}
                ))
    return ListNodeSchemasResponse(nodes=nodes_info)
