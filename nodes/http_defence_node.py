"""
================================================================================
HTTP DEFENCE NODE
================================================================================

DEVELOPER INSTRUCTIONS:
--------------------------------------------------------------------------------
1. Standalone Logic: This node acts as an agnostic webhook. It makes HTTP POST 
   requests to a target server, assuming the server handles its own model routing.
2. Initialization: Extracts `url` and optional `headers` from `self.config["node_params"]`.
3. State Deltas: Returns only state updates (the 'defence' object) via a dictionary.
4. Type Safety: Strict dictionary access for `SystemState`. No `.get()` on the root.
================================================================================
"""

from typing import Dict, Any
import httpx
from datetime import datetime
from nodes.base import BaseAdversarialNode
from engine.domain_models import create_defence_response, AttackPayload
from engine.state_schema import SystemState
from engine.debug_utils import debug, tracer, step, warn, err


class HTTPDefenceNode(BaseAdversarialNode):
    """
    Defence node that makes real HTTP API calls to an external target server.
    The external server is expected to handle model routing, auth, and execution.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        
        self.node_params = self.config["node_params"] if "node_params" in self.config else {}
        
        # We only care about where to send the payload
        self.url = self.node_params["url"] if "url" in self.node_params else ""
        self.default_headers = self.node_params["headers"] if "headers" in self.node_params else {}
        self.timeout = self.node_params["timeout"] if "timeout" in self.node_params else 30.0
        
        if not self.url:
            warn("HTTPDefenceNode initialized without a 'url' in node_params.")
        
        self._client = None
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client"""
        if self._client is None:
            debug("Creating new HTTP client", timeout=self.timeout)
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True
            )
        return self._client
        
    def _format_request(self, attack: AttackPayload) -> Dict[str, Any]:
        """Format a simple, agnostic HTTP payload."""
        # Just send the prompt. The target server handles the rest.
        return {"prompt": attack.to_string()}
    
    async def execute(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        """Sends the attack to the target system and captures the response."""
        if runtime_config is None: runtime_config = {}
        tracer("HTTPDefenceNode.execute")
        
        # STRICT STATE ACCESS
        if "current_turn" not in state:
            raise ValueError("Corrupted state: Missing 'current_turn'.")
            
        current_turn = state["current_turn"]
        attack = current_turn["attack"] if "attack" in current_turn else None
        
        if not attack:
            raise ValueError("No attack payload found in current_turn to send to HTTP defence.")
        
        # RUNTIME OVERRIDES (in case you want to switch URLs mid-run)
        active_url = runtime_config["url"] if "url" in runtime_config else self.url
        
        if not active_url:
            err("No URL provided for HTTPDefenceNode.")
            from engine.domain_models import create_defence_response
            error_defence = create_defence_response("No URL configured for target server", status_code=400)
            return {"current_turn": {"defence": error_defence, "node_name": self.name}}

        step("Sending request to target server", url=active_url)
        
        payload = self._format_request(attack)
        
        # Merge headers (runtime headers override static headers)
        headers = {**self.default_headers}
        if "headers" in runtime_config:
            headers.update(runtime_config["headers"])
        
        start_time = datetime.utcnow()
        
        try:
            client = self._get_client()
            
            response = await client.post(
                active_url,
                json=payload,
                headers=headers
            )
            
            end_time = datetime.utcnow()
            latency_ms = (end_time - start_time).total_seconds() * 1000
            
            defence = create_defence_response(
                text=response.text,
                status_code=response.status_code,
                headers=dict(response.headers),
                latency_ms=max(10, latency_ms),
                url=active_url,
                request_payload=payload
            )
            step("Got response from server", status=response.status_code, latency_ms=latency_ms)
            
        except httpx.TimeoutException as e:
            end_time = datetime.utcnow()
            latency_ms = (end_time - start_time).total_seconds() * 1000
            
            defence = create_defence_response(
                text=f"Request timeout: {str(e)}",
                status_code=408,
                headers={},
                latency_ms=latency_ms,
                error="timeout",
                url=active_url
            )
            debug("Request timeout", error=str(e))
            
        except httpx.RequestError as e:
            end_time = datetime.utcnow()
            latency_ms = (end_time - start_time).total_seconds() * 1000
            
            defence = create_defence_response(
                text=f"Request error: {str(e)}",
                status_code=500, 
                headers={},
                latency_ms=latency_ms,
                error=str(e),
                url=active_url
            )
            debug("Request error", error=str(e))
        
        # RETURN CLEAN DELTA
        return {
            "current_turn": {
                "defence": defence,
                "node_name": getattr(self, "name", "http_defence")
            }
        }
    
    async def cleanup(self):
        """Close the HTTP client"""
        if self._client:
            debug("Closing HTTP client")
            await self._client.aclose()
            self._client = None

    @classmethod
    def get_node_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL of the target server to test"
                },
                "headers": {
                    "type": "object",
                    "description": "Optional headers to include in the request (e.g., custom auth tokens)"
                },
                "timeout": {
                    "type": "number",
                    "description": "Request timeout in seconds",
                    "default": 30.0
                }
            },
            "required": ["url"]
        }