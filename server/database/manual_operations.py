
"""
Manual Session Database Operations

CRUD operations for manual attack sessions and turns.
Ensures integration with the main database context.
"""

from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime
from server.database.manual_models import ManualSession, ManualTurn, ManualRunConfig
from server.run_manager import RunStatus # For status updates


class ManualSessionOperations:
    """Database operations for manual attack sessions"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.sessions = db.manual_sessions
        self.turns = db.manual_turns
        self.runs = db.runs # Access to the main runs collection
    
    # ========================================================================
    # Session Operations
    # ========================================================================
    
    async def create_session(
        self,
        run_id: str,
        session_id: str,
        name: str,
        description: str = "",
        defense_config: Dict[str, Any] = None,
        domain_notes: str = ""
    ) -> Dict[str, Any]:
        """Create a new manual session"""
        session_doc = {
            "session_id": session_id,
            "run_id": run_id,
            "name": name,
            "description": description,
            "status": "active",
            "turn_count": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "defense_config": defense_config or {},
            "domain_notes": domain_notes,
            "total_attacks": 0,
            "successful_attacks": 0,
            "average_score": None
        }
        
        await self.sessions.insert_one(session_doc)
        session_doc.pop("_id", None)
        return session_doc
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID"""
        session = await self.sessions.find_one({"session_id": session_id})
        if session:
            session.pop("_id", None)
        return session
    
    async def list_sessions(
        self,
        run_id: str,
        status: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List sessions for a run"""
        query = {"run_id": run_id}
        if status:
            query["status"] = status
        
        cursor = self.sessions.find(query).sort("created_at", -1).limit(limit)
        sessions = await cursor.to_list(length=limit)
        
        for session in sessions:
            session.pop("_id", None)
        
        return sessions
    
    async def update_session(
        self,
        session_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """Update session"""
        updates["updated_at"] = datetime.utcnow().isoformat()
        
        result = await self.sessions.update_one(
            {"session_id": session_id},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    async def save_session(self, session_id: str) -> bool:
        """Mark session as saved"""
        return await self.update_session(session_id, {
            "status": "saved",
            "saved_at": datetime.utcnow().isoformat()
        })
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete session and all its turns"""
        # Delete turns first
        await self.turns.delete_many({"session_id": session_id})
        
        # Delete session
        result = await self.sessions.delete_one({"session_id": session_id})
        return result.deleted_count > 0
    
    # ========================================================================
    # Turn Operations
    # ========================================================================
    
    async def add_turn(
        self,
        session_id: str,
        turn_id: str,
        turn_index: int,
        role: str,
        attack_prompt: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Add a new turn to session"""
        turn_doc = {
            "turn_id": turn_id,
            "session_id": session_id,
            "run_id": None, # Will be populated later if needed
            "turn_index": turn_index,
            "role": role,
            "attack_prompt": attack_prompt,
            "attack_timestamp": datetime.utcnow().isoformat(),
            "defense_response": None,
            "defense_status_code": None,
            "defense_was_blocked": None,
            "defense_timestamp": None,
            "eval_score": None,
            "eval_success": None,
            "eval_category": None,
            "eval_feedback": None,
            "eval_timestamp": None,
            "metadata": metadata or {}
        }
        
        await self.turns.insert_one(turn_doc)
        
        # Update session turn count and last updated time
        await self.sessions.update_one(
            {"session_id": session_id},
            {
                "$inc": {"turn_count": 1, "total_attacks": 1},
                "$set": {"updated_at": datetime.utcnow().isoformat()}
            }
        )
        
        turn_doc.pop("_id", None)
        return turn_doc
    
    async def update_turn_defense(
        self,
        turn_id: str,
        response: str,
        status_code: int,
        was_blocked: bool,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """Update turn with defense response"""
        updates = {
            "defense_response": response,
            "defense_status_code": status_code,
            "defense_was_blocked": was_blocked,
            "defense_timestamp": datetime.utcnow().isoformat()
        }
        
        if metadata:
            updates["metadata"] = metadata
        
        result = await self.turns.update_one(
            {"turn_id": turn_id},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    async def update_turn_evaluation(
        self,
        turn_id: str,
        score: float,
        success: bool,
        category: str,
        feedback: str,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """Update turn with evaluation"""
        updates = {
            "eval_score": score,
            "eval_success": success,
            "eval_category": category,
            "eval_feedback": feedback,
            "eval_timestamp": datetime.utcnow().isoformat()
        }
        
        if metadata:
            updates["metadata"] = metadata
        
        result = await self.turns.update_one(
            {"turn_id": turn_id},
            {"$set": updates}
        )
        
        # Update session statistics if the turn was modified
        if result.modified_count > 0:
            turn = await self.turns.find_one({"turn_id": turn_id})
            if turn:
                await self._update_session_stats(turn.get("session_id", None))
        
        return result.modified_count > 0
    
    async def get_session_turns(
        self,
        session_id: str,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """Get all turns for a session"""
        cursor = self.turns.find({"session_id": session_id}).sort("turn_index", 1).limit(limit)
        turns = await cursor.to_list(length=limit)
        
        for turn in turns:
            turn.pop("_id", None)
        
        return turns
    
    async def get_turn(self, turn_id: str) -> Optional[Dict[str, Any]]:
        """Get single turn"""
        turn = await self.turns.find_one({"turn_id": turn_id})
        if turn:
            turn.pop("_id", None)
        return turn
    
    # ========================================================================
    # Statistics
    # ========================================================================
    
    async def _update_session_stats(self, session_id: Optional[str]):
        """Recalculate session statistics"""
        if not session_id:
            return
        
        turns = await self.get_session_turns(session_id)
        
        evaluated_turns = [t for t in turns if t.get("eval_score") is not None]
        
        if evaluated_turns:
            avg_score = sum(t["eval_score"] for t in evaluated_turns) / len(evaluated_turns)
            successful = sum(1 for t in evaluated_turns if t.get("eval_success"))
            
            await self.update_session(session_id, {
                "average_score": avg_score,
                "successful_attacks": successful
            })
    
    async def get_manual_stats(self, run_id: str) -> Dict[str, Any]:
        """Get statistics for manual run"""
        sessions = await self.list_sessions(run_id)
        
        active_sessions = [s for s in sessions if s["status"] == "active"]
        saved_sessions = [s for s in sessions if s["status"] == "saved"]
        
        total_turns = sum(s.get("turn_count", 0) for s in sessions)
        total_successful = sum(s.get("successful_attacks", 0) for s in sessions)
        
        return {
            "run_id": run_id,
            "total_sessions": len(sessions),
            "active_sessions": len(active_sessions),
            "saved_sessions": len(saved_sessions),
            "total_turns": total_turns,
            "total_successful_attacks": total_successful,
            "success_rate": total_successful / total_turns if total_turns > 0 else 0
        }
    
    # ========================================================================
    # Run Config Operations
    # ========================================================================
    
    async def get_manual_config(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Get manual run configuration"""
        run = await self.runs.find_one({"run_id": run_id})
        if not run:
            return None
        
        return run.get("manual_config", {{}})
    
    async def update_manual_config(
        self,
        run_id: str,
        config: Dict[str, Any]
    ) -> bool:
        """Update manual run configuration"""
        result = await self.runs.update_one(
            {"run_id": run_id},
            {"$set": {"manual_config": config}}
        )
        return result.modified_count > 0


def get_manual_ops(db: AsyncIOMotorDatabase) -> ManualSessionOperations:
    """Get manual session operations instance"""
    return ManualSessionOperations(db)
