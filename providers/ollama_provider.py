"""
Ollama LLM Provider

Integrates with local Ollama instance for LLM inference.
"""

from typing import Dict, Any
import asyncio
import shutil
import subprocess
import sys
from providers.base import BaseLLMProvider
from core.logging import debug, tracer, step, warn, err
from core.env import get_settings


class OllamaProvider(BaseLLMProvider):
    """
    Provider for Ollama local LLM inference.
    
    Requires Ollama to be running locally or accessible at the specified base URL.
    """
    
    def __init__(self, config: Dict[str, Any]):
        tracer("OllamaProvider.__init__", model=config.get("model"))
        default_config = {
            "base_url": get_settings().ollama_base_url,
            "temperature": 0.7,
            "max_tokens": 1000
        }
        default_config.update(config)
        
        super().__init__(default_config)
        
        self.base_url = self.config.get("base_url")
        self._client = None
        debug("Ollama provider initialized", base_url=self.base_url, model=self.model)

    async def ensure_running(self) -> bool:
        """Check if Ollama is reachable; if not, try to start it."""
        if await self.validate_connection():
            return True
        warn("Ollama is not running – attempting to start it...")
        try:
            ollama_path = shutil.which("ollama")
            if not ollama_path:
                err("ollama binary not found on PATH")
                return False
            proc = await asyncio.create_subprocess_exec(
                ollama_path, "serve",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for attempt in range(15):
                await asyncio.sleep(1)
                if await self.validate_connection():
                    step("Ollama started successfully")
                    return True
                debug(f"Waiting for Ollama... ({attempt + 1}/15)")
            warn("Ollama did not become ready within 15 seconds "
                 "(it may still be starting in the background)")
            return False
        except FileNotFoundError:
            err("ollama binary not found")
            return False
        except Exception as e:
            err("Failed to start Ollama", error=str(e))
            return False

    def _get_client(self):
        """Lazy initialization of LangChain Ollama client"""
        if self._client is None:
            debug("Creating Ollama client", model=self.model, base_url=self.base_url)
            try:
                from langchain_ollama import ChatOllama
                
                self._client = ChatOllama(
                    model=self.model,
                    base_url=self.base_url,
                    temperature=self.temperature,
                    num_predict=self.max_tokens
                )
                step("Ollama client created")
            except ImportError:
                err("langchain-ollama not installed")
                raise ImportError(
                    "langchain-ollama not installed. "
                    "Install with: pip install langchain-ollama"
                )
        
        return self._client
    
    async def generate(self, prompt: str, **kwargs) -> str:
        """Generate text using Ollama."""
        tracer("OllamaProvider.generate", model=self.model)
        client = self._get_client()
        
        temperature = kwargs.get("temperature", self.temperature)
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        
        if temperature != self.temperature:
            client.temperature = temperature
        if max_tokens != self.max_tokens:
            client.num_predict = max_tokens
        
        debug("Generating response", temperature=temperature, max_tokens=max_tokens)
        response = await client.ainvoke(prompt)
        
        step("Generation complete", response_length=len(response.content))
        return response.content
    
    def get_model_name(self) -> str:
        """Get the current model name"""
        return self.model
    
    async def validate_connection(self) -> bool:
        """Validate connection to Ollama."""
        tracer("OllamaProvider.validate_connection")
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags")
                connected = response.status_code == 200
                debug("Connection validated", connected=connected)
                return connected
        except Exception as e:
            err("Ollama connection failed", error=str(e))
            return False
    
    async def list_available_models(self) -> list:
        """List all models available in Ollama."""
        tracer("OllamaProvider.list_available_models")
        try:
            import httpx
            
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    models = [model["name"] for model in data.get("models", [])]
                    step("Models listed", models=models)
                    return models
        except Exception as e:
            err("Failed to list models", error=str(e))
        
        return []
    
    async def pull_model(self, model_name: str) -> bool:
        """Pull a model from Ollama registry."""
        tracer("OllamaProvider.pull_model", model=model_name)
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/pull",
                    json={"name": model_name}
                )
                success = response.status_code == 200
                step("Pull model result", model=model_name, success=success)
                return success
        except Exception as e:
            err("Failed to pull model", model=model_name, error=str(e))
            return False
