"""
Production Defence Node

Makes actual HTTP requests to external target systems.
"""

from typing import Dict, Any, Optional
import httpx
from datetime import datetime
from nodes.base import BaseAdversarialNode
from engine.domain_models import create_defence_response
from engine.state_schema import update_turn_data, SystemState


class HTTPDefenceNode(BaseAdversarialNode):
    """
    Defence node that makes real HTTP API calls to target systems.
    """
    
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        config: Dict[str, Any] = None
    ):
        super().__init__(config)
        self.base_url = base_url.rstrip('/')
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
        Send attack to target system and capture response.
        
        Args:
            state: Current system state
            runtime_config: Runtime configuration.
        
        Returns:
            Updated current_turn with defence payload
        """
        current_turn = state.get("current_turn", {})
        attack = current_turn.get("attack")
        
        if not attack:
            raise ValueError("No attack payload found in current_turn")
        
        # Get endpoint from config or use default
        endpoint = self.config.get("endpoint", "/chat")
        url = f"{self.base_url}{endpoint}"
        
        # Prepare request payload
        payload = self._format_request(attack, state)
        
        # Merge headers
        headers = {**self.default_headers}
        if "headers" in self.config:
            headers.update(self.config["headers"])
        
        # Make request with timing
        start_time = datetime.utcnow()
        
        try:
            client = self._get_client()
            
            response = await client.post(
                url,
                json=payload,
                headers=headers
            )
            
            end_time = datetime.utcnow()
            latency_ms = (end_time - start_time).total_seconds() * 1000
            
            defence = create_defence_response(
                text=response.text,
                status_code=response.status_code,
                headers=dict(response.headers),
                latency_ms=latency_ms,
                url=url,
                request_payload=payload
            )
            
        except httpx.TimeoutException as e:
            end_time = datetime.utcnow()
            latency_ms = (end_time - start_time).total_seconds() * 1000
            
            defence = create_defence_response(
                text=f"Request timeout: {str(e)}",
                status_code=408,
                headers={},
                latency_ms=latency_ms,
                error="timeout",
                url=url
            )
            
        except httpx.RequestError as e:
            end_time = datetime.utcnow()
            latency_ms = (end_time - start_time).total_seconds() * 1000
            
            defence = create_defence_response(
                text=f"Request error: {str(e)}",
                status_code=0,
                headers={},
                latency_ms=latency_ms,
                error=str(e),
                url=url
            )
        
        # Update turn data
        updated_turn = update_turn_data(
            current_turn,
            defence=defence,
            node_name="defence"
        )
        
        return {"current_turn": updated_turn}
    
    async def cleanup(self):
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
        

class OpenAIDefenceNode(HTTPDefenceNode):
    """
    Specialized defence node for OpenAI API format.
    """
    
    def __init__(self, api_key: str, model: str = "gpt-3.5-turbo", config: Dict[str, Any] = None):
        super().__init__(
            base_url="https://api.openai.com/v1",
            api_key=api_key,
            config=config
        )
        self.model = model
    
    def _format_request(self, attack, state: Dict[str, Any]) -> Dict[str, Any]:
        """Format for OpenAI chat completions API"""
        return {
            "model": self.model,
            "messages": attack.to_messages(),
            "temperature": 0.7,
            "max_tokens": 500
        }
