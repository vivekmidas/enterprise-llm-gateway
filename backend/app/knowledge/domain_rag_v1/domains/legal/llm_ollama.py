from __future__ import annotations

import json
import requests

class OllamaJsonLLM:
    """
    Small adapter for the existing local Ollama setup.
    Default model is intentionally configurable.
    """

    def __init__(
        self,
        model: str = "llama3.2:latest",
        base_url: str = "http://localhost:11434",
        timeout: int = 180,
    ):
        self.model = model
        self.url = base_url.rstrip("/") + "/api/chat"
        self.timeout = timeout

    def generate_json(self, *, system: str, user: str, schema: dict) -> dict:
        response = requests.post(
            self.url,
            json={
                "model": self.model,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload.get("message", {}).get("content", "")
        if not content:
            raise ValueError("Ollama returned an empty response")
        return json.loads(content)
