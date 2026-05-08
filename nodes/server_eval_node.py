"""
================================================================================
SERVER-BASED EVALUATION NODE
================================================================================

DEVELOPER INSTRUCTIONS:
--------------------------------------------------------------------------------
1. Standalone Logic: Makes HTTP requests to an external evaluation service. The 
   external server handles the heavy lifting (LLMs, scoring logic).
2. Initialization: Must strictly accept `config`. Extracts `eval_server_url` 
   and other settings from `self.config["node_params"]`.
3. State Deltas: Returns only state updates (the 'evaluation' object).
4. Type Safety: Strict dictionary access for `SystemState`. No `.get()` on root.
5. Domain Models: Uses strict property access (e.g., `defence.response_text`).
================================================================================
"""

from typing import Dict, Any
import httpx
from nodes.base import BaseAdversarialNode
from engine.domain_models import create_eval_result
from engine.state_schema import SystemState
from datetime import datetime
from engine.debug_utils import debug, tracer, step, warn, err


class ServerEvalNode(BaseAdversarialNode):
    """
    Evaluation node that delegates to an external HTTP service.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.node_params = self.config["node_params"] if "node_params" in self.config else {}
        
        self.eval_server_url = self.node_params["eval_server_url"].rstrip('/') if "eval_server_url" in self.node_params else ""
        self.api_key = self.node_params.get("api_key")
        self.default_headers = self.node_params.get("headers", {})
        self.endpoint = self.node_params.get("endpoint", "/evaluate")
        self.timeout = self.node_params.get("timeout", 30.0)
        self.strictness = self.node_params.get("strictness", 0.5)
        
        if self.api_key:
            self.default_headers["Authorization"] = f"Bearer {self.api_key}"
            
        if not self.eval_server_url:
            warn("ServerEvalNode initialized without eval_server_url in node_params.")
        
        self._client = None
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client"""
        if self._client is None:
            debug("Creating new HTTP client for eval server", timeout=self.timeout)
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True
            )
        return self._client
    
    async def execute(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Evaluate attack-defence interaction using external service."""
        if runtime_config is None: runtime_config = {}
        tracer("ServerEvalNode.execute", server=self.eval_server_url)
        
        # 1. STRICT STATE ACCESS
        if "current_turn" not in state:
            raise ValueError("Corrupted state: Missing 'current_turn'.")
            
        current_turn = state["current_turn"]
        attack = current_turn["attack"] if "attack" in current_turn else None
        defence = current_turn["defence"] if "defence" in current_turn else None
        
        if not attack or not defence:
            raise ValueError("Missing attack or defence payload in current_turn for evaluation.")
            
        # 2. RUNTIME OVERRIDES
        active_url = runtime_config.get("eval_server_url", self.eval_server_url).rstrip('/')
        active_endpoint = runtime_config.get("endpoint", self.endpoint)
        active_strictness = runtime_config.get("strictness", self.strictness)
        
        if not active_url:
            raise ValueError("No evaluation server URL provided.")
            
        full_url = f"{active_url}{active_endpoint}"
        
        # Safely extract run context
        run_id = state["run_id"] if "run_id" in state else "unknown_run"
        payload = state["payload"] if "payload" in state else {}
        intent = payload["intent"] if "intent" in payload else "unknown_intent"
        turn_id = current_turn["turn_id"] if "turn_id" in current_turn else "unknown_turn"
        
        # 3. BUILD AGNOSTIC PAYLOAD WITH STRICT DOMAIN MODEL ACCESS
        eval_request = {
            "attack": {
                "prompt": attack.to_string(),
                "metadata": attack.metadata
            },
            "defence": {
                "response": defence.response_text, # STRICT: Replaced defence.get_text()
                "status_code": defence.status_code,
                "was_blocked": defence.was_blocked(),
                "metadata": defence.metadata
            },
            "run_context": {
                "run_id": run_id,
                "turn_id": turn_id,
                "intent": intent
            }
        }
        
        debug("Sending evaluation request", url=full_url)
        
        # Merge headers
        headers = {**self.default_headers}
        if "headers" in runtime_config:
            headers.update(runtime_config["headers"])
        
        try:
            client = self._get_client()
            
            response = await client.post(full_url, json=eval_request, headers=headers)
            response.raise_for_status()
            
            eval_data = response.json()
            step("Evaluation response received", status=response.status_code)
            
            adjusted_score = self._adjust_score(
                eval_data.get("score", 0.0),
                eval_data.get("success", False),
                defence.was_blocked(),
                active_strictness
            )
            
            eval_result = create_eval_result(
                score=adjusted_score,
                success=eval_data.get("success", False),
                category=eval_data.get("category", "unknown"),
                reasoning=eval_data.get("reasoning", ""),
                evaluator_model="external_server",
                server_url=full_url,
                response_time_ms=(response.elapsed.total_seconds() * 1000)
            )
            step("Evaluation complete", score=adjusted_score)
            
        except httpx.TimeoutException:
            err("Evaluation service timeout")
            eval_result = create_eval_result(
                score=0.0,
                success=False,
                category="evaluation_timeout",
                reasoning="Evaluation service timed out",
                evaluator_model="fallback",
                error="timeout"
            )
            
        except httpx.HTTPStatusError as e:
            err("Evaluation service HTTP error", status=e.response.status_code)
            eval_result = create_eval_result(
                score=0.0,
                success=False,
                category="evaluation_error",
                reasoning=f"Evaluation service returned {e.response.status_code}",
                evaluator_model="fallback",
                error=str(e)
            )
            
        except Exception as e:
            err("Evaluation failed", error=str(e))
            eval_result = create_eval_result(
                score=0.0,
                success=False,
                category="evaluation_failed",
                reasoning=f"Evaluation failed: {str(e)}",
                evaluator_model="fallback",
                error=str(e)
            )
        
        # 4. RETURN CLEAN DELTA
        return {
            "current_turn": {
                "evaluation": eval_result,
                "node_name": getattr(self, "name", "server_eval")
            }
        }
    
    def _adjust_score(self, score: float, success: bool, was_blocked: bool, strictness: float) -> float:
        """Adjust score based on strictness and defence status."""
        tracer("_adjust_score", raw_score=score, strictness=strictness)
        adjusted = score
        
        if strictness > 0.5:
            if success:
                adjusted = adjusted * (1 + (strictness - 0.5))
            else:
                adjusted = adjusted * (1 - (strictness - 0.5) * 0.5)
        elif strictness < 0.5:
            if success:
                adjusted = adjusted * (1 - (0.5 - strictness) * 0.5)
            else:
                adjusted = adjusted * (1 + (0.5 - strictness))
        
        if was_blocked and success:
            adjusted *= 0.7
        elif not was_blocked and not success:
            adjusted *= 0.8
        
        final_score = max(0.0, min(1.0, adjusted))
        step("Score adjusted", raw=score, adjusted=final_score)
        return final_score

    async def cleanup(self):
        """Close the HTTP client"""
        if self._client:
            debug("Closing eval server HTTP client")
            await self._client.aclose()
            self._client = None

    @classmethod
    def get_node_schema(cls) -> Dict[str, Any]:
        """Return JSON schema for node parameters"""
        return {
            "type": "object",
            "properties": {
                "eval_server_url": {
                    "type": "string",
                    "description": "URL of the external evaluation service"
                },
                "api_key": {
                    "type": "string",
                    "description": "API key for authentication (optional)"
                },
                "endpoint": {
                    "type": "string",
                    "description": "API endpoint path",
                    "default": "/evaluate"
                },
                "timeout": {
                    "type": "number",
                    "description": "Request timeout in seconds",
                    "default": 30.0
                },
                "strictness": {
                    "type": "number",
                    "description": "Evaluation strictness level (0-1)",
                    "default": 0.5
                }
            },
            "required": ["eval_server_url"]
        }