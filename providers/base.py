"""
Base LLM Provider Interface

All LLM providers must implement this interface to work with the engine.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from core.logging import debug, tracer, step, warn, err


class BaseLLMProvider(ABC):
    """
    Abstract base class for all LLM providers.
    
    Provides a unified interface for different LLM backends (Ollama, Gemini, OpenAI).
    """
    
    def __init__(self, config: Dict[str, Any]):
        tracer(f"BaseLLMProvider.__init__", model=config.get("model"))
        self.config = config
        self.model = config.get("model")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 1000)
        debug("Provider initialized", model=self.model, temperature=self.temperature, max_tokens=self.max_tokens)
        
    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate text from the LLM.
        
        Args:
            prompt: The input prompt
            **kwargs: Additional generation parameters that override defaults
        
        Returns:
            Generated text string
        
        Raises:
            Exception: If generation fails
        """
        raise NotImplementedError
    
    @abstractmethod
    def get_model_name(self) -> str:
        """
        Get the name/identifier of the current model.
        
        Returns:
            Model name string
        """
        raise NotImplementedError
    
    @abstractmethod
    async def validate_connection(self) -> bool:
        """
        Validate that the provider can connect to the LLM service.
        
        Returns:
            True if connection is valid, False otherwise
        """
        raise NotImplementedError
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the current provider configuration.
        
        Returns:
            Configuration dictionary
        """
        return self.config
    
    async def batch_generate(self, prompts: List[str], **kwargs) -> List[str]:
        """Generate text for multiple prompts (default sequential implementation)."""
        tracer("batch_generate", prompt_count=len(prompts))
        import asyncio
        
        tasks = [self.generate(prompt, **kwargs) for prompt in prompts]
        results = await asyncio.gather(*tasks)
        step("Batch generation complete", results=len(results))
        return results
    
    async def cleanup(self):
        """Cleanup resources when provider is destroyed."""
        debug("Provider cleanup", model=self.model)
        pass


class MockLLMProvider(BaseLLMProvider):
    """
    Mock LLM provider for testing without actual API calls.
    
    Returns predefined responses or simple transformations.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        default_config = {
            "model": "mock-model",
            "temperature": 0.7,
            "max_tokens": 1000,
            "response_template": "Mock response to: {prompt}"
        }
        
        if config:
            default_config.update(config)
        
        super().__init__(default_config)
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """Return a mock response"""
        tracer("MockLLMProvider.generate")
        template = self.config.get("response_template", "Mock response to: {prompt}")
        result = template.format(prompt=prompt[:100])
        debug("Mock response generated", length=len(result))
        return result
    
    def get_model_name(self) -> str:
        return "mock-model"
    
    async def validate_connection(self) -> bool:
        debug("MockLLMProvider validating connection")
        return True