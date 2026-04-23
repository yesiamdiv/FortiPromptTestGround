"""
Database Migration Script

Migrates from old schema (embedded data in runs) to new schema (separate collections).

OLD SCHEMA:
- runs collection with embedded attack/defence/evaluation data
- steps collection with all step data

NEW SCHEMA:
- runs collection with metadata only
- attacks collection (one doc per attack)
- defences collection (one doc per defence)
- evaluations collection (one doc per evaluation)
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
import argparse


class DatabaseMigration:
    """Handles migration from old schema to new schema"""
    
    def __init__(self, mongo_url: str, database_name: str):
        """
        Initialize migration.
        
        Args:
            mongo_url: MongoDB connection string
            database_name: Database name
        """
        self.client = AsyncIOMotorClient(mongo_url)
        self.db = self.client[database_name]
        
        self.stats = {
            "runs_migrated": 0,
            "attacks_created": 0,
            "defences_created": 0,
            "evaluations_created": 0,
            "errors": []
        }
    
    async def migrate(self, dry_run: bool = False):
        """
        Run migration.
        
        Args:
            dry_run: If True, only show what would be done
        """
        print("\n" + "="*70)
        print("DATABASE MIGRATION: Old Schema → New Schema")
        print("="*70 + "\n")
        
        if dry_run:
            print("🔍 DRY RUN MODE - No changes will be made\n")
        
        # Get all runs from old schema
        runs = await self.db.runs.find({}).to_list(length=None)
        total_runs = len(runs)
        
        print(f"Found {total_runs} runs to migrate\n")
        
        for i, run in enumerate(runs, 1):
            print(f"[{i}/{total_runs}] Migrating run: {run.get('run_id', 'unknown')}")
            
            try:
                if not dry_run:
                    await self._migrate_run(run)
                else:
                    await self._analyze_run(run)
                
                self.stats["runs_migrated"] += 1
                
            except Exception as e:
                error_msg = f"Error migrating run {run.get('run_id')}: {e}"
                print(f"  ❌ {error_msg}")
                self.stats["errors"].append(error_msg)
        
        # Print summary
        print("\n" + "="*70)
        print("MIGRATION SUMMARY")
        print("="*70)
        print(f"Runs migrated: {self.stats['runs_migrated']}")
        print(f"Attacks created: {self.stats['attacks_created']}")
        print(f"Defences created: {self.stats['defences_created']}")
        print(f"Evaluations created: {self.stats['evaluations_created']}")
        print(f"Errors: {len(self.stats['errors'])}")
        
        if self.stats['errors']:
            print("\nErrors encountered:")
            for error in self.stats['errors']:
                print(f"  - {error}")
        
        print("\n")
    
    async def _migrate_run(self, old_run):
        """Migrate a single run"""
        run_id = old_run["run_id"]
        
        # 1. Create new run document (metadata only)
        new_run = {
            "run_id": run_id,
            "name": old_run.get("name", f"Run {run_id[:8]}"),
            "status": old_run.get("status", "completed"),
            "description": old_run.get("description", ""),
            "strategy": old_run.get("strategy", "unknown"),
            "components": old_run.get("components", []),
            "config": old_run.get("config", {}),
            "created_at": old_run.get("created_at", datetime.utcnow().isoformat()),
            "started_at": old_run.get("started_at"),
            "completed_at": old_run.get("completed_at"),
            "total_iterations": 0,
            "successful_iterations": 0,
            "final_score": old_run.get("final_score"),
            "best_score": old_run.get("best_score"),
            "intent": old_run.get("intent", "unknown"),
            "target": old_run.get("target"),
            "user_id": old_run.get("user_id"),
            "session_id": old_run.get("session_id"),
            "tags": old_run.get("tags", []),
            "error": old_run.get("error")
        }
        
        # Update or insert run
        await self.db.runs.update_one(
            {"run_id": run_id},
            {"$set": new_run},
            upsert=True
        )
        
        # 2. Migrate embedded data if present
        if "attack_data" in old_run:
            for attack in old_run["attack_data"]:
                await self._create_attack(run_id, attack)
        
        if "defense_data" in old_run:
            for defence in old_run["defense_data"]:
                await self._create_defence(run_id, defence)
        
        if "evaluation_data" in old_run:
            for evaluation in old_run["evaluation_data"]:
                await self._create_evaluation(run_id, evaluation)
        
        # 3. Migrate from steps collection if exists
        steps = await self.db.steps.find({"run_id": run_id}).to_list(length=None)
        for step in steps:
            if "attack" in step:
                await self._create_attack_from_step(run_id, step)
            
            if "defence" in step:
                await self._create_defence_from_step(run_id, step)
            
            if "evaluation" in step:
                await self._create_evaluation_from_step(run_id, step)
        
        print(f"  ✅ Migrated run {run_id}")
    
    async def _create_attack(self, run_id, attack_data):
        """Create attack document in new schema"""
        attack_doc = {
            "run_id": run_id,
            "index": attack_data.get("index", 0),
            "turn_id": f"turn_{attack_data.get('index', 0)}",
            "prompt": attack_data.get("prompt", ""),
            "metadata": attack_data.get("metadata", {}),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Check if already exists
        existing = await self.db.attacks.find_one({
            "run_id": run_id,
            "index": attack_doc["index"]
        })
        
        if not existing:
            await self.db.attacks.insert_one(attack_doc)
            self.stats["attacks_created"] += 1
    
    async def _create_defence(self, run_id, defence_data):
        """Create defence document in new schema"""
        defence_doc = {
            "run_id": run_id,
            "index": defence_data.get("index", 0),
            "turn_id": f"turn_{defence_data.get('index', 0)}",
            "response": defence_data.get("response", ""),
            "status_code": 200,
            "was_blocked": False,
            "metadata": defence_data.get("metadata", {}),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        existing = await self.db.defences.find_one({
            "run_id": run_id,
            "index": defence_doc["index"]
        })
        
        if not existing:
            await self.db.defences.insert_one(defence_doc)
            self.stats["defences_created"] += 1
    
    async def _create_evaluation(self, run_id, eval_data):
        """Create evaluation document in new schema"""
        eval_doc = {
            "run_id": run_id,
            "index": eval_data.get("index", 0),
            "turn_id": f"turn_{eval_data.get('index', 0)}",
            "score": eval_data.get("score", 0.0),
            "success": False,
            "category": "unknown",
            "feedback": eval_data.get("feedback"),
            "metadata": {},
            "timestamp": datetime.utcnow().isoformat()
        }
        
        existing = await self.db.evaluations.find_one({
            "run_id": run_id,
            "index": eval_doc["index"]
        })
        
        if not existing:
            await self.db.evaluations.insert_one(eval_doc)
            self.stats["evaluations_created"] += 1
    
    async def _create_attack_from_step(self, run_id, step):
        """Create attack from step document"""
        attack_data = step.get("attack", {})
        if isinstance(attack_data, dict) and "data" in attack_data:
            prompt = attack_data.get("data", "")
        else:
            prompt = str(attack_data)
        
        await self._create_attack(run_id, {
            "index": 0,  # Would need better indexing
            "prompt": prompt,
            "metadata": attack_data.get("metadata", {}) if isinstance(attack_data, dict) else {}
        })
    
    async def _create_defence_from_step(self, run_id, step):
        """Create defence from step document"""
        defence_data = step.get("defence", {})
        
        await self._create_defence(run_id, {
            "index": 0,
            "response": str(defence_data),
            "metadata": {}
        })
    
    async def _create_evaluation_from_step(self, run_id, step):
        """Create evaluation from step document"""
        eval_data = step.get("evaluation", {})
        
        await self._create_evaluation(run_id, {
            "index": 0,
            "score": eval_data.get("score", 0.0) if isinstance(eval_data, dict) else 0.0,
            "feedback": eval_data.get("feedback") if isinstance(eval_data, dict) else None
        })
    
    async def _analyze_run(self, old_run):
        """Analyze a run without migrating (dry run)"""
        run_id = old_run["run_id"]
        
        attack_count = len(old_run.get("attack_data", []))
        defence_count = len(old_run.get("defense_data", []))
        eval_count = len(old_run.get("evaluation_data", []))
        
        # Check steps
        steps = await self.db.steps.find({"run_id": run_id}).to_list(length=None)
        step_count = len(steps)
        
        print(f"  📊 Would migrate:")
        print(f"     - Attacks: {attack_count}")
        print(f"     - Defences: {defence_count}")
        print(f"     - Evaluations: {eval_count}")
        print(f"     - Steps: {step_count}")
    
    async def create_indexes(self):
        """Create indexes on new collections"""
        print("\nCreating indexes...")
        
        # Attacks
        await self.db.attacks.create_index([("run_id", 1), ("index", 1)])
        await self.db.attacks.create_index("run_id")
        
        # Defences
        await self.db.defences.create_index([("run_id", 1), ("index", 1)])
        await self.db.defences.create_index("run_id")
        
        # Evaluations
        await self.db.evaluations.create_index([("run_id", 1), ("index", 1)])
        await self.db.evaluations.create_index("run_id")
        await self.db.evaluations.create_index("score")
        
        print("✅ Indexes created")
    
    async def close(self):
        """Close database connection"""
        self.client.close()


async def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description="Migrate database to new schema")
    parser.add_argument("--mongo-url", default="mongodb://localhost:27017")
    parser.add_argument("--database", default="adversarial_testing")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    parser.add_argument("--create-indexes", action="store_true", help="Create indexes on new collections")
    
    args = parser.parse_args()
    
    migration = DatabaseMigration(args.mongo_url, args.database)
    
    try:
        await migration.migrate(dry_run=args.dry_run)
        
        if args.create_indexes and not args.dry_run:
            await migration.create_indexes()
        
    finally:
        await migration.close()


if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════════════════╗
    ║  Database Migration Tool                                         ║
    ║  Migrates from old schema to new schema (separate collections)   ║
    ╚══════════════════════════════════════════════════════════════════╝
    """)
    
    asyncio.run(main())