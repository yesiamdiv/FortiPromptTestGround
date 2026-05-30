"""
Registry for LLM Providers
"""

from typing import Dict, Any, Callable, Type

# Import base provider classes and specific provider implementations
from providers.base import BaseLLMProvider
from providers.ollama_provider import OllamaProvider
from providers.gemini_provider import GeminiProvider
# from providers.openai_provider import OpenAIProvider
from core.logging import tracer, step, debug, warn, err


ProviderFactory = Callable[..., Any]

class ProviderRegistry:
    """Manages a registry of LLM provider factories."""
    def __init__(self):
        self._registry: Dict[str, Type[BaseLLMProvider]] = {}

    def register(self, name: str, provider_class: Type[BaseLLMProvider]):
        """Register a provider class."""
        if name in self._registry:
            warn(f"Provider '{name}' already registered, overwriting")
            raise ValueError(f"Provider '{name}' already registered.")
        self._registry[name] = provider_class
        debug("Provider registered", name=name)

    def get(self, name: str, config: Dict[str, Any], **kwargs: Any) -> BaseLLMProvider:
        """
        Get and instantiate a provider using its class.
        
        Args:
            name: The name of the provider to retrieve (e.g., 'ollama', 'gemini').
            config: The configuration dictionary for the provider.
            **kwargs: Additional arguments to pass to the provider constructor.
        """
        provider_class = self._registry.get(name)
        if not provider_class:
            err(f"Provider class '{name}' not found", available=list(self._registry.keys()))
            raise ValueError(f"Provider class '{name}' not found.")
        debug("Provider instantiated", name=name, model=config.get("model"))
        return provider_class(config=config, **kwargs)

_provider_registry = ProviderRegistry()

def get_provider_registry() -> ProviderRegistry:
    return _provider_registry

def register_all_providers():
    """Registers all available LLM providers."""
    tracer("register_all_providers")
    _provider_registry.register("ollama", OllamaProvider)
    _provider_registry.register("gemini", GeminiProvider)
    step("Registered providers", providers=["ollama", "gemini"])
    # _provider_registry.register("openai", OpenAIProvider)

# Call this function during application startup to register providers.
# Example: In server/main.py's lifespan context:
# await register_all_providers()
