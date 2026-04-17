"""Logging Middleware"""

from typing import Dict, Any
from datetime import datetime
from middlewares.base import BaseMiddleware


class LoggingMiddleware(BaseMiddleware):
    """Console logging middleware for observing execution flow"""
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {"verbose": False, "timestamps": True}
        if config:
            default_config.update(config)
        super().__init__(default_config)
        self.run_timings: Dict[str, float] = {}
    
    async def before_run(self, initial_state, config, run_id):
        self.run_timings[run_id] = datetime.utcnow().timestamp()
        strategy_name = config["configurable"]["strategy"].name
        intent = initial_state.get("initial_payload", {}).get("intent", "unknown")
        
        self._log(f"\n{'='*60}")
        self._log(f"🚀 RUN STARTED: {run_id}")
        self._log(f"   Strategy: {strategy_name}")
        self._log(f"   Intent: {intent}")
        self._log(f"{'='*60}\n")
    
    async def after_step(self, step_data, run_id):
        if not step_data:
            return
        
        node_name = list(step_data.keys())[0]
        node_output = step_data[node_name]
        
        self._log(f"📍 NODE: {node_name}")
        
        if "current_turn" in node_output:
            turn = node_output["current_turn"]
            
            if turn.get("attack"):
                attack = turn["attack"]
                preview = attack.to_string()[:100]
                self._log(f"   ⚔️  Attack: {preview}...")
            
            if turn.get("defence"):
                defence = turn["defence"]
                blocked = "🚫 BLOCKED" if defence.was_blocked() else "✅ ALLOWED"
                self._log(f"   🛡️  Defence: {blocked}")
            
            if turn.get("evaluation"):
                eval_result = turn["evaluation"]
                self._log(f"   📊 Eval: {eval_result.to_summary()}")
        
        if "routing_signal" in node_output:
            signal = node_output["routing_signal"]
            self._log(f"   🔀 Routing: {signal}")
        
        self._log("")
    
    async def after_run(self, final_state, run_id):
        if run_id in self.run_timings:
            elapsed = datetime.utcnow().timestamp() - self.run_timings[run_id]
            del self.run_timings[run_id]
        else:
            elapsed = 0
        
        self._log(f"\n{'='*60}")
        self._log(f"🏁 RUN COMPLETED: {run_id}")
        self._log(f"   Duration: {elapsed:.2f}s")
        
        if final_state.get("current_turn", {}).get("evaluation"):
            eval_result = final_state["current_turn"]["evaluation"]
            self._log(f"   Final Result: {eval_result.to_summary()}")
        
        self._log(f"{'='*60}\n")
    
    async def on_error(self, error, run_id, step_data=None):
        self._log(f"\n❌ ERROR in {run_id}: {type(error).__name__}")
        self._log(f"   Message: {str(error)}\n")
    
    def _log(self, message: str):
        if self.config.get("timestamps"):
            timestamp = datetime.utcnow().strftime("%H:%M:%S.%f")[:-3]
            print(f"[{timestamp}] {message}")
        else:
            print(message)
