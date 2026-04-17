"""
Base LLM Provider Interface

All LLM providers must implement this interface to work with the engine.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List


class BaseLLMProvider(ABC):
    """
    Abstract base class for all LLM providers.
    
    Provides a unified interface for different LLM backends (Ollama, Gemini, OpenAI).
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the provider with configuration.
        
        Args:
            config: Provider-specific configuration including:
                - model: Model identifier
                - temperature: Sampling temperature
                - max_tokens: Maximum response length
                - api_key: API key (if required)
                - base_url: API endpoint (if required)
        """
        self.config = config
        self.model = config.get("model")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 1000)
        
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
        """
        Generate text for multiple prompts (default sequential implementation).
        
        Override this for providers that support true batch processing.
        
        Args:
            prompts: List of input prompts
            **kwargs: Additional generation parameters
        
        Returns:
            List of generated text strings
        """
        import asyncio
        
        tasks = [self.generate(prompt, **kwargs) for prompt in prompts]
        return await asyncio.gather(*tasks)
    
    async def cleanup(self):
        """
        Cleanup resources when provider is destroyed.
        
        Override this to close connections, flush buffers, etc.
        """
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
        template = self.config.get("response_template", "Mock response to: {prompt}")
        return template.format(prompt=prompt[:100])
    
    def get_model_name(self) -> str:
        return "mock-model"
    
    async def validate_connection(self) -> bool:
        return True
