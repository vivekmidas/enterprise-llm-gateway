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
        data_val = self.get_input_data(inp)
        if data_val is None or (isinstance(data_val, str) and not data_val.strip()) or (isinstance(data_val, (dict, list)) and not data_val):
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
        temperature = config.get("temperature") # Ensure temperature is a float
        system_prompt = config.get("system_prompt")

        data_val = self.get_input_data(inp)
        if isinstance(data_val, (dict, list)):
            message_to_llm = json.dumps(data_val, indent=2)
        elif data_val is not None:
            message_to_llm = str(data_val)
        else:
            message_to_llm = ""
        
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
                
                out_data = self.set_output_data(inp, ai_message)
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=out_data,
                    metadata={
                        "endpoint": endpoint,
                        "model": model_name,
                        "usage": usage
                    },
                    status="success"
                )
        except Exception as e:
            self.logger.error("generic_llm_request_failed", trace_id=inp.trace_id, error=str(e), endpoint=endpoint)
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_message=f"Generic LLM request failed: {str(e)}",
            )