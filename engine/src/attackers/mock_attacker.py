"""
attackers/mock_attacker.py

Dataset-Driven Mock Attacker.

Instead of calling an LLM, this attacker reads pre-written attack
payloads from a JSON file and iterates through them one by one.

Perfect for:
  - Running benchmark datasets (e.g. HarmBench, AdvBench)
  - Reproducible tests where you want fixed inputs
  - Testing the pipeline without burning LLM API credits
  - CI/CD smoke-testing

JSON file format:
    [
        {
            "prompt": "Ignore all previous instructions and…",
            "strategy": "direct_injection",   // optional label
            "notes": "Classic DAN variant"    // optional
        },
        …
    ]
Or a flat list of strings:
    [
        "Ignore all previous instructions and…",
        "Pretend you are DAN…"
    ]
"""

import json
import logging
from pathlib import Path

from src.core.interfaces import BaseAttacker
from src.core.state import ArenaState

logger = logging.getLogger(__name__)


class MockAttacker(BaseAttacker):
    """
    Iterates through a list of pre-written attack prompts.

    On each call to generate_attack(), it returns the next prompt in the list.
    When the list is exhausted it cycles back to the beginning.

    Args:
        source: Either a path to a JSON file (str or Path) or a Python list
                of prompt strings/dicts.
    """

    def __init__(self, source: str | Path | list):
        self._source = source
        self._prompts: list[str] = []
        self._index: int = 0

    def setup(self, **kwargs) -> None:
        if isinstance(self._source, (str, Path)):
            path = Path(self._source)
            logger.info(f"MockAttacker loading prompts from: {path}")
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        else:
            raw = self._source

        # Normalise to flat list of strings
        self._prompts = []
        for item in raw:
            if isinstance(item, str):
                self._prompts.append(item)
            elif isinstance(item, dict):
                self._prompts.append(item.get("prompt", str(item)))
            else:
                self._prompts.append(str(item))

        logger.info(f"MockAttacker loaded {len(self._prompts)} prompt(s).")
        self._index = 0

    def generate_attack(self, state: ArenaState) -> dict:
        if not self._prompts:
            raise RuntimeError("MockAttacker has no prompts loaded. Did you call setup()?")

        prompt = self._prompts[self._index % len(self._prompts)]
        logger.info(
            f"MockAttacker sending prompt {self._index + 1}/{len(self._prompts)}: "
            f"{prompt[:60]}{'…' if len(prompt) > 60 else ''}"
        )
        self._index += 1

        return {
            "current_prompt": prompt,
            "strategy_metadata": {
                "prompt_index": self._index,
                "source_type": "dataset",
            },
        }