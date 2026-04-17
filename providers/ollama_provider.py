"""
Ollama LLM Provider

Integrates with local Ollama instance for LLM inference.
"""

from typing import Dict, Any
from providers.base import BaseLLMProvider


class OllamaProvider(BaseLLMProvider):
    """
    Provider for Ollama local LLM inference.
    
    Requires Ollama to be running locally or accessible at the specified base URL.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize Ollama provider.
        
        Args:
            config: Configuration including:
                - model: Model name (e.g., "llama3", "mistral", "codellama")
                - base_url: Ollama API endpoint (default: "http://localhost:11434")
                - temperature: Sampling temperature (default: 0.7)
                - max_tokens: Maximum response length (default: 1000)
        """
        default_config = {
            "base_url": "http://localhost:11434",
            "temperature": 0.7,
            "max_tokens": 1000
        }
        default_config.update(config)
        
        super().__init__(default_config)
        
        self.base_url = self.config.get("base_url")
        self._client = None
    
    def _get_client(self):
        """Lazy initialization of LangChain Ollama client"""
        if self._client is None:
            try:
                from langchain_ollama import ChatOllama
                
                self._client = ChatOllama(
                    model=self.model,
                    base_url=self.base_url,
                    temperature=self.temperature,
                    num_predict=self.max_tokens
                )
            except ImportError:
                raise ImportError(
                    "langchain-ollama not installed. "
                    "Install with: pip install langchain-ollama"
                )
        
        return self._client
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """
        Generate text using Ollama.
        
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
            client.num_predict = max_tokens
        
        # Generate
        response = await client.ainvoke(prompt)
        
        return response.content
    
    def get_model_name(self) -> str:
        """Get the current model name"""
        return self.model
    
    async def validate_connection(self) -> bool:
        """
        Validate connection to Ollama.
        
        Returns:
            True if Ollama is accessible, False otherwise
        """
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception as e:
            print(f"Ollama connection failed: {e}")
            return False
    
    async def list_available_models(self) -> list:
        """
        List all models available in Ollama.
        
        Returns:
            List of model names
        """
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    return [model["name"] for model in data.get("models", [])]
        except Exception as e:
            print(f"Failed to list models: {e}")
        
        return []
    
    async def pull_model(self, model_name: str) -> bool:
        """
        Pull a model from Ollama registry.
        
        Args:
            model_name: Name of the model to pull
        
        Returns:
            True if successful, False otherwise
        """
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model_name}
                )
                return response.status_code == 200
        except Exception as e:
            print(f"Failed to pull model: {e}")
            return False
