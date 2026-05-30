"""
OpenAI LLM Provider

Integrates with OpenAI API for GPT models.
"""

from typing import Dict, Any
from providers.base import BaseLLMProvider
from core.logging import debug, tracer, step, warn, err


class OpenAIProvider(BaseLLMProvider):
    """
    Provider for OpenAI API.
    
    Supports GPT-4, GPT-3.5-turbo, and other OpenAI models.
    """
    
    def __init__(self, config: Dict[str, Any]):
        tracer("OpenAIProvider.__init__", model=config.get("model"))
        default_config = {
            "model": "gpt-4",
            "temperature": 0.7,
            "max_tokens": 1000
        }
        default_config.update(config)
        
        if "api_key" not in config:
            err("Missing API key for OpenAI provider")
            raise ValueError("OpenAI provider requires 'api_key' in config")
        
        super().__init__(default_config)
        
        self.api_key = self.config["api_key"]
        self.organization = self.config.get("organization")
        self._client = None
        debug("OpenAI provider initialized", model=self.model, org=bool(self.organization))
    
    def _get_client(self):
        """Lazy initialization of LangChain OpenAI client"""
        if self._client is None:
            debug("Creating OpenAI client", model=self.model)
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
                step("OpenAI client created")
            except ImportError:
                err("langchain-openai not installed")
                raise ImportError(
                    "langchain-openai not installed. "
                    "Install with: pip install langchain-openai"
                )
        
        return self._client
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate text using OpenAI."""
        tracer("OpenAIProvider.generate", model=self.model)
        client = self._get_client()
        
        temperature = kwargs.get("temperature", self.temperature)
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        
        if temperature != self.temperature:
            client.temperature = temperature
        if max_tokens != self.max_tokens:
            client.max_tokens = max_tokens
        
        debug("Generating response", temperature=temperature, max_tokens=max_tokens)
        response = await client.ainvoke(prompt)
        
        step("Generation complete", response_length=len(response.content))
        return response.content
    
    def get_model_name(self) -> str:
        """Get the current model name"""
        return self.model
    
    async def validate_connection(self) -> bool:
        """Validate connection to OpenAI API."""
        tracer("OpenAIProvider.validate_connection")
        try:
            test_prompt = "Say 'OK' if you can read this."
            response = await self.generate(test_prompt)
            connected = len(response) > 0
            debug("Connection validated", connected=connected)
            return connected
        except Exception as e:
            err("OpenAI connection failed", error=str(e))
            return False
    
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Estimate the cost of a request."""
        tracer("OpenAIProvider.estimate_cost", model=self.model, input_tokens=input_tokens, output_tokens=output_tokens)
        pricing = {
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},
            "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
        }
        
        model_pricing = pricing.get(self.model, pricing["gpt-4"])
        
        input_cost = (input_tokens / 1000) * model_pricing["input"]
        output_cost = (output_tokens / 1000) * model_pricing["output"]
        
        total = input_cost + output_cost
        debug("Cost estimated", total=round(total, 6))
        return total
    
    def get_token_limit(self) -> int:
        """Get the context window size for the current model."""
        limits = {
            "gpt-4": 8192,
            "gpt-4-turbo": 128000,
            "gpt-4-32k": 32768,
            "gpt-3.5-turbo": 16385,
            "gpt-3.5-turbo-16k": 16385,
        }
        
        limit = limits.get(self.model, 8192)
        debug("Token limit retrieved", model=self.model, limit=limit)
        return limit
