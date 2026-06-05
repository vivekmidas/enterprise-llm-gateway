import httpx
import time
from typing import Any, Dict
from app.nodes.base import BaseNode, NodeInput, NodeOutput

class GenericLLMAgent(BaseNode):
    name: str = "generic_llm_agent"
    description: str = "Calls an LLM via specific IP and Port using OpenAI-compatible API"
    version: str = "1.0.0"
    category: str = "LLM"

    async def init(self) -> None:
        await super().init()

    async def execute(self, inp: NodeInput) -> NodeOutput:
        start_ts = time.time()
        config = inp.config or {}
        
        ip = config.get("ip", "127.0.0.1")
        port = config.get("port", "8000")
        model = config.get("model", "default-model")
        temperature = config.get("temperature", 0.7)
        system_prompt = config.get("systemPrompt", "You are a helpful assistant.")
        
        # OpenAI-compatible chat completion endpoint
        endpoint = f"http://{ip}:{port}/v1/chat/completions"
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": inp.content}
            ],
            "temperature": float(temperature),
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(endpoint, json=payload, timeout=60.0)
                response.raise_for_status()
                data = response.json()
                
                # Extracting content from OpenAI response format
                ai_message = data["choices"][0]["message"]["content"]
                
                return NodeOutput(
                    trace_id=inp.trace_id,
                    content=ai_message,
                    metadata={
                        "endpoint": endpoint,
                        "model": model,
                        "provider": "generic_http"
                    },
                    status="success"
                )
        except Exception as e:
            return NodeOutput(
                trace_id=inp.trace_id,
                content=inp.content,
                status="failure",
                error=f"Generic LLM request failed: {str(e)}",
            )