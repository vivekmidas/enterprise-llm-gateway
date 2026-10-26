"""
Ollama Provider Node implementation.
Extends BaseLLMNode to execute chat completions against a local or remote Ollama server.
Supports standard OpenAI-compatible completions endpoints, model querying, and token tracking.
"""

from typing import Any, Dict, List, Optional
from app.nodes.built_in.llm.base_llm_node import BaseLLMNode


class OllamaNode(BaseLLMNode):
    """
    Ollama LLM Node.
    Executes chat completions against an Ollama server instance.
    """

    def build_auth_headers(self, api_key: str) -> Dict[str, str]:
        """Constructs Authorization headers if API key is provided and non-default."""
        headers = {}
        if api_key and api_key.strip() and api_key not in ("ollama", "EMPTY"):
            headers["Authorization"] = f"Bearer {api_key.strip()}"
        return headers

    def get_completions_endpoint(self, base_url: str, model: str = "", api_key: str = "") -> str:
        """Constructs chat completions endpoint URL for Ollama."""
        url = (base_url or "http://127.0.0.1:11434").rstrip("/")
        if "chat/completions" in url or "api/chat" in url:
            return url
        return f"{url}/v1/chat/completions"

    def get_models_endpoint(self, base_url: str) -> Optional[str]:
        """Returns the endpoint URL for fetching available models in Ollama."""
        url = (base_url or "http://127.0.0.1:11434").rstrip("/")
        if "chat/completions" in url:
            url = url.replace("/chat/completions", "")
        return f"{url}/v1/models"

    def build_payload(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        top_p: float
    ) -> Dict[str, Any]:
        """Constructs payload for Ollama chat completions API."""
        return {
            "model": model or "llama3.2",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "stream": False
        }

    def parse_response(self, response_json: Dict[str, Any]) -> str:
        """Parses clean text output from Ollama chat or completions API response."""
        if "message" in response_json:
            message = response_json.get("message", {})
            content = message.get("content")
            if content is not None:
                return str(content)
        choices = response_json.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content")
            if content is not None:
                return str(content)
        if "response" in response_json:
            return str(response_json["response"])
        raise ValueError("Ollama response does not contain message, choices, or response content.")
