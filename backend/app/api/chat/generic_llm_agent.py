import httpx
import time
from typing import Any, Dict
from app.agents.built_in.base import BaseAgent, AgentInput, AgentOutput

class GenericLLMAgent(BaseAgent):
    name = "generic_llm_agent"
    description = "Calls an LLM via specific IP and Port using OpenAI-compatible API"
    version = "1.0.0"
    category = "LLM"

    async def run(self, inp: AgentInput) -> AgentOutput:
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
                
                return AgentOutput(
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
            return AgentOutput(
                trace_id=inp.trace_id,
                content=inp.content,
                status="failure",
                error=f"Generic LLM request failed: {str(e)}",
            )