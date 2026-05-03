"""
Server-Based Evaluation Node

Makes HTTP requests to an external evaluation service.
"""

from typing import Dict, Any, Optional
import httpx
from nodes.base import BaseAdversarialNode
from engine.domain_models import create_eval_result
from engine.state_schema import update_turn_data, SystemState
from datetime import datetime


class ServerEvalNode(BaseAdversarialNode):
    """
    Evaluation node that delegates to an external HTTP service.
    """
    
    def __init__(
        self,
        eval_server_url: str,
        api_key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        config: Dict[str, Any] = None
    ):
        super().__init__(config)
        self.eval_server_url = eval_server_url.rstrip('/')
        self.api_key = api_key
        self.default_headers = headers or {}
        
        if self.api_key:
            self.default_headers["Authorization"] = f"Bearer {self.api_key}"
        
        self._client = None
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.config.get("timeout", 30.0),
                follow_redirects=True
            )
        return self._client
    
    async def execute(self, state: SystemState, runtime_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate attack-defence interaction using external service.
        
        Args:
            state: Current system state
            runtime_config: Runtime configuration.
        
        Returns:
            Updated current_turn with evaluation result
        """
        current_turn = state.get("current_turn", {})
        attack = current_turn.get("attack")
        defence = current_turn.get("defence")
        
        if not attack or not defence:
            raise ValueError("Missing attack or defence payload in current_turn")
        
        eval_request = {
            "attack": {
                "prompt": attack.to_string(),
                "metadata": attack.metadata
            },
            "defence": {
                "response": defence.get_text(),
                "status_code": defence.status_code,
                "was_blocked": defence.was_blocked(),
                "metadata": defence.metadata
            },
            "run_context": {
                "run_id": state.get("run_id"),
                "turn_id": current_turn.get("turn_id"),
                "intent": state.get("initial_payload", {}).get("intent")
            }
        }
        
        try:
            client = self._get_client()
            endpoint = self.config.get("endpoint", "/evaluate")
            url = f"{self.eval_server_url}{endpoint}"
            
            response = await client.post(url, json=eval_request)
            response.raise_for_status()
            
            eval_data = response.json()
            
            adjusted_score = self._adjust_score(
                eval_data.get("score", 0.0),
                eval_data.get("success", False),
                defence.was_blocked()
            )
            
            eval_result = create_eval_result(
                score=adjusted_score,
                success=eval_data.get("success", False),
                category=eval_data.get("category", "unknown"),
                reasoning=eval_data.get("reasoning", ""),
                evaluator_model="external_server",
                server_url=url,
                response_time_ms=(response.elapsed.total_seconds() * 1000)
            )
            
        except httpx.TimeoutException:
            eval_result = create_eval_result(
                score=0.0,
                success=False,
                category="evaluation_timeout",
                reasoning="Evaluation service timed out",
                evaluator="fallback",
                error="timeout"
            )
            
        except httpx.HTTPStatusError as e:
            eval_result = create_eval_result(
                score=0.0,
                success=False,
                category="evaluation_error",
                reasoning=f"Evaluation service returned {e.response.status_code}",
                evaluator="fallback",
                error=str(e)
            )
            
        except Exception as e:
            eval_result = create_eval_result(
                score=0.0,
                success=False,
                category="evaluation_failed",
                reasoning=f"Evaluation failed: {str(e)}",
                evaluator="fallback",
                error=str(e)
            )
        
        updated_turn = update_turn_data(
            current_turn,
            evaluation=eval_result,
            node_name="eval"
        )
        
        return {"current_turn": updated_turn}
    
    def _adjust_score(self, score: float, success: bool, was_blocked: bool) -> float:
        """
        Adjust score based on strictness and defence status.
        """
        adjusted = score
        
        strictness = self.config.get("strictness", 0.5)
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
        
        return max(0.0, min(1.0, adjusted))


