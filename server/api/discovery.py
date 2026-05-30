"""
Discovery endpoints: list and inspect available strategies, providers, and node types.

Absorbs both the discovery endpoints from the original routes.py and the
separate discovery_routes.py, which were split for no clear reason.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from pydantic import BaseModel

from server.api.schemas import (
    StrategySchemaResponse, ListStrategiesResponse,
    ProviderInfoResponse, ListProvidersResponse,
    NodeSchemaResponse, ListNodeSchemasResponse,
)
from engine.registry import get_strategy_registry, get_node_registry, NodeRegistry, StrategyRegistry
from engine.provider_registry import get_provider_registry
from core.logging import tracer, step, warn


router = APIRouter()


# ─────────────────────────────────────────────────────────────
# Strategies
# ─────────────────────────────────────────────────────────────

@router.get("/strategies", response_model=ListStrategiesResponse)
async def list_available_strategies():
    """List all registered attack strategies and their configuration schemas."""
    tracer("Listing available strategies")
    strategy_registry = get_strategy_registry()
    strategies_info = []
    for name, strategy_class in strategy_registry._registry.items():
        try:
            schema = strategy_class.get_dependency_schema()
            strategies_info.append(StrategySchemaResponse(
                strategy_name=name,
                schema_definition=schema
            ))
        except Exception:
            warn(f"Could not get schema for strategy", strategy=name)
            strategies_info.append(StrategySchemaResponse(
                strategy_name=name,
                schema_definition={"error": "Could not load schema"}
            ))
    step(f"Found {len(strategies_info)} strategies")
    return ListStrategiesResponse(strategies=strategies_info)


@router.get("/strategies/{strategy_name}/schema")
async def get_strategy_schema_by_name(strategy_name: str):
    """Get the configuration schema for a specific strategy."""
    tracer("Getting strategy schema", name=strategy_name)
    strategy_registry = get_strategy_registry()
    try:
        strategy_class = strategy_registry.get(strategy_name)
        schema = {}
        if hasattr(strategy_class, 'get_strategy_schema'):
            schema = strategy_class.get_strategy_schema()
        return StrategySchemaResponse(strategy_name=strategy_name, schema_definition=schema)
    except Exception:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found.")


# ─────────────────────────────────────────────────────────────
# Providers
# ─────────────────────────────────────────────────────────────

@router.get("/providers", response_model=ListProvidersResponse)
async def list_available_providers():
    """List all registered LLM providers."""
    tracer("Listing available providers")
    provider_registry = get_provider_registry()
    providers_info = [ProviderInfoResponse(name=name) for name in provider_registry._registry]
    step(f"Found {len(providers_info)} providers")
    return ListProvidersResponse(providers=providers_info)


# ─────────────────────────────────────────────────────────────
# Nodes
# ─────────────────────────────────────────────────────────────

def _collect_node_schemas(category_filter: str) -> List[NodeSchemaResponse]:
    """Return NodeSchemaResponse objects for all nodes whose name contains category_filter."""
    node_registry = get_node_registry()
    results = []
    for name, factory in node_registry._registry.items():
        if category_filter not in name:
            continue
        try:
            dummy_instance = factory(config={})
            schema = dummy_instance.get_node_schema() if hasattr(dummy_instance, 'get_node_schema') else {}
            results.append(NodeSchemaResponse(
                node_type=category_filter,
                node_name=name,
                schema_definition=schema
            ))
        except Exception:
            warn(f"Could not get schema for node", node=name)
            results.append(NodeSchemaResponse(
                node_type=category_filter,
                node_name=name,
                schema_definition={"error": "Could not load schema"}
            ))
    return results


@router.get("/nodes/attack", response_model=ListNodeSchemasResponse)
async def list_attack_nodes():
    """List available attack node types and their configuration schemas."""
    tracer("Listing attack nodes")
    nodes = _collect_node_schemas("attack")
    step(f"Found {len(nodes)} attack nodes")
    return ListNodeSchemasResponse(nodes=nodes)


@router.get("/nodes/defense", response_model=ListNodeSchemasResponse)
async def list_defense_nodes():
    """List available defense node types and their configuration schemas."""
    tracer("Listing defense nodes")
    nodes = _collect_node_schemas("defense")
    step(f"Found {len(nodes)} defense nodes")
    return ListNodeSchemasResponse(nodes=nodes)


@router.get("/nodes/evaluation", response_model=ListNodeSchemasResponse)
async def list_evaluation_nodes():
    """List available evaluation node types and their configuration schemas."""
    tracer("Listing evaluation nodes")
    nodes = _collect_node_schemas("eval")
    step(f"Found {len(nodes)} evaluation nodes")
    return ListNodeSchemasResponse(nodes=nodes)


# ─────────────────────────────────────────────────────────────
# Richer discovery (from original discovery_routes.py)
# ─────────────────────────────────────────────────────────────

class NodeInfo(BaseModel):
    node_type: str
    description: str
    schema: Dict[str, Any]


class StrategyInfo(BaseModel):
    strategy_name: str
    description: str
    schema: Dict[str, Any]


@router.get("/discovery/nodes", response_model=List[NodeInfo])
async def list_all_nodes_with_descriptions():
    """List all node types with full descriptions and schemas."""
    try:
        registry = NodeRegistry()
        nodes_info = []
        for node_type in registry.list_nodes():
            try:
                factory = registry._registry.get(node_type)
                node_class = getattr(factory, '__class_ref__', None)
                if node_class and hasattr(node_class, 'get_node_schema'):
                    schema = node_class.get_node_schema()
                    description = (node_class.__doc__ or f"{node_type} node").strip()
                    nodes_info.append(NodeInfo(node_type=node_type, description=description, schema=schema))
            except Exception:
                continue
        return nodes_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list nodes: {str(e)}")


@router.get("/discovery/nodes/{node_type}", response_model=NodeInfo)
async def get_node_detail(node_type: str):
    """Get description and schema for a specific node type."""
    try:
        registry = NodeRegistry()
        factory = registry._registry.get(node_type)
        if not factory:
            raise HTTPException(status_code=404, detail=f"Node type '{node_type}' not found")
        node_class = getattr(factory, '__class_ref__', None)
        if not node_class or not hasattr(node_class, 'get_node_schema'):
            return NodeInfo(node_type=node_type, description=f"{node_type} node", schema={"type": "object", "properties": {}})
        return NodeInfo(
            node_type=node_type,
            description=(node_class.__doc__ or f"{node_type} node").strip(),
            schema=node_class.get_node_schema()
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get node schema: {str(e)}")


@router.get("/discovery/strategies", response_model=List[StrategyInfo])
async def list_all_strategies_with_descriptions():
    """List all strategy types with full descriptions and schemas."""
    try:
        registry = StrategyRegistry()
        strategies_info = []
        for strategy_name in registry.list_strategies():
            try:
                strategy_class = registry._registry.get(strategy_name)
                if strategy_class and hasattr(strategy_class, 'get_strategy_schema'):
                    schema = strategy_class.get_strategy_schema()
                    description = (strategy_class.__doc__ or f"{strategy_name} strategy").strip()
                    strategies_info.append(StrategyInfo(strategy_name=strategy_name, description=description, schema=schema))
            except Exception:
                continue
        return strategies_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list strategies: {str(e)}")


@router.get("/discovery/strategies/{strategy_name}", response_model=StrategyInfo)
async def get_strategy_detail(strategy_name: str):
    """Get description and schema for a specific strategy."""
    try:
        registry = StrategyRegistry()
        strategy_class = registry._registry.get(strategy_name)
        if not strategy_class:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found")
        if not hasattr(strategy_class, 'get_strategy_schema'):
            return StrategyInfo(
                strategy_name=strategy_name,
                description=(strategy_class.__doc__ or f"{strategy_name} strategy").strip(),
                schema={"type": "object", "properties": {}}
            )
        return StrategyInfo(
            strategy_name=strategy_name,
            description=(strategy_class.__doc__ or f"{strategy_name} strategy").strip(),
            schema=strategy_class.get_strategy_schema()
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get strategy schema: {str(e)}")
