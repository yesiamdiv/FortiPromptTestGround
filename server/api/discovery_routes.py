"""
Discovery Routes - API endpoints to discover available nodes, strategies, and their schemas
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from engine.registry import NodeRegistry, StrategyRegistry
from pydantic import BaseModel


router = APIRouter(prefix="/discovery", tags=["discovery"])


class NodeInfo(BaseModel):
    """Information about a node type"""
    node_type: str
    description: str
    schema: Dict[str, Any]


class StrategyInfo(BaseModel):
    """Information about a strategy type"""
    strategy_name: str
    description: str
    schema: Dict[str, Any]


@router.get("/nodes", response_model=List[NodeInfo])
async def list_available_nodes():
    """
    Get list of all available node types with their parameter schemas.
    Used by frontend to dynamically show node configuration options.
    """
    try:
        registry = NodeRegistry()
        nodes_info = []
        
        for node_type in registry.list_nodes():
            try:
                # Get the factory function
                factory = registry._registry.get(node_type)
                # Try to get the class reference attached to the factory
                node_class = getattr(factory, '__class_ref__', None)
                
                if node_class and hasattr(node_class, 'get_node_schema'):
                    schema = node_class.get_node_schema()
                    description = node_class.__doc__ or f"{node_type} node"
                    nodes_info.append(NodeInfo(
                        node_type=node_type,
                        description=description.strip(),
                        schema=schema
                    ))
            except Exception as e:
                print(f"Error getting schema for node {node_type}: {e}")
                continue
        
        return nodes_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list nodes: {str(e)}")


@router.get("/nodes/{node_type}", response_model=NodeInfo)
async def get_node_schema(node_type: str):
    """
    Get parameter schema for a specific node type.
    """
    try:
        registry = NodeRegistry()
        factory = registry._registry.get(node_type)
        
        if not factory:
            raise HTTPException(status_code=404, detail=f"Node type '{node_type}' not found")
        
        # Try to get the class reference attached to the factory
        node_class = getattr(factory, '__class_ref__', None)
        
        if not node_class or not hasattr(node_class, 'get_node_schema'):
            return NodeInfo(
                node_type=node_type,
                description=f"{node_type} node",
                schema={"type": "object", "properties": {}}
            )
        
        schema = node_class.get_node_schema()
        description = node_class.__doc__ or f"{node_type} node"
        
        return NodeInfo(
            node_type=node_type,
            description=description.strip(),
            schema=schema
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get node schema: {str(e)}")


@router.get("/strategies", response_model=List[StrategyInfo])
async def list_available_strategies():
    """
    Get list of all available strategy types with their parameter schemas.
    Used by frontend to dynamically show strategy configuration options.
    """
    try:
        registry = StrategyRegistry()
        strategies_info = []
        
        for strategy_name in registry.list_strategies():
            try:
                # Get the strategy class (not instance)
                strategy_class = registry._registry.get(strategy_name)
                if strategy_class and hasattr(strategy_class, 'get_strategy_schema'):
                    schema = strategy_class.get_strategy_schema()
                    description = strategy_class.__doc__ or f"{strategy_name} strategy"
                    strategies_info.append(StrategyInfo(
                        strategy_name=strategy_name,
                        description=description.strip(),
                        schema=schema
                    ))
            except Exception as e:
                print(f"Error getting schema for strategy {strategy_name}: {e}")
                continue
        
        return strategies_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list strategies: {str(e)}")


@router.get("/strategies/{strategy_name}", response_model=StrategyInfo)
async def get_strategy_schema(strategy_name: str):
    """
    Get parameter schema for a specific strategy type.
    """
    try:
        registry = StrategyRegistry()
        strategy_class = registry._registry.get(strategy_name)
        
        if not strategy_class:
            raise HTTPException(status_code=404, detail=f"Strategy '{strategy_name}' not found")
        
        if not hasattr(strategy_class, 'get_strategy_schema'):
            return StrategyInfo(
                strategy_name=strategy_name,
                description=strategy_class.__doc__ or f"{strategy_name} strategy",
                schema={"type": "object", "properties": {}}
            )
        
        schema = strategy_class.get_strategy_schema()
        description = strategy_class.__doc__ or f"{strategy_name} strategy"
        
        return StrategyInfo(
            strategy_name=strategy_name,
            description=description.strip(),
            schema=schema
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get strategy schema: {str(e)}")