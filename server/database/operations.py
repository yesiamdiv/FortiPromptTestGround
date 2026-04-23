"""
Database Operations

CRUD operations for separate collections (attacks, defences, evaluations, runs).

This module contains the actual database logic that middlewares call.
"""

from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
from server.database.models_v2 import (
    RunModel,
    AttackData,
    DefenceData,
    EvaluationData,
    RunStatistics
)


class DatabaseOperations:
    """
    Database operations for adversarial testing data.
    
    Manages separate collections for runs, attacks, defences, and evaluations.
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
    
    # ========================================================================
    # Run Operations
    # ========================================================================
    
    async def create_run(self, run_data: Dict[str, Any]) -> str:
        """
        Create a new run document.
        
        Args:
            run_data: Run data dictionary
        
        Returns:
            run_id of created run
        """
        run_doc = {
            **run_data,
            "created_at": datetime.utcnow().isoformat(),
            "total_iterations": 0,
            "successful_iterations": 0
        }
        
        result = await self.runs.insert_one(run_doc)
        return run_data["run_id"]
    
    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Get run by ID.
        
        Args:
            run_id: Run identifier
        
        Returns:
            Run document or None
        """
        run = await self.runs.find_one({"run_id": run_id})
        if run:
            run.pop("_id", None)
        return run
    
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
    ) -> List[Dict[str, Any]]:
        """
        List runs with optional filtering.
        
        Args:
            status: Filter by status
            limit: Maximum number to return
            skip: Number to skip (pagination)
        
        Returns:
            List of run documents
        """
        query = {}
        if status:
            query["status"] = status
        
        cursor = self.runs.find(query).sort("created_at", -1).skip(skip).limit(limit)
        runs = await cursor.to_list(length=limit)
        
        for run in runs:
            run.pop("_id", None)
        
        return runs
    
    # ========================================================================
    # Attack Operations
    # ========================================================================
    
    async def save_attack(
        self,
        run_id: str,
        index: int,
        turn_id: str,
        prompt: str,
        metadata: Dict[str, Any] = None
    ) -> str:
        """
        Save attack to database.
        
        Args:
            run_id: Associated run ID
            index: Attack index/iteration number
            turn_id: Turn identifier
            prompt: Attack prompt text
            metadata: Additional metadata
        
        Returns:
            Inserted document ID
        """
        attack_doc = {
            "run_id": run_id,
            "index": index,
            "turn_id": turn_id,
            "prompt": prompt,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        result = await self.attacks.insert_one(attack_doc)
        
        # Update run iteration count
        await self.runs.update_one(
            {"run_id": run_id},
            {"$inc": {"total_iterations": 1}}
        )
        
        return str(result.inserted_id)
    
    async def get_attacks(self, run_id: str) -> List[Dict[str, Any]]:
        """
        Get all attacks for a run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            List of attack documents
        """
        cursor = self.attacks.find({"run_id": run_id}).sort("index", 1)
        attacks = await cursor.to_list(length=None)
        
        for attack in attacks:
            attack.pop("_id", None)
        
        return attacks
    
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
        metadata: Dict[str, Any] = None
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
            "timestamp": datetime.utcnow().isoformat()
        }
        
        result = await self.defences.insert_one(defence_doc)
        return str(result.inserted_id)
    
    async def get_defences(self, run_id: str) -> List[Dict[str, Any]]:
        """
        Get all defences for a run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            List of defence documents
        """
        cursor = self.defences.find({"run_id": run_id}).sort("index", 1)
        defences = await cursor.to_list(length=None)
        
        for defence in defences:
            defence.pop("_id", None)
        
        return defences
    
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
        metadata: Dict[str, Any] = None
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
            "timestamp": datetime.utcnow().isoformat()
        }
        
        result = await self.evaluations.insert_one(eval_doc)
        
        # Update run statistics
        if success:
            await self.runs.update_one(
                {"run_id": run_id},
                {"$inc": {"successful_iterations": 1}}
            )
        
        return str(result.inserted_id)
    
    async def get_evaluations(self, run_id: str) -> List[Dict[str, Any]]:
        """
        Get all evaluations for a run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            List of evaluation documents
        """
        cursor = self.evaluations.find({"run_id": run_id}).sort("index", 1)
        evals = await cursor.to_list(length=None)
        
        for eval_doc in evals:
            eval_doc.pop("_id", None)
        
        return evals
    
    # ========================================================================
    # Combined Operations
    # ========================================================================
    
    async def get_run_with_data(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Get run with all associated data.
        
        Args:
            run_id: Run identifier
        
        Returns:
            Dictionary with run, attacks, defences, evaluations
        """
        run = await self.get_run(run_id)
        if not run:
            return None
        
        attacks = await self.get_attacks(run_id)
        defences = await self.get_defences(run_id)
        evaluations = await self.get_evaluations(run_id)
        
        return {
            "run": run,
            "attacks": attacks,
            "defences": defences,
            "evaluations": evaluations
        }
    
    async def get_run_statistics(self, run_id: str) -> Optional[RunStatistics]:
        """
        Calculate statistics for a run.
        
        Args:
            run_id: Run identifier
        
        Returns:
            RunStatistics or None
        """
        run = await self.get_run(run_id)
        if not run:
            return None
        
        evaluations = await self.get_evaluations(run_id)
        defences = await self.get_defences(run_id)
        
        if not evaluations:
            return None
        
        scores = [e["score"] for e in evaluations]
        successes = [e["success"] for e in evaluations]
        categories = [e["category"] for e in evaluations]
        
        blocked_count = sum(1 for d in defences if d.get("was_blocked", False))
        
        return RunStatistics(
            run_id=run_id,
            total_attacks=len(evaluations),
            total_defences=len(defences),
            total_evaluations=len(evaluations),
            success_rate=sum(successes) / len(successes) if successes else 0.0,
            average_score=sum(scores) / len(scores) if scores else 0.0,
            best_score=max(scores) if scores else 0.0,
            worst_score=min(scores) if scores else 0.0,
            blocked_count=blocked_count,
            blocked_rate=blocked_count / len(defences) if defences else 0.0,
            categories={cat: categories.count(cat) for cat in set(categories)}
        )


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