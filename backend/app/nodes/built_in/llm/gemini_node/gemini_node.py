from typing import Any, Dict, List, Optional
from app.nodes.built_in.llm.base_llm_node import BaseLLMNode

class GeminiNode(BaseLLMNode):


    # Standard System Properties with Gemini defaults

    def build_auth_headers(self, api_key: str) -> Dict[str, str]:
        # Google Gemini takes api_key in URL parameters, so headers remain empty
        return {}

    def build_payload(
        self, 
        messages: List[Dict[str, str]], 
        model: str, 
        temperature: float, 
        max_tokens: int,
        top_p: float
    ) -> Dict[str, Any]:
        contents = []
        system_instruction = None

        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system_instruction = {
                    "parts": [{"text": content}]
                }
            else:
                gemini_role = "user" if role == "user" else "model"
                contents.append({
                    "role": gemini_role,
                    "parts": [{"text": content}]
                })

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": top_p
            }
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        return payload

    def get_completions_endpoint(self, base_url: str, model: str = "", api_key: str = "") -> str:
        url = base_url.rstrip("/")
        m = model or "gemini-1.5-flash"
        # Endpoint formatting
        return f"{url}/v1beta/models/{m}:generateContent?key={api_key}"

    def get_models_endpoint(self, base_url: str) -> Optional[str]:
        # Google Gemini models endpoint path
        return f"{base_url.rstrip('/')}/v1beta/models"

    def parse_response(self, response_json: Dict[str, Any]) -> str:
        candidates = response_json.get("candidates", [])
        if not candidates:
            # If Google API returned an error structure
            if "error" in response_json:
                error_msg = response_json["error"].get("message") or "Unknown Gemini API error."
                raise ValueError(f"Gemini API returned error: {error_msg}")
            raise ValueError("Gemini completions response has no candidates.")
            
        candidate = candidates[0]
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        if not parts:
            # Check if candidate was blocked (e.g. safety settings)
            finish_reason = candidate.get("finishReason")
            if finish_reason and finish_reason != "STOP":
                raise ValueError(f"Gemini generation did not complete normally. Finish reason: {finish_reason}")
            raise ValueError("Gemini completions response content parts are empty.")
            
        text = parts[0].get("text")
        if text is None:
            return ""
        return str(text)
