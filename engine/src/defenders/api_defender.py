"""
defenders/api_defender.py

External API Defender.

The simplest, most common defender: forwards the attack prompt to any
HTTP endpoint and captures the JSON response. The endpoint could be:
  - An OpenAI / Anthropic / Gemini API
  - A company's internal AI gateway
  - A LiteLLM proxy
  - A LangServe deployment
  - Any custom REST service

The Orchestrator has zero awareness of what happens on that server.
"""

import logging
import requests

from src.core.interfaces import BaseDefender
from src.core.state import ArenaState

logger = logging.getLogger(__name__)

# Default timeout in seconds
DEFAULT_TIMEOUT = 30


class APIDefender(BaseDefender):
    """
    Forwards current_prompt to a user-specified HTTP endpoint via POST.

    Args:
        endpoint_url:   The full URL to POST the attack to.
        request_builder: Optional callable(state) -> dict that builds the
                         request body. Defaults to a generic OpenAI-style format.
        response_parser: Optional callable(response_json) -> str that extracts
                         the response text. Defaults to OpenAI-style parsing.
        headers:         Extra HTTP headers (e.g. {"Authorization": "Bearer …"}).
        timeout:         Request timeout in seconds.

    Example (OpenAI-compatible endpoint):
        defender = APIDefender(
            endpoint_url="https://api.openai.com/v1/chat/completions",
            headers={"Authorization": "Bearer sk-…"},
        )

    Example (custom endpoint):
        def my_builder(state):
            return {"input": state["current_prompt"], "session_id": "test"}

        def my_parser(data):
            return data["output"]["text"]

        defender = APIDefender(
            endpoint_url="https://my-company.ai/chat",
            request_builder=my_builder,
            response_parser=my_parser,
            headers={"X-API-Key": "secret"},
        )
    """

    def __init__(
        self,
        endpoint_url: str,
        request_builder=None,
        response_parser=None,
        headers: dict | None = None,
        timeout: int = DEFAULT_TIMEOUT,
        model: str = "gpt-4o-mini",
    ):
        self.endpoint_url = endpoint_url
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.timeout = timeout
        self.model = model
        self._request_builder = request_builder or self._default_request_builder
        self._response_parser = response_parser or self._default_response_parser

    # ── Default builders/parsers (OpenAI chat completions format) ─────────────

    def _default_request_builder(self, state: ArenaState) -> dict:
        """Build an OpenAI-style chat completion request."""
        return {
            "model": self.model,
            "messages": [
                {"role": "user", "content": state["current_prompt"]}
            ],
            "max_tokens": 1024,
        }

    def _default_response_parser(self, data: dict) -> str:
        """Parse an OpenAI-style chat completion response."""
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            # Fall back to raw JSON string if parsing fails
            import json
            return json.dumps(data)

    # ── Core logic ────────────────────────────────────────────────────────────

    def get_response(self, state: ArenaState) -> dict:
        body = self._request_builder(state)

        try:
            logger.debug(f"Posting to {self.endpoint_url}")
            resp = requests.post(
                self.endpoint_url,
                json=body,
                headers=self.headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            response_text = self._response_parser(data)

        except requests.exceptions.Timeout:
            logger.error("Defender endpoint timed out.")
            response_text = "[DEFENDER ERROR: Request timed out]"

        except requests.exceptions.HTTPError as exc:
            logger.error(f"Defender endpoint returned HTTP error: {exc}")
            response_text = f"[DEFENDER ERROR: HTTP {exc.response.status_code}]"

        except Exception as exc:
            logger.error(f"Defender request failed: {exc}")
            response_text = f"[DEFENDER ERROR: {exc}]"

        return {"current_response": response_text}

    def setup(self, **kwargs) -> None:
        logger.info(f"APIDefender configured → {self.endpoint_url}")