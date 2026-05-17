"""
API Endpoints for Run Management and Discovery
"""

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
from engine.debug_utils import checkpoint, debug, err, tracer, step, warn
from engine.registry import get_strategy_registry, get_node_registry
from engine.provider_registry import get_provider_registry # Import provider registry
from server.config.models import GraphConfig, AttackNodeConfig, DefenseNodeConfig, EvaluationNodeConfig # For GraphConfig validation
from datetime import datetime
from strategies.batch_data_manager import delete_prompts_for_run


router = APIRouter()

async def _get_db_ops_dependency():
    db = get_db()
    if db is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Database not connected.")
    return get_db_ops(db)

@router.post("/runs", response_model=RunDetailsResponse, status_code=status.HTTP_201_CREATED)
async def create_new_run(
    request: CreateRunRequest,
    run_manager: RunManager = Depends(get_run_manager),
    db_ops:DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """
    Create a new adversarial run.
    
    This initializes a run record in the database but does not start execution.
    """
    tracer("Creating new run", name=request.name)
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
        step("Run created", run_id=run_id)
        
        created_run = await db_ops.get_run(run_id)
        return RunDetailsResponse(**created_run.dict())
    except Exception as e:
        err(f"Failed to create run: {e}")
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
    debug("Updating run config", run_id=run_id)
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
        if request.attack_node_params is not None:
            updates["graph_config.attack_node_config.node_params"] = request.attack_node_params
        if request.defense_node_params is not None:
            updates["graph_config.defense_node_config.node_params"] = request.defense_node_params
        if request.evaluation_node_params is not None:
            updates["graph_config.evaluation_node_config.node_params"] = request.evaluation_node_params
        
        if updates:
            updates["updated_at"] = datetime.utcnow().isoformat()
            await db_ops.update_run(run_id, updates)
            updated_run = await db_ops.get_run(run_id) # Fetch updated run
            if not updated_run:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve updated run.")
            step("Run config updated", run_id=run_id)
            return RunDetailsResponse(**updated_run.dict())
        else:
            return RunDetailsResponse(**run.dict()) # No updates provided, return original run

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to update run {run_id}: {str(e)}")

@router.delete("/runs/{run_id}")
async def delet_run(
    run_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
    ):
    """
    Delete a run from the database but not its releted data (for now)
    """
    tracer("Deleting run", run_id=run_id)
    try:
        if await db_ops.delete_run(run_id):
            # Clean up the batch prompts file on disk if it exists
            delete_prompts_for_run(run_id)
            step("Run deleted", run_id=run_id)
            return {"message":f"{run_id} is deleted"}
        else: 
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to delete run")
    except Exception as e:
        err(f"Failed to delete run: {e}")
        raise e

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
    tracer("start_existing_run", run_id=run_id)
    try:
        run_response = await run_manager.start_run(run_id, input_payload=payload)
        step("Run started", run_id=run_id, status=run_response.get("status") if isinstance(run_response, dict) else run_response.status)
        return RunResponse(**run_response)
    except ValueError as e:
        err("Run not found for start", run_id=run_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RuntimeError as e:
        err("Invalid run state for start", run_id=run_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        err("Failed to start run", run_id=run_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to start run: {str(e)}")

@router.post("/runs/{run_id}/stop", response_model=RunResponse)
async def stop_running_run(
    run_id: str,
    run_manager: RunManager = Depends(get_run_manager)
):
    """
    Stop a currently running adversarial run.
    """
    tracer("stop_running_run", run_id=run_id)
    try:
        response = await run_manager.stop_run(run_id)
        step("Run stopped", run_id=run_id)
        return RunResponse(**response)
    except ValueError as e:
        err("Run not found for stop", run_id=run_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        err("Failed to stop run", run_id=run_id, error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to stop run: {str(e)}")

@router.get("/runs", response_model=ListRunsResponse)
async def list_all_runs(db_ops: Any = Depends(_get_db_ops_dependency)):
    """
    Retrieve a list of all adversarial runs.
    """
    tracer("list_all_runs")
    try:
        runs = await db_ops.list_runs()
        step("Runs listed", count=len(runs))
        return ListRunsResponse(runs=runs)
    except Exception as e:
        err("Failed to list runs", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to list runs: {str(e)}")

@router.get("/runs/{run_id}", response_model=RunDetailsResponse)
async def get_run_details(
    run_id: str,
    db_ops: Any = Depends(_get_db_ops_dependency)
):
    """
    Retrieve detailed information about a specific adversarial run.
    """
    debug("Getting run details", run_id=run_id)
    try:
        run = await db_ops.get_run(run_id)
        if not run:
            warn(f"Run not found", run_id=run_id)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run with ID {run_id} not found.")
        checkpoint("Run details retrieved", run_id=run_id)
        return RunDetailsResponse(**run.dict())
    except HTTPException as e:
        raise e
    except Exception as e:
        err(f"Failed to get run details: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to get run details: {str(e)}")

@router.get("/strategies", response_model=ListStrategiesResponse)
async def list_available_strategies():
    """
    List all available attack strategies and their configuration schemas.
    This allows the frontend to dynamically build forms for strategy configuration.
    """
    tracer("Listing available strategies")
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
            warn(f"Could not get schema for strategy", strategy=name)
            strategies_info.append(StrategySchemaResponse(
                strategy_name=name,
                schema_definition={"error": f"Could not load schema: {str(e)}"}
            ))
    step(f"Found {len(strategies_info)} strategies")
    return ListStrategiesResponse(strategies=strategies_info)

@router.get("/providers", response_model=ListProvidersResponse)
async def list_available_providers():
    """
    List all available LLM providers.
    """
    tracer("Listing available providers")
    provider_registry = get_provider_registry()
    providers_info = []
    for name, _ in provider_registry._registry.items(): # Iterate over registered provider names
        providers_info.append(ProviderInfoResponse(name=name))
    step(f"Found {len(providers_info)} providers")
    return ListProvidersResponse(providers=providers_info)

# Node Discovery Endpoints

# Helper to get node schema (similar to strategy schema)
def _get_node_schema(node_type: str, node_name: str, node_class: Any) -> Dict[str, Any]:
    # Implement logic to get schema for a given node class
    # This might involve a class method on the node or a lookup table
    # For now, return a placeholder
    debug("Getting node schema", node_type=node_type, node_name=node_name)
    if hasattr(node_class, 'get_node_schema'): # Assuming nodes might have a schema method
        return node_class.get_node_schema() 
    return {"type": "object", "properties": {}, "description": f"Schema for {node_name} node of type {node_type}"}

@router.get("/nodes/attack", response_model=ListNodeSchemasResponse)
async def list_attack_nodes():
    """
    List available attack node types and their configuration schemas.
    """
    tracer("Listing attack nodes")
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
                warn(f"Could not get schema for attack node", node=name)
                nodes_info.append(NodeSchemaResponse(
                    node_type="attack",
                    node_name=name,
                    schema_definition={"error": f"Could not load schema: {str(e)}"}
                ))
    step(f"Found {len(nodes_info)} attack nodes")
    return ListNodeSchemasResponse(nodes=nodes_info)

@router.get("/nodes/defense", response_model=ListNodeSchemasResponse)
async def list_defense_nodes():
    """
    List available defense node types and their configuration schemas.
    """
    tracer("Listing defense nodes")
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
                warn(f"Could not get schema for defense node", node=name)
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
    tracer("Listing evaluation nodes")
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
                warn(f"Could not get schema for evaluation node", node=name)
                nodes_info.append(NodeSchemaResponse(
                    node_type="evaluation",
                    node_name=name,
                    schema_definition={"error": f"Could not load schema: {str(e)}"}
                ))
    step(f"Found {len(nodes_info)} evaluation nodes")
    return ListNodeSchemasResponse(nodes=nodes_info)


# ============================================================================
# Sync Data Endpoints (4-B1, 4-B2, 4-B3, 4-B7)
# ============================================================================

@router.get("/runs/{run_id}/attacks")
async def get_run_attacks(
    run_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """Get all attacks recorded for a run."""
    tracer("Getting run attacks", run_id=run_id)
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found.")
    attacks = await db_ops.get_attacks(run_id)
    return {"attacks": [a.dict() for a in attacks]}


@router.get("/runs/{run_id}/defences")
async def get_run_defences(
    run_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """Get all defences recorded for a run."""
    tracer("Getting run defences", run_id=run_id)
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found.")
    defences = await db_ops.get_defences(run_id)
    return {"defences": [d.dict() for d in defences]}


@router.get("/runs/{run_id}/evaluations")
async def get_run_evaluations(
    run_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """Get all evaluations recorded for a run."""
    tracer("Getting run evaluations", run_id=run_id)
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found.")
    evaluations = await db_ops.get_evaluations(run_id)
    return {"evaluations": [e.dict() for e in evaluations]}


@router.get("/runs/{run_id}/stats")
async def get_run_stats(
    run_id: str,
    db_ops: DatabaseOperations = Depends(_get_db_ops_dependency)
):
    """Get computed statistics for a run."""
    tracer("Getting run stats", run_id=run_id)
    run = await db_ops.get_run(run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id} not found.")
    
    attacks = await db_ops.get_attacks(run_id)
    defences = await db_ops.get_defences(run_id)
    evaluations = await db_ops.get_evaluations(run_id)
    
    total = len(evaluations)
    successes = sum(1 for e in evaluations if e.success)
    blocked = sum(1 for d in defences if d.was_blocked)
    scores = [e.score for e in evaluations]
    
    # Group by category
    categories = {}
    for e in evaluations:
        categories[e.category] = categories.get(e.category, 0) + 1
    
    return {
        "run_id": run_id,
        "total_attacks": len(attacks),
        "total_defences": len(defences),
        "total_evaluations": total,
        "success_rate": successes / total if total else 0.0,
        "blocked_rate": blocked / len(defences) if defences else 0.0,
        "average_score": sum(scores) / len(scores) if scores else 0.0,
        "best_score": max(scores) if scores else None,
        "categories": categories
    }


@router.get("/strategies/{strategy_name}/schema")
async def get_strategy_schema_by_name(strategy_name: str):
    """Get schema for a specific strategy by name."""
    tracer("Getting strategy schema", name=strategy_name)
    from engine.registry import get_strategy_registry
    strategy_registry = get_strategy_registry()
    try:
        strategy_class = strategy_registry.get(strategy_name)
        schema = {}
        if hasattr(strategy_class, 'get_strategy_schema'):
            schema = strategy_class.get_strategy_schema()
        return StrategySchemaResponse(strategy_name=strategy_name, schema_definition=schema)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Strategy '{strategy_name}' not found.")
