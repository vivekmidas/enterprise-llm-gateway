import httpx
from typing import Any, Dict, List, Optional
import json
from app.nodes.base import BaseNode
from app.core.types.common import NodeInput, NodeOutput

class GenericLLMAgent(BaseNode):
    name: str = "generic_llm_agent"
    label: str = "Generic LLM"
    description: str = "Calls an LLM via specific IP and Port using OpenAI-compatible API"
    version: str = "1.0.0"
    category: str = "LLM"
    group: str = "LLM"
    icon: str = "bot"

    # Hardcoded fallback defaults (Level 0)
    # Level 1 (NodeDB) will override these during init()
    # Level 2 (Workflow Instance) will override everything during run()
 

    async def init(self) -> None:
        """
        Initializes the agent.
        BaseNode.init() fetches global defaults from the NodeDB, ensuring we 
        bypass any local file-based configurations.
        """
        await super().init()
        self.logger.info("generic_llm_agent_properties_loaded", properties=self.properties) 
        self.logger.info("generic_llm_agent_initialized", node_name=self.name)

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        """Validates that input content is present before execution."""
        await super().validate_input(inp)
        if not inp.data or not inp.data.strip():
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_message="Input content is empty",
            )
        return None
        
    async def execute(self, inp: NodeInput) -> NodeOutput:
        """
        Executes the LLM call using the merged config.
        The 'config' object already contains the priority-resolved properties:
        NodeDB Default -> Overridden by Workflow Node Instance.
        """
        config = inp.config
        
        ip = config.get("ip")
        port = config.get("port")
        model_name = config.get("model_name")
        temperature = float(config.get("temperature")) # Ensure temperature is a float
        system_prompt = config.get("system_prompt")

        message_to_llm = inp.data # Default to using the raw content

        # Attempt to parse as JSON and extract 'message' if it's a dict
        try:
            parsed_json = json.loads(inp.data)
            if isinstance(parsed_json, dict) and "message" in parsed_json:
                message_to_llm = parsed_json["message"]
        except json.JSONDecodeError:
            # Not a valid JSON string, fallback to using the original content
            pass
        
        # OpenAI-compatible chat completion endpoint
        path = config.get("path", "/v1/chat/completions")
        endpoint = f"http://{ip}:{port}{path}"
        
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message_to_llm}
            ],
            "temperature": temperature,
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(endpoint, json=payload, timeout=60.0)
                response.raise_for_status()
                data = response.json()
                
                # Extracting content from OpenAI response format
                ai_message = data["choices"][0]["message"]["content"]
                usage = data.get("usage", {})
                
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=ai_message,
                    metadata={
                        "endpoint": endpoint,
                        "model": model_name,
                        "usage": usage
                    },
                    status="success"
                )
        except Exception as e:
            self.logger.error("generic_llm_request_failed", error=str(e), endpoint=endpoint)
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_message=f"Generic LLM request failed: {str(e)}",
            )