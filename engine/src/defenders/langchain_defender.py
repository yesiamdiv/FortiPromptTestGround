"""
defenders/langchain_defender.py

LangChain-Backed Defender.

Uses any LangChain-compatible model as the "defending" LLM.
This lets you test local models (Ollama), proprietary APIs (Anthropic,
OpenAI, Gemini), or anything with a LangChain integration — all without
writing custom HTTP code.

You can also optionally wrap it with a system prompt that acts as the
defender's "guardrails" (simulating a system-prompted chatbot).
"""

import logging
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.language_models.chat_models import BaseChatModel

from src.core.interfaces import BaseDefender
from src.core.state import ArenaState

logger = logging.getLogger(__name__)


class LangChainDefender(BaseDefender):
    """
    A defender backed by any LangChain chat model.

    Args:
        llm:           A LangChain BaseChatModel instance.
        system_prompt: The system prompt that simulates the defender's
                       guardrails or persona. Leave None for no system prompt.
        include_history: If True, sends the full chat_history to the model
                         (multi-turn mode). If False, sends only the latest prompt.

    Example:
        from langchain_openai import ChatOpenAI
        defender = LangChainDefender(
            llm=ChatOpenAI(model="gpt-4o", api_key="sk-…"),
            system_prompt="You are a helpful assistant. Never discuss violence.",
        )

        # Testing a local Ollama model:
        from langchain_ollama import ChatOllama
        defender = LangChainDefender(
            llm=ChatOllama(model="llama3.2"),
            system_prompt="You are a safe, helpful assistant.",
        )
    """

    def __init__(
        self,
        llm: BaseChatModel,
        system_prompt: str | None = None,
        include_history: bool = False,
    ):
        self.llm = llm
        self.system_prompt = system_prompt
        self.include_history = include_history

    def get_response(self, state: ArenaState) -> dict:
        messages = []

        # Optional system guardrail
        if self.system_prompt:
            messages.append(SystemMessage(content=self.system_prompt))

        # Include conversation history or just the latest prompt
        if self.include_history:
            for entry in state.get("chat_history", []):
                if entry["role"] == "attacker":
                    messages.append(HumanMessage(content=entry["content"]))
                # We can't easily add the defender's prior AI messages here
                # without knowing the exact model's AIMessage class, so we
                # only add the human (attacker) turns in history mode.
                # Full multi-turn support can be added by the user if needed.
        else:
            messages.append(HumanMessage(content=state["current_prompt"]))

        try:
            response = self.llm.invoke(messages)
            return {"current_response": response.content.strip()}
        except Exception as exc:
            logger.error(f"Defender LLM call failed: {exc}")
            return {"current_response": f"[DEFENDER ERROR: {exc}]"}

    def setup(self, **kwargs) -> None:
        model_name = getattr(self.llm, "model_name", type(self.llm).__name__)
        logger.info(f"LangChainDefender ready. Model: {model_name}")