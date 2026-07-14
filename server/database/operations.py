
"""
Database Operations
"""

from typing import Dict, Any, List, Optional
from fastapi.encoders import jsonable_encoder
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid
from server.database.models import (
    RunModel,
    AttackData,
    DefenceData,
    EvaluationData,
    Session,
    Turn,
)
from core.logging import checkpoint, debug, err, tracer, step
from core.config import GraphConfig
from engine.state import SystemState



class DatabaseOperations:
    """
    Database operations for adversarial testing data.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize with database instance.
        
        Args:
            db: MongoDB database instance
        """
        tracer("DatabaseOperations initialized")
        self.db = db
        self.runs = db.runs
        self.attacks = db.attacks
        self.defences = db.defences
        self.evaluations = db.evaluations
        self.sessions = db.sessions
        self.turns = db.turns
    
    # ========================================================================
    # Run Operations
    # ========================================================================
    
    async def create_run(self, run_data: Dict[str, Any]) -> str:
        """
        Create a new run document. This is for the overall run campaign.
        
        Args:
            run_data: Run data dictionary. Must include 'run_id', 'strategy', and 'graph_config'.
        
        Returns:
            run_id of created run
        """
        tracer("Creating run", run_id=run_data.get("run_id"))
        
        if 'graph_config' not in run_data:
            raise ValueError("Graph configuration is missing in run_data.")
        
        run_doc = {
            **run_data,
            "created_at": datetime.utcnow().isoformat(),
            "status": run_data.get("status", "idle") # Default status to idle if not provided
        }
        
        result = await self.runs.insert_one(run_doc)
        step("Run created", run_id=run_data.get("run_id"))
        return run_data["run_id"]
    
    async def get_run(self, run_id: str) -> Optional[RunModel]:
        """
        Get run by ID.
        
        Args:
            run_id: Run identifier
        
        Returns:
            RunModel instance or None.
        """
        debug("Getting run", run_id=run_id)
        run_doc = await self.runs.find_one({"run_id": run_id})
        if run_doc:
            run_doc.pop("_id", None)
            # Derive components from graph_config if not already stored
            if not run_doc.get("components"):
                gc = run_doc.get("graph_config", {})
                comps = []
                for key in ("attack_node_config", "defense_node_config", "evaluation_node_config"):
                    cfg = gc.get(key, {})
                    if isinstance(cfg, dict) and cfg.get("node_type"):
                        comps.append(cfg["node_type"])
                if gc.get("strategy_config", {}).get("strategy_name"):
                    comps.append(gc["strategy_config"]["strategy_name"])
                run_doc["components"] = comps
            return RunModel(**run_doc)
        return None
    
    async def update_run(self, run_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update run document.
        
        Args:
            run_id: Run identifier
            updates: Fields to update
        
        Returns:
            True if updated, False if not found
        """
        debug("Updating run", run_id=run_id, updates=list(updates.keys()))
        result = await self.runs.update_one(
            {"run_id": run_id},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    async def delete_run(
        self,
        run_id: str     
    ) -> bool:
        """
        Delete a runs record, not its related data (for now)
        
        Args:
            run_id: Run identifier

        Returns:
            True or false
        """
        tracer("Deleting run", run_id=run_id)
        result = await self.runs.delete_one({"run_id": run_id})
        step("Run deleted", run_id=run_id)
        return result.deleted_count > 0

    async def mark_run_failed(self, run_id: str, error: str) -> bool:
        """
        Mark run as failed.
        
        Args:
            run_id: Run identifier
            error: Error message
        
        Returns:
            True if updated
        """
        err(f"Marking run failed: {error}")
        return await self.update_run(run_id, {
            "status": "failed",
            "completed_at": datetime.utcnow().isoformat(),
            "error": error
        })
    
    async def list_runs(
        self,
        status: Optional[str] = None,
        limit: int = 100,
        skip: int = 0
    ) -> List[RunModel]:
        """
        List runs with optional filtering.
        
        Args:
            status: Filter by status
            limit: Maximum number to return
            skip: Number to skip (pagination)
        
        Returns:
            List of RunModel instances
        """
        tracer("Listing runs", status=status, limit=limit, skip=skip)
        query = {}
        if status:
            query["status"] = status
        
        cursor = self.runs.find(query).sort("created_at", -1).skip(skip).limit(limit)
        run_docs = await cursor.to_list(length=limit)
        
        step(f"Found {len(run_docs)} runs")
        return [RunModel(**{k: v for k, v in doc.items() if k != "_id"}) for doc in run_docs]
    
    # ========================================================================
    # Attack Operations
    # ========================================================================
    
    async def save_attack(
        self,
        run_id: str,
        index: int,
        turn_id: str,
        prompt: str,
        metadata: Dict[str, Any] = None,
        timestamp: str = None
    ) -> str:
        """
        Save attack to database.
        
        Args:
            run_id: Associated run ID
            index: Attack index/iteration number
            turn_id: Turn identifier
            prompt: Attack prompt text
            metadata: Additional metadata
            timestamp: ISO timestamp when the attack was recorded
        
        Returns:
            Inserted document ID
        """
        tracer("Saving attack", run_id=run_id, index=index, turn_id=turn_id)
        attack_doc = {
            "run_id": run_id,
            "index": index,
            "turn_id": turn_id,
            "prompt": prompt,
            "metadata": metadata or {},
            "timestamp": timestamp or datetime.utcnow().isoformat()
        }
        
        result = await self.attacks.insert_one(attack_doc)
        step("Attack saved", run_id=run_id, index=index)
        return str(result.inserted_id)
    
    async def get_attacks(self, run_id: str) -> List[AttackData]:
        """
        Get all attacks for a run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            List of AttackData instances
        """
        debug("Getting attacks", run_id=run_id)
        cursor = self.attacks.find({"run_id": run_id}).sort("index", 1)
        attack_docs = await cursor.to_list(length=None)
        
        step(f"Found {len(attack_docs)} attacks", run_id=run_id)
        return [AttackData(**{k: v for k, v in doc.items() if k != "_id"}) for doc in attack_docs]    
    # ========================================================================
    # Defence Operations
    # ========================================================================
    
    async def save_defence(
        self,
        run_id: str,
        index: int,
        turn_id: str,
        response: str,
        status_code: int,
        was_blocked: bool,
        metadata: Dict[str, Any] = None,
        timestamp: str = None
    ) -> str:
        """
        Save defence response to database.
        
        Args:
            run_id: Associated run ID
            index: Defence index/iteration number
            turn_id: Turn identifier
            response: Defence response text
            status_code: HTTP status code
            was_blocked: Whether request was blocked
            metadata: Additional metadata
            timestamp: ISO timestamp when the defence response was recorded
        
        Returns:
            Inserted document ID
        """
        tracer("Saving defence", run_id=run_id, index=index, was_blocked=was_blocked)
        defence_doc = {
            "run_id": run_id,
            "index": index,
            "turn_id": turn_id,
            "response": response,
            "status_code": status_code,
            "was_blocked": was_blocked,
            "metadata": metadata or {},
            "timestamp": timestamp or datetime.utcnow().isoformat()
        }
        
        result = await self.defences.insert_one(defence_doc)
        step("Defence saved", run_id=run_id, index=index)
        return str(result.inserted_id)
    
    async def get_defences(self, run_id: str) -> List[DefenceData]:
        """
        Get all defences for a run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            List of DefenceData instances
        """
        debug("Getting defences", run_id=run_id)
        cursor = self.defences.find({"run_id": run_id}).sort("index", 1)
        defence_docs = await cursor.to_list(length=None)
        
        step(f"Found {len(defence_docs)} defences", run_id=run_id)
        return [DefenceData(**{k: v for k, v in doc.items() if k != "_id"}) for doc in defence_docs]
    
    # ========================================================================
    # Evaluation Operations
    # ========================================================================
    
    async def save_evaluation(
        self,
        run_id: str,
        index: int,
        turn_id: str,
        score: float,
        success: bool,
        category: str,
        feedback: Optional[str] = None,
        metadata: Dict[str, Any] = None,
        timestamp: str = None
    ) -> str:
        """
        Save evaluation to database.
        
        Args:
            run_id: Associated run ID
            index: Evaluation index/iteration number
            turn_id: Turn identifier
            score: Evaluation score (0-1)
            success: Whether attack was successful
            category: Classification category
            feedback: Evaluation reasoning/feedback
            metadata: Additional metadata
            timestamp: ISO timestamp when the evaluation was recorded
        
        Returns:
            Inserted document ID
        """
        tracer("Saving evaluation", run_id=run_id, index=index, score=score, success=success)
        eval_doc = {
            "run_id": run_id,
            "index": index,
            "turn_id": turn_id,
            "score": score,
            "success": success,
            "category": category,
            "feedback": feedback,
            "metadata": metadata or {},
            "timestamp": timestamp or datetime.utcnow().isoformat()
        }
        
        result = await self.evaluations.insert_one(eval_doc)
        step("Evaluation saved", run_id=run_id, index=index, score=score)
        return str(result.inserted_id)
    
    async def get_evaluations(self, run_id: str) -> List[EvaluationData]:
        """
        Get all evaluations for a run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            List of EvaluationData instances
        """
        debug("Getting evaluations", run_id=run_id)
        cursor = self.evaluations.find({"run_id": run_id}).sort("index", 1)
        eval_docs = await cursor.to_list(length=None)
        
        step(f"Found {len(eval_docs)} evaluations", run_id=run_id)
        return [EvaluationData(**{k: v for k, v in doc.items() if k != "_id"}) for doc in eval_docs]

    async def get_attack_by_id(self, doc_id: str):
        """Get an attack by MongoDB document ID (string)."""
        from bson import ObjectId
        try:
            doc = await self.attacks.find_one({"_id": ObjectId(doc_id)})
            if doc:
                doc.pop("_id", None)
                return AttackData(**doc)
        except Exception:
            pass
        return None

    async def get_defence_by_id(self, doc_id: str):
        """Get a defence by MongoDB document ID (string)."""
        from bson import ObjectId
        try:
            doc = await self.defences.find_one({"_id": ObjectId(doc_id)})
            if doc:
                doc.pop("_id", None)
                return DefenceData(**doc)
        except Exception:
            pass
        return None

    async def get_evaluation_by_id(self, doc_id: str):
        """Get an evaluation by MongoDB document ID (string)."""
        from bson import ObjectId
        try:
            doc = await self.evaluations.find_one({"_id": ObjectId(doc_id)})
            if doc:
                doc.pop("_id", None)
                return EvaluationData(**doc)
        except Exception:
            pass
        return None

    # ========================================================================
    # Unified Session Operations
    # ========================================================================

    async def create_session(
        self,
        session_id: str,
        run_id: str,
        name: str,
        run_type: str,
        description: str = "",
    ) -> str:
        """Create a new session document in the unified sessions collection."""
        tracer("Creating session", session_id=session_id, run_id=run_id, run_type=run_type)
        now = datetime.utcnow().isoformat()
        session_doc = {
            "session_id": session_id,
            "run_id": run_id,
            "name": name,
            "description": description,
            "run_type": run_type,
            "status": "active",
            "created_at": now,
            "updated_at": now,
            "turn_ids": [],
            "total_turns": 0,
            "successful_turns": 0,
        }
        await self.sessions.insert_one(session_doc)
        step("Session created", session_id=session_id)
        return session_id

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID from the unified sessions collection."""
        debug("Getting session", session_id=session_id)
        doc = await self.sessions.find_one({"session_id": session_id})
        if doc:
            doc.pop("_id", None)
            return Session(**doc)
        return None

    async def update_session(self, session_id: str, **fields) -> None:
        """Update fields on a session document."""
        debug("Updating session", session_id=session_id, fields=list(fields.keys()))
        fields["updated_at"] = datetime.utcnow().isoformat()
        await self.sessions.update_one(
            {"session_id": session_id},
            {"$set": fields}
        )

    async def get_sessions_for_run(self, run_id: str) -> list:
        """List all sessions for a run, ordered by creation time."""
        tracer("Getting sessions for run", run_id=run_id)
        cursor = self.sessions.find({"run_id": run_id}).sort("created_at", 1)
        docs = await cursor.to_list(length=None)
        step(f"Found {len(docs)} sessions", run_id=run_id)
        return [Session(**{k: v for k, v in d.items() if k != "_id"}) for d in docs]

    # ========================================================================
    # Unified Turn Operations
    # ========================================================================

    async def create_turn(
        self,
        session_id: str,
        turn_id: str,
        run_id: str,
        index: int,
    ) -> str:
        """Create a new turn document and append its ID to the parent session."""
        tracer("Creating turn", turn_id=turn_id, session_id=session_id, index=index)
        now = datetime.utcnow().isoformat()
        turn_doc = {
            "turn_id": turn_id,
            "session_id": session_id,
            "run_id": run_id,
            "index": index,
            "attack_data_id": None,
            "defence_data_id": None,
            "evaluation_data_id": None,
            "created_at": now,
            "updated_at": now,
            "metadata": {},
        }
        await self.turns.insert_one(turn_doc)
        await self.sessions.update_one(
            {"session_id": session_id},
            {
                "$push": {"turn_ids": turn_id},
                "$inc": {"total_turns": 1},
                "$set": {"updated_at": now},
            },
        )
        step("Turn created", turn_id=turn_id, index=index)
        return turn_id

    async def update_turn_references(
        self,
        turn_id: str,
        attack_data_id: Optional[str] = None,
        defence_data_id: Optional[str] = None,
        evaluation_data_id: Optional[str] = None,
    ) -> None:
        """Link AttackData / DefenceData / EvaluationData IDs into a turn document."""
        debug("Updating turn references", turn_id=turn_id)
        updates: dict = {"updated_at": datetime.utcnow().isoformat()}
        if attack_data_id is not None:
            updates["attack_data_id"] = attack_data_id
        if defence_data_id is not None:
            updates["defence_data_id"] = defence_data_id
        if evaluation_data_id is not None:
            updates["evaluation_data_id"] = evaluation_data_id
        await self.turns.update_one({"turn_id": turn_id}, {"$set": updates})

    async def get_turn(self, turn_id: str) -> Optional[Turn]:
        """Get a turn by ID."""
        debug("Getting turn", turn_id=turn_id)
        doc = await self.turns.find_one({"turn_id": turn_id})
        if doc:
            doc.pop("_id", None)
            return Turn(**doc)
        return None

    async def get_turns_for_session(self, session_id: str) -> list:
        """Get all turns for a session, ordered by index."""
        tracer("Getting turns for session", session_id=session_id)
        cursor = self.turns.find({"session_id": session_id}).sort("index", 1)
        docs = await cursor.to_list(length=None)
        step(f"Found {len(docs)} turns", session_id=session_id)
        return [Turn(**{k: v for k, v in d.items() if k != "_id"}) for d in docs]

    async def get_last_turn_for_session(self, session_id: str) -> Optional[Turn]:
        """Get the most recent turn in a session."""
        debug("Getting last turn", session_id=session_id)
        docs = await self.turns.find(
            {"session_id": session_id}
        ).sort("index", -1).limit(1).to_list(length=1)
        if docs:
            docs[0].pop("_id", None)
            return Turn(**docs[0])
        return None


# ========================================================================
# Convenience function
# ========================================================================

def get_db_ops(db: AsyncIOMotorDatabase) -> DatabaseOperations:
    """
    Create DatabaseOperations instance.

    Args:
        db: MongoDB database

    Returns:
        DatabaseOperations instance
    """
    debug("Creating DatabaseOperations instance")
    return DatabaseOperations(db)
