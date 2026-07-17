from typing import Any, Dict, List, Optional
from app.nodes.built_in.llm.base_llm_node import BaseLLMNode

class OllamaNode(BaseLLMNode):
    name: str = "ollama_node"
    label: str = "Ollama Node"
    description: str = "Executes llm request Ollama server"
    version: str = "1.0.1"

    icon: str = "bot"
    color: str = "#FF8C00"  # DarkOrange
    badge: str = "Ollama"
    sub_label: str = "Local Completion"

    # Standard System Properties with Ollama-specific defaults
    system_properties: List[Dict[str, Any]] = [
        {"key": "base_url", "label": "Base URL", "type": "string", "default": "http://127.0.0.1:11434"},
        {"key": "api_key", "label": "API Key", "type": "password", "default": "ollama"},
        {"key": "timeout_seconds", "label": "Timeout (seconds)", "type": "number", "default": 60},
        {"key": "max_retries", "label": "Max Retries", "type": "number", "default": 3},
        {"key": "default_model", "label": "Default Model", "type": "string", "default": "qwen:0.5b"}
    ]

    def build_auth_headers(self, api_key: str) -> Dict[str, str]:
        # Ollama usually does not require auth headers, but we support them if configured
        headers = {}
        if api_key and api_key.strip() and api_key != "ollama" and api_key != "EMPTY":
            headers["Authorization"] = f"Bearer {api_key.strip()}"
        return headers

    def build_payload(
        self, 
        messages: List[Dict[str, str]], 
        model: str, 
        temperature: float, 
        max_tokens: int,
        top_p: float
    ) -> Dict[str, Any]:
        return {
            "model": model or "qwen:0.5b",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p
        }

    def get_completions_endpoint(self, base_url: str, model: str = "", api_key: str = "") -> str:
        url = base_url.rstrip("/")
        if "chat/completions" in url:
            return url
        return f"{url}/v1/chat/completions"

    def get_models_endpoint(self, base_url: str) -> Optional[str]:
        url = base_url.rstrip("/")
        if "chat/completions" in url:
            url = url.replace("/chat/completions", "")
        return f"{url}/v1/models"

    def parse_response(self, response_json: Dict[str, Any]) -> str:
        choices = response_json.get("choices", [])
        if not choices:
            raise ValueError("Ollama completions response has no choices.")
        message = choices[0].get("message", {})
        content = message.get("content")
        if content is None:
            return ""
        return str(content)
