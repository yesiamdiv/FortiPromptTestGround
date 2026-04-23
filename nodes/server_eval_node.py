"""
Server-Based Evaluation Node

Makes HTTP requests to an external evaluation service.
Useful when evaluation logic is complex or hosted separately.
"""

from typing import Dict, Any, Optional
import httpx
from nodes.base import BaseAdversarialNode
from engine.domain_models import create_eval_result
from engine.state_schema import update_turn_data


class ServerEvalNode(BaseAdversarialNode):
    """
    Evaluation node that delegates to an external HTTP service.
    
    The evaluation server receives attack and defence data,
    processes it using custom logic, and returns evaluation results.
    """
    
    def __init__(
        self,
        eval_server_url: str,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        config: Dict[str, Any] = None
    ):
        """
        Initialize with evaluation server details.
        
        Args:
            eval_server_url: Base URL of evaluation service
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
            config: Additional configuration
        """
        super().__init__(config)
        self.eval_server_url = eval_server_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self._client = None
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client"""
        if self._client is None:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                headers=headers
            )
        return self._client
    
    async def execute(self, state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate attack-defence interaction using external service.
        
        Sends:
        - Attack prompt
        - Defence response
        - Metadata
        
        Receives:
        - Score (0.0-1.0)
        - Success boolean
        - Category
        - Reasoning/feedback
        
        Args:
            state: Current system state
            config: Runtime configuration
        
        Returns:
            Updated current_turn with evaluation result
        """
        current_turn = state.get("current_turn", {})
        attack = current_turn.get("attack")
        defence = current_turn.get("defence")
        
        if not attack or not defence:
            raise ValueError("Missing attack or defence payload in current_turn")
        
        # Build evaluation request payload
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
            # Call evaluation service
            client = self._get_client()
            
            endpoint = self.config.get("endpoint", "/evaluate")
            url = f"{self.eval_server_url}{endpoint}"
            
            response = await client.post(url, json=eval_request)
            response.raise_for_status()
            
            # Parse response
            eval_data = response.json()
            
            # Create evaluation result
            eval_result = create_eval_result(
                score=eval_data.get("score", 0.0),
                success=eval_data.get("success", False),
                category=eval_data.get("category", "unknown"),
                reasoning=eval_data.get("reasoning", ""),
                evaluator="external_server",
                server_url=url,
                response_time_ms=(response.elapsed.total_seconds() * 1000)
            )
            
        except httpx.TimeoutException:
            # Fallback on timeout
            eval_result = create_eval_result(
                score=0.0,
                success=False,
                category="evaluation_timeout",
                reasoning="Evaluation service timed out",
                evaluator="fallback",
                error="timeout"
            )
            
        except httpx.HTTPStatusError as e:
            # Fallback on HTTP error
            eval_result = create_eval_result(
                score=0.0,
                success=False,
                category="evaluation_error",
                reasoning=f"Evaluation service returned {e.response.status_code}",
                evaluator="fallback",
                error=str(e)
            )
            
        except Exception as e:
            # Fallback on any other error
            eval_result = create_eval_result(
                score=0.0,
                success=False,
                category="evaluation_failed",
                reasoning=f"Evaluation failed: {str(e)}",
                evaluator="fallback",
                error=str(e)
            )
        
        # Update turn data
        updated_turn = update_turn_data(
            current_turn,
            evaluation=eval_result,
            node_name="eval"
        )
        
        return {"current_turn": updated_turn}
    
    async def cleanup(self):
        """Close HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None


# Example evaluation server specification
EVAL_SERVER_API_SPEC = """
# Evaluation Server API Specification

## POST /evaluate

Request:
{
    "attack": {
        "prompt": "string",
        "metadata": {}
    },
    "defence": {
        "response": "string",
        "status_code": 200,
        "was_blocked": false,
        "metadata": {}
    },
    "run_context": {
        "run_id": "string",
        "turn_id": "string",
        "intent": "string"
    }
}

Response:
{
    "score": 0.75,  // float 0.0-1.0
    "success": true,  // boolean
    "category": "jailbreak_successful",  // string
    "reasoning": "Detailed explanation...",  // string
    "metadata": {}  // optional additional data
}

Status Codes:
- 200: Success
- 400: Invalid request
- 500: Server error
- 503: Service unavailable
"""