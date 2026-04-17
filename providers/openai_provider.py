"""
OpenAI LLM Provider

Integrates with OpenAI API for GPT models.
"""

from typing import Dict, Any
from providers.base import BaseLLMProvider


class OpenAIProvider(BaseLLMProvider):
    """
    Provider for OpenAI API.
    
    Supports GPT-4, GPT-3.5-turbo, and other OpenAI models.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize OpenAI provider.
        
        Args:
            config: Configuration including:
                - api_key: OpenAI API key (required)
                - model: Model name (default: "gpt-4")
                - temperature: Sampling temperature (default: 0.7)
                - max_tokens: Maximum response length (default: 1000)
                - organization: OpenAI organization ID (optional)
        """
        default_config = {
            "model": "gpt-4",
            "temperature": 0.7,
            "max_tokens": 1000
        }
        default_config.update(config)
        
        if "api_key" not in config:
            raise ValueError("OpenAI provider requires 'api_key' in config")
        
        super().__init__(default_config)
        
        self.api_key = self.config["api_key"]
        self.organization = self.config.get("organization")
        self._client = None
    
    def _get_client(self):
        """Lazy initialization of LangChain OpenAI client"""
        if self._client is None:
            try:
                from langchain_openai import ChatOpenAI
                
                kwargs = {
                    "model": self.model,
                    "api_key": self.api_key,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens
                }
                
                if self.organization:
                    kwargs["organization"] = self.organization
                
                self._client = ChatOpenAI(**kwargs)
                
            except ImportError:
                raise ImportError(
                    "langchain-openai not installed. "
                    "Install with: pip install langchain-openai"
                )
        
        return self._client
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate text using OpenAI.
        
        Args:
            prompt: Input prompt
            **kwargs: Override parameters (temperature, max_tokens, etc.)
        
        Returns:
            Generated text
        """
        client = self._get_client()
        
        # Override defaults with kwargs
        temperature = kwargs.get("temperature", self.temperature)
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        
        # Update client params if needed
        if temperature != self.temperature:
            client.temperature = temperature
        if max_tokens != self.max_tokens:
            client.max_tokens = max_tokens
        
        # Generate
        response = await client.ainvoke(prompt)
        
        return response.content
    
    def get_model_name(self) -> str:
        """Get the current model name"""
        return self.model
    
    async def validate_connection(self) -> bool:
        """
        Validate connection to OpenAI API.
        
        Returns:
            True if API key is valid, False otherwise
        """
        try:
            # Try a simple generation
            test_prompt = "Say 'OK' if you can read this."
            response = await self.generate(test_prompt)
            return len(response) > 0
        except Exception as e:
            print(f"OpenAI connection failed: {e}")
            return False
    
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """
        Estimate the cost of a request.
        
        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
        
        Returns:
            Estimated cost in USD
        """
        # Pricing as of 2024 (update as needed)
        pricing = {
            "gpt-4": {"input": 0.03, "output": 0.06},  # per 1k tokens
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},
            "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        }
        
        model_pricing = pricing.get(self.model, pricing["gpt-4"])
        
        input_cost = (input_tokens / 1000) * model_pricing["input"]
        output_cost = (output_tokens / 1000) * model_pricing["output"]
        
        return input_cost + output_cost
    
    def get_token_limit(self) -> int:
        """
        Get the context window size for the current model.
        
        Returns:
            Maximum token limit
        """
        limits = {
            "gpt-4": 8192,
            "gpt-4-turbo": 128000,
            "gpt-4-32k": 32768,
            "gpt-3.5-turbo": 16385,
            "gpt-3.5-turbo-16k": 16385,
        }
        
        return limits.get(self.model, 8192)
