"""
redgen/engines/ollama_engine.py
────────────────────────────────
Simple wrapper around the `ollama` CLI for offline paraphrasing.

The class exposes the same ``paraphrase(text)`` interface as
``GroqEngine`` so that the rest of the codebase can remain engine‑agnostic.

Usage requires the `ollama` binary to be on PATH and a local model such as
``llama3.1:latest`` to be installed.  The engine will attempt to run a
very small prompt that includes the same system instruction used by the
Groq version.

Install ollama from https://ollama.ai and run ``ollama pull llama3.1:latest``
(or whatever model you want) beforehand.
"""

import subprocess
import time
from typing import Optional

# reuse the same system prompt from groq_engine so the two engines behave
# similarly.  importing would create a circular import, so just duplicate it
PARAPHRASE_SYSTEM = (
    "You are a text rewriter . "
    "Rewrite the given text to say the same thing with different wording. "
    "Keep the same intent and meaning. Output ONLY the rewritten text, "
    "no explanations, no preamble, no quotes."
)


class OllamaEngine:
    def __init__(
        self,
        model: str = "dolphin-mistral:7b-v2.6",
        timeout: float = 60.0,
        rpm_limit: int = 30,          # match Groq defaults
    ):
        self.model = model
        self.timeout = timeout

        # simple rate limiter in case someone does rapid-fire calls
        self._last_call_time = 0.0
        self._min_interval = 60.0 / rpm_limit

        # ensure the ollama binary is available
        try:
            _ = subprocess.run(["ollama", "version"], capture_output=True, text=True)
        except FileNotFoundError:
            raise ImportError(
                "`ollama` CLI not found on PATH. "
                "Install from https://ollama.ai and make sure the binary is reachable."
            )

        print(f"[OllamaEngine] Ready  model={self.model}")

    def _rate_limit(self):
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()

    async def paraphrase(self, text: str, retries: int = 3) -> Optional[str]:
        """Return a paraphrased version of ``text`` or ``None`` on failure."""

        # join the system prompt with the actual text so the model understands
        payload = PARAPHRASE_SYSTEM + "\n\n" + text

        for attempt in range(retries):
            try:
                self._rate_limit()
                proc = subprocess.run(
                    ["ollama", "run", self.model, "-"],
                    input=payload,
                    capture_output=True,
                    text=True,
                    encoding='utf-8', # Explicitly set encoding to UTF-8
                    errors='replace', # Replace undecodable characters
                    timeout=self.timeout,
                )

                if proc.returncode != 0:
                    raise RuntimeError(f"non-zero exit code: {proc.returncode} {proc.stderr}")

                result = proc.stdout.strip()
                if result:
                    return result
            except Exception as e:
                wait = 2 ** attempt
                print(
                    f"[OllamaEngine] Attempt {attempt+1} failed: {e}. "
                    f"Retrying in {wait}s..."
                )
                time.sleep(wait)
        return None
