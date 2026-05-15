"""
defenders/mock_defender.py

Mock Defender for Testing.

Returns hardcoded or scripted responses. Useful for:
  - Unit testing the pipeline without any external calls
  - Simulating a defender that always blocks (or always complies)
  - Scripting specific responses to specific turn numbers
"""

import logging
from src.core.interfaces import BaseDefender
from src.core.state import ArenaState

logger = logging.getLogger(__name__)


class MockDefender(BaseDefender):
    """
    A defender that returns scripted responses.

    Args:
        responses:  A list of strings. The defender returns them in order,
                    cycling when exhausted. If a single string is passed,
                    it's returned every time.
        always_block: If True, always returns a generic refusal message,
                      overriding `responses`.
    """

    def __init__(
        self,
        responses: list[str] | str | None = None,
        always_block: bool = False,
    ):
        if always_block:
            self._responses = ["I'm sorry, I can't help with that."]
        elif responses is None:
            self._responses = ["I'm just a mock defender. This is a test response."]
        elif isinstance(responses, str):
            self._responses = [responses]
        else:
            self._responses = responses

        self._index = 0

    def get_response(self, state: ArenaState) -> dict:
        response = self._responses[self._index % len(self._responses)]
        self._index += 1
        logger.info(f"MockDefender returning response {self._index}: {response[:60]}")
        return {"current_response": response}

    def setup(self, **kwargs) -> None:
        logger.info(f"MockDefender ready with {len(self._responses)} scripted response(s).")