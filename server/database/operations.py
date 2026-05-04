
"""
Database Operations
"""

from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
import uuid
from server.database.models_v2 import (
    RunModel,
    AttackData,
    DefenceData,
    EvaluationData,
    RunStatistics,
    ManualTurn,
    ManualSession,
    SystemState # Assuming SystemState is also a Pydantic model or dict type
)
from server.config.models import GraphConfig # Import GraphConfig for type hinting and Pydantic parsing


class DatabaseOperations:
    """
    Database operations for adversarial testing data.
    
    Manages separate collections for runs, attacks, defences, evaluations,
    and specific collections for manual sessions and turns.
    """
    
    def __init__(self, db: AsyncIOMotorDatabase):
        """
        Initialize with database instance.
        
        Args:
            db: MongoDB database instance
        """
        self.db = db
        self.runs = db.runs
        self.attacks = db.attacks
        self.defences = db.defences
        self.evaluations = db.evaluations
        self.manual_sessions = db.manual_sessions  # New collection for manual sessions
        self.manual_turns = db.manual_turns      # New collection for manual turns
    
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
        if 'graph_config' not in run_data:
            raise ValueError("Graph configuration is missing in run_data.")
        
        run_doc = {
            **run_data,
            "created_at": datetime.utcnow().isoformat(),
            "status": run_data.get("status", "idle") # Default status to idle if not provided
        }
        
        result = await self.runs.insert_one(run_doc)
        return run_data["run_id"]
    
    async def get_run(self, run_id: str) -> Optional[RunModel]:
        """
        Get run by ID.
        
        Args:
            run_id: Run identifier
        
        Returns:
            RunModel instance or None.
        """
        run_doc = await self.runs.find_one({"run_id": run_id})
        if run_doc:
            run_doc.pop("_id", None)
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
        result = await self.runs.update_one(
            {"run_id": run_id},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    async def mark_run_completed(
        self,
        run_id: str,
        final_score: Optional[float] = None,
        best_score: Optional[float] = None
    ) -> bool:
        """
        Mark run as completed.
        
        Args:
            run_id: Run identifier
            final_score: Final evaluation score
            best_score: Best score achieved
        
        Returns:
            True if updated
        """
        updates = {
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat()
        }
        
        if final_score is not None:
            updates["final_score"] = final_score
        if best_score is not None:
            updates["best_score"] = best_score
        
        return await self.update_run(run_id, updates)
    
    async def mark_run_failed(self, run_id: str, error: str) -> bool:
        """
        Mark run as failed.
        
        Args:
            run_id: Run identifier
            error: Error message
        
        Returns:
            True if updated
        """
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
        query = {}
        if status:
            query["status"] = status
        
        cursor = self.runs.find(query).sort("created_at", -1).skip(skip).limit(limit)
        run_docs = await cursor.to_list(length=limit)
        
        return [RunModel(**doc.pop("_id", None) or doc) for doc in run_docs]
    
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
        attack_doc = {
            "run_id": run_id,
            "index": index,
            "turn_id": turn_id,
            "prompt": prompt,
            "metadata": metadata or {},
            "timestamp": timestamp or datetime.utcnow().isoformat()
        }
        
        result = await self.attacks.insert_one(attack_doc)
        return str(result.inserted_id)
    
    async def get_attacks(self, run_id: str) -> List[AttackData]:
        """
        Get all attacks for a run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            List of AttackData instances
        """
        cursor = self.attacks.find({"run_id": run_id}).sort("index", 1)
        attack_docs = await cursor.to_list(length=None)
        
        return [AttackData(**doc.pop("_id", None) or doc) for doc in attack_docs]
    
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
        return str(result.inserted_id)
    
    async def get_defences(self, run_id: str) -> List[DefenceData]:
        """
        Get all defences for a run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            List of DefenceData instances
        """
        cursor = self.defences.find({"run_id": run_id}).sort("index", 1)
        defence_docs = await cursor.to_list(length=None)
        
        return [DefenceData(**doc.pop("_id", None) or doc) for doc in defence_docs]
    
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
        return str(result.inserted_id)
    
    async def get_evaluations(self, run_id: str) -> List[EvaluationData]:
        """
        Get all evaluations for a run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            List of EvaluationData instances
        """
        cursor = self.evaluations.find({"run_id": run_id}).sort("index", 1)
        eval_docs = await cursor.to_list(length=None)
        
        return [EvaluationData(**doc.pop("_id", None) or doc) for doc in eval_docs]

    # ========================================================================
    # Manual Session Operations
    # ========================================================================

    async def create_manual_session(
        self,
        run_id: str,
        name: str,
        description: str = "",
        initial_state_checkpoint: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new manual interaction session.

        Args:
            run_id: The ID of the parent run.
            name: A human-readable name for the session.
            description: Optional description for the session.
            initial_state_checkpoint: The initial LangGraph SystemState to save (optional).

        Returns:
            The newly created session_id.
        """
        session_id = f"sess_{uuid.uuid4().hex[:12]}"
        session_doc = {
            "session_id": session_id,
            "run_id": run_id,
            "name": name,
            "description": description,
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "turn_ids": [],
            "total_turns": 0,
            "state_checkpoint": initial_state_checkpoint  # Save initial state
        }
        await self.manual_sessions.insert_one(session_doc)
        return session_id
    
    async def get_manual_session(self, session_id: str) -> Optional[ManualSession]:
        """
        Get a manual session by its ID.
        """
        session_doc = await self.manual_sessions.find_one({"session_id": session_id})
        if session_doc:
            session_doc.pop("_id", None)
            return ManualSession(**session_doc)
        return None

    async def update_manual_session_state(
        self,
        session_id: str,
        run_id: str, # Added run_id for consistency/lookup
        state_checkpoint: SystemState,
        final_score: Optional[float] = None,
        best_score: Optional[float] = None
    ) -> bool:
        """
        Update the state checkpoint and final scores for a manual session.
        """
        updates = {
            "state_checkpoint": state_checkpoint,
            "updated_at": datetime.utcnow().isoformat()
        }
        if final_score is not None:
            updates["final_score"] = final_score
        if best_score is not None:
            updates["best_score"] = best_score
        
        result = await self.manual_sessions.update_one(
            {"session_id": session_id, "run_id": run_id},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    async def get_last_manual_turn_for_session(self, session_id: str) -> Optional[ManualTurn]:
        """
        Get the last manual turn for a given session, ordered by index.
        """
        turn_doc = await self.manual_turns.find(
            {"session_id": session_id}
        ).sort("index", -1).limit(1).to_list(length=1)
        
        if turn_doc:
            return ManualTurn(**turn_doc[0].pop("_id", None) or turn_doc[0])
        return None

    # ========================================================================
    # Manual Turn Operations
    # ========================================================================

    async def create_manual_turn(
        self,
        session_id: str,
        turn_id: str,
        run_id: str,
        index: int,
        turn_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new manual turn document.
        """
        manual_turn_doc = {
            "session_id": session_id,
            "run_id": run_id,
            "turn_id": turn_id,
            "index": index,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            # Fields for attack, defence, eval data IDs will be updated later
            "attack_data_id": None,
            "defence_data_id": None,
            "evaluation_data_id": None,
            "state_checkpoint": turn_data # Initially save the turn_data as a partial state
        }
        await self.manual_turns.insert_one(manual_turn_doc)
        
        # Add turn_id to the manual session's turn_ids list
        await self.manual_sessions.update_one(
            {"session_id": session_id},
            {"$push": {"turn_ids": turn_id}, "$inc": {"total_turns": 1}, "$set": {"updated_at": datetime.utcnow().isoformat()}}
        )
        return turn_id
    
    async def get_manual_turn(self, turn_id: str) -> Optional[ManualTurn]:
        """
        Get a manual turn by its ID.
        """
        turn_doc = await self.manual_turns.find_one({"turn_id": turn_id})
        if turn_doc:
            turn_doc.pop("_id", None)
            return ManualTurn(**turn_doc)
        return None

    async def get_manual_turns_for_session(self, session_id: str) -> List[ManualTurn]:
        """
        Get all manual turns for a given session, ordered by index.
        """
        cursor = self.manual_turns.find({"session_id": session_id}).sort("index", 1)
        turn_docs = await cursor.to_list(length=None)
        return [ManualTurn(**doc.pop("_id", None) or doc) for doc in turn_docs]
    
    async def update_manual_turn_data(
        self,
        session_id: str,
        turn_id: str,
        turn_index: int, # Explicitly pass turn_index to update/verify
        attack_prompt: Optional[str] = None,
        attack_metadata: Optional[Dict[str, Any]] = None,
        defence_response: Optional[str] = None,
        defence_status_code: Optional[int] = None,
        defence_was_blocked: Optional[bool] = None,
        defence_metadata: Optional[Dict[str, Any]] = None,
        evaluation_score: Optional[float] = None,
        evaluation_success: Optional[bool] = None,
        evaluation_category: Optional[str] = None,
        evaluation_feedback: Optional[str] = None,
        evaluation_metadata: Optional[Dict[str, Any]] = None,
        state_checkpoint: Optional[Dict[str, Any]] = None # Allow updating the turn's checkpoint
    ) -> bool:
        """
        Update data within an existing manual turn document.
        This method is designed to be called by middlewares or nodes as data becomes available.
        It also updates the corresponding AttackData, DefenceData, EvaluationData documents.
        """
        updates = {"updated_at": datetime.utcnow().isoformat()}
        
        # Update attack data and link to turn
        if attack_prompt is not None:
            attack_id = await self.save_attack(
                run_id=(await self.get_manual_session(session_id)).run_id, # Fetch run_id from session
                index=turn_index,
                turn_id=turn_id,
                prompt=attack_prompt,
                metadata=attack_metadata
            )
            updates["attack_data_id"] = attack_id

        # Update defence data and link to turn
        if defence_response is not None:
            defence_id = await self.save_defence(
                run_id=(await self.get_manual_session(session_id)).run_id,
                index=turn_index,
                turn_id=turn_id,
                response=defence_response,
                status_code=defence_status_code,
                was_blocked=defence_was_blocked,
                metadata=defence_metadata
            )
            updates["defence_data_id"] = defence_id

        # Update evaluation data and link to turn
        if evaluation_score is not None:
            evaluation_id = await self.save_evaluation(
                run_id=(await self.get_manual_session(session_id)).run_id,
                index=turn_index,
                turn_id=turn_id,
                score=evaluation_score,
                success=evaluation_success,
                category=evaluation_category,
                feedback=evaluation_feedback,
                metadata=evaluation_metadata
            )
            updates["evaluation_data_id"] = evaluation_id
            
        if state_checkpoint is not None:
            updates["state_checkpoint"] = state_checkpoint
            
        result = await self.manual_turns.update_one(
            {"session_id": session_id, "turn_id": turn_id},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    # ========================================================================
    # Convenience function
    # ========================================================================

# Convenience function
def get_db_ops(db: AsyncIOMotorDatabase) -> DatabaseOperations:
    """
    Create DatabaseOperations instance.
    
    Args:
        db: MongoDB database
    
    Returns:
        DatabaseOperations instance
    """
    return DatabaseOperations(db)
