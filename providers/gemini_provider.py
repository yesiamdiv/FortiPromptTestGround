"""
Google Gemini LLM Provider

Integrates with Google's Gemini API for LLM inference.
"""

from typing import Dict, Any
from providers.base import BaseLLMProvider
from core.logging import debug, tracer, step, warn, err


class GeminiProvider(BaseLLMProvider):
    """
    Provider for Google Gemini API.
    
    Supports Gemini Pro and other Gemini models.
    """
    
    def __init__(self, config: Dict[str, Any]):
        tracer("GeminiProvider.__init__", model=config.get("model"))
        default_config = {
            "model": "gemini-pro",
            "temperature": 0.7,
            "max_tokens": 1000
        }
        default_config.update(config)
        
        if "api_key" not in config:
            err("Missing API key for Gemini provider")
            raise ValueError("Gemini provider requires 'api_key' in config")
        
        super().__init__(default_config)
        
        self.api_key = self.config["api_key"]
        self._client = None
        debug("Gemini provider initialized", model=self.model)
    
    def _get_client(self):
        """Lazy initialization of LangChain Gemini client"""
        if self._client is None:
            debug("Creating Gemini client", model=self.model)
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                
                self._client = ChatGoogleGenerativeAI(
                    model=self.model,
                    google_api_key=self.api_key,
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens
                )
                step("Gemini client created")
            except ImportError:
                err("langchain-google-genai not installed")
                raise ImportError(
                    "langchain-google-genai not installed. "
                    "Install with: pip install langchain-google-genai"
                )
        
        return self._client
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate text using Gemini."""
        tracer("GeminiProvider.generate", model=self.model)
        client = self._get_client()
        
        temperature = kwargs.get("temperature", self.temperature)
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        
        if temperature != self.temperature:
            client.temperature = temperature
        if max_tokens != self.max_tokens:
            client.max_output_tokens = max_tokens
        
        debug("Generating response", temperature=temperature, max_tokens=max_tokens)
        response = await client.ainvoke(prompt)
        
        step("Generation complete", response_length=len(response.content))
        return response.content
    
    def get_model_name(self) -> str:
        """Get the current model name"""
        return self.model
    
    async def validate_connection(self) -> bool:
        """Validate connection to Gemini API."""
        tracer("GeminiProvider.validate_connection")
        try:
            test_prompt = "Say 'OK' if you can read this."
            response = await self.generate(test_prompt)
            connected = len(response) > 0
            debug("Connection validated", connected=connected)
            return connected
        except Exception as e:
            err("Gemini connection failed", error=str(e))
            return False
    
    def set_safety_settings(self, settings: Dict[str, str]):
        """Configure safety settings for Gemini."""
        tracer("GeminiProvider.set_safety_settings", categories=list(settings.keys()))
        self.config["safety_settings"] = settings
        self._client = None
        debug("Safety settings updated, client reset")
