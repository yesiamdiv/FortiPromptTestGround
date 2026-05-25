"""
================================================================================
HTTP DEFENCE NODE
================================================================================

Sends the attack prompt to an external HTTP target server.
If the server allows the prompt through AND enable_llm_forwarding=True,
the prompt is forwarded to a configured LLM and the LLM's response is
recorded as the defence response for evaluation.
================================================================================
"""

from typing import Dict, Any
import httpx
from datetime import datetime
from nodes.base import BaseAdversarialNode
from nodes.llm_forwarding_mixin import LLMForwardingMixin
from engine.domain_models import create_defence_response, AttackPayload
from engine.state_schema import SystemState
from engine.debug_utils import debug, tracer, step, warn, err


class HTTPDefenceNode(LLMForwardingMixin, BaseAdversarialNode):
    """
    Defence node that makes real HTTP API calls to an external target server.
    Optionally forwards allowed prompts to an LLM for a real response.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)

        self.node_params = self.config.get("node_params", {})
        self.url = self.node_params.get("url", "")
        self.default_headers = self.node_params.get("headers", {})
        self.timeout = self.node_params.get("timeout", 30.0)

        if not self.url:
            warn("HTTPDefenceNode initialized without a 'url' in node_params.")

        # Initialise LLM forwarding (no-op if enable_llm_forwarding=False)
        self._init_llm_forwarding(self.node_params)

        self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)
        return self._client

    def _format_request(self, attack: AttackPayload) -> Dict[str, Any]:
        return {"prompt": attack.to_string()}

    async def execute(self, state: SystemState, runtime_config: Dict[str, Any] = None) -> Dict[str, Any]:
        if runtime_config is None:
            runtime_config = {}
        tracer("HTTPDefenceNode.execute")

        if "current_turn" not in state:
            raise ValueError("Corrupted state: Missing 'current_turn'.")

        current_turn = state["current_turn"]
        attack = current_turn.get("attack")

        if not attack:
            raise ValueError("No attack payload found in current_turn.")

        active_url = runtime_config.get("url", self.url)
        if not active_url:
            err("No URL provided for HTTPDefenceNode.")
            return {"current_turn": {
                "defence": create_defence_response("No URL configured", status_code=400),
                "node_name": self.name,
            }}

        step("Sending request to target server", url=active_url)
        payload = self._format_request(attack)
        headers = {**self.default_headers, **runtime_config.get("headers", {})}
        start_time = datetime.utcnow()

        try:
            response = await self._get_client().post(active_url, json=payload, headers=headers)
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            defence = create_defence_response(
                text=response.text,
                status_code=response.status_code,
                headers=dict(response.headers),
                latency_ms=max(10, latency_ms),
                url=active_url,
                request_payload=payload,
            )
            step("Got response from server", status=response.status_code, latency_ms=latency_ms)

        except httpx.TimeoutException as e:
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            defence = create_defence_response(
                text=f"Request timeout: {e}", status_code=408,
                latency_ms=latency_ms, error="timeout", url=active_url,
            )
        except httpx.RequestError as e:
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            defence = create_defence_response(
                text=f"Request error: {e}", status_code=500,
                latency_ms=latency_ms, error=str(e), url=active_url,
            )

        # Forward to LLM if allowed and toggled on
        defence = await self.maybe_forward_to_llm(defence, attack.to_string(), runtime_config)

        return {"current_turn": {"defence": defence, "node_name": self.name}}

    async def cleanup(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    @classmethod
    def get_node_schema(cls) -> Dict[str, Any]:
        props = {
            "url": {"type": "string", "description": "Full URL of the target server to test"},
            "headers": {"type": "object", "description": "Optional headers (e.g. auth tokens)"},
            "timeout": {"type": "number", "description": "Request timeout in seconds", "default": 30.0},
        }
        props.update(LLMForwardingMixin.llm_forwarding_schema_fragment())
        return {"type": "object", "properties": props, "required": ["url"]}
