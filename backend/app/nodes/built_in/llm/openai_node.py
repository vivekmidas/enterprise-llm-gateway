from typing import Any, Dict, List, Optional
from app.nodes.built_in.llm.base_llm_node import BaseLLMNode

class OpenAINode(BaseLLMNode):
    name: str = "openai_node"
    label: str = "OpenAI Chat"
    description: str = "Executes chat completions on OpenAI, Grok, DeepSeek, or other OpenAI-compatible APIs."
    version: str = "1.0.0"

    icon: str = "bot"
    color: str = "#10A37F"  # OpenAI Green
    badge: str = "OpenAI"
    sub_label: str = "Chat Completion"

    def build_auth_headers(self, api_key: str) -> Dict[str, str]:
        headers = {}
        if api_key and api_key.strip() and api_key != "EMPTY":
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
            "model": model or "gpt-4o-mini",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p
        }

    def get_completions_endpoint(self, base_url: str, model: str = "", api_key: str = "") -> str:
        url = base_url.rstrip("/")
        # If the base_url already contains completions/chat/completions, use it directly
        if "chat/completions" in url:
            return url
        return f"{url}/chat/completions"

    def get_models_endpoint(self, base_url: str) -> Optional[str]:
        url = base_url.rstrip("/")
        if "chat/completions" in url:
            url = url.replace("/chat/completions", "")
        return f"{url}/models"

    def parse_response(self, response_json: Dict[str, Any]) -> str:
        choices = response_json.get("choices", [])
        if not choices:
            raise ValueError("OpenAI completions response has no choices.")
        message = choices[0].get("message", {})
        content = message.get("content")
        if content is None:
            return ""
        return str(content)
