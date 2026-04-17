"""
Google Gemini LLM Provider

Integrates with Google's Gemini API for LLM inference.
"""

from typing import Dict, Any
from providers.base import BaseLLMProvider


class GeminiProvider(BaseLLMProvider):
    """
    Provider for Google Gemini API.
    
    Supports Gemini Pro and other Gemini models.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Gemini provider.
        
        Args:
            config: Configuration including:
                - api_key: Google API key (required)
                - model: Model name (default: "gemini-pro")
                - temperature: Sampling temperature (default: 0.7)
                - max_tokens: Maximum response length (default: 1000)
        """
        default_config = {
            "model": "gemini-pro",
            "temperature": 0.7,
            "max_tokens": 1000
        }
        default_config.update(config)
        
        if "api_key" not in config:
            raise ValueError("Gemini provider requires 'api_key' in config")
        
        super().__init__(default_config)
        
        self.api_key = self.config["api_key"]
        self._client = None
    
    def _get_client(self):
        """Lazy initialization of LangChain Gemini client"""
        if self._client is None:
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
                
                self._client = ChatGoogleGenerativeAI(
                    model=self.model,
                    google_api_key=self.api_key,
                    temperature=self.temperature,
                    max_output_tokens=self.max_tokens
                )
            except ImportError:
                raise ImportError(
                    "langchain-google-genai not installed. "
                    "Install with: pip install langchain-google-genai"
                )
        
        return self._client
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate text using Gemini.
        
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
            client.max_output_tokens = max_tokens
        
        # Generate
        response = await client.ainvoke(prompt)
        
        return response.content
    
    def get_model_name(self) -> str:
        """Get the current model name"""
        return self.model
    
    async def validate_connection(self) -> bool:
        """
        Validate connection to Gemini API.
        
        Returns:
            True if API key is valid, False otherwise
        """
        try:
            # Try a simple generation
            test_prompt = "Say 'OK' if you can read this."
            response = await self.generate(test_prompt)
            return len(response) > 0
        except Exception as e:
            print(f"Gemini connection failed: {e}")
            return False
    
    def set_safety_settings(self, settings: Dict[str, str]):
        """
        Configure safety settings for Gemini.
        
        Args:
            settings: Dictionary of safety settings
                Example: {
                    "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                    "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE"
                }
        """
        self.config["safety_settings"] = settings
        # Recreate client with new settings
        self._client = None
