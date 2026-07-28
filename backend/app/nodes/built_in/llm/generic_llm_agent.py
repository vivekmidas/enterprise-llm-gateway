import httpx
from typing import Any, Dict, List, Optional
import json
from app.nodes.built_in.llm.base_llm_node import BaseLLMNode
from app.core.types.common import NodeInput, NodeOutput

# BLOCK COMMENT FOR GENERIC LLM AGENT
# GenericLLMAgent provides standard OpenAI-compatible API execution helpers
class GenericLLMAgent(BaseLLMNode):
    name: str = "generic_llm_agent"
    label: str = "Generic LLM"
    description: str = "Calls an LLM via specific IP and Port using OpenAI-compatible API"
    version: str = "1.0.0"
    category: str = "LLM"
    group: str = "LLM"
    icon: str = "bot"

    user_properties: List[Dict[str, Any]] = [
        # {
        #     "key": "model",
        #     "label": "Model Name",
        #     "type": "string",
        #     "default": "qwen:0.5b"
        # },
        # {
        #     "key": "temperature",
        #     "label": "Temperature",
        #     "type": "number",
        #     "default": 0.7
        # },
        # {
        #     "key": "system_prompt",
        #     "label": "System Prompt",
        #     "type": "textarea",
        #     "default": ""
        # }
    ]

    system_properties: List[Dict[str, Any]] = [
        # {
        #     "key": "ip",
        #     "label": "IP Address",
        #     "type": "string",
        #     "default": "127.0.0.1"
        # },
        # {
        #     "key": "port",
        #     "label": "Port",
        #     "type": "string",
        #     "default": "11434"
        # },
        # {
        #     "key": "path",
        #     "label": "Path",
        #     "type": "string",
        #     "default": "/v1/chat/completions"
        # }
    ]

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

    async def get_input_contract ():
        return self.input_contract

    async def get_output_contract ():
        return self.output_contract
    
    async def execute(self, inp: NodeInput) -> NodeOutput:
        """
        Executes the LLM call using the merged config.
        The 'config' object already contains the priority-resolved properties:
        NodeDB Default -> Overridden by Workflow Node Instance.
        """
        config = inp.config
        
        ip = config.get("ip") or "127.0.0.1"
        port = config.get("port") or "11434"
        model_name = config.get("model_name") or config.get("model") or "qwen:0.5b"
        
        temperature_raw = config.get("temperature")
        if temperature_raw is not None:
            try:
                temperature = float(temperature_raw)
            except (ValueError, TypeError):
                temperature = 0.7
        else:
            temperature = 0.7

        system_prompt = config.get("system_prompt") or config.get("systemPrompt")
        if not system_prompt:
            from app.core.config import get_settings
            system_prompt = get_settings().SYSTEM_PROMPT

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
            self.logger.info("generic_llm_request_started", trace_id=inp.trace_id, endpoint=endpoint, model=model_name)
            async with httpx.AsyncClient() as client:
                response = await client.post(endpoint, json=payload, timeout=60.0)
                response.raise_for_status()
                data = response.json()
                
                if "choices" not in data or not data["choices"]:
                    self.logger.error("generic_llm_invalid_response", trace_id=inp.trace_id, response=data)
                    raise ValueError("OpenAI-compatible API response missing choices key or choices is empty")

                choice = data["choices"][0]
                if "message" not in choice or "content" not in choice["message"]:
                    self.logger.error("generic_llm_invalid_choice_structure", trace_id=inp.trace_id, choice=choice)
                    raise ValueError("OpenAI-compatible API choice missing message or content")

                # Extracting content from OpenAI response format
                ai_message = choice["message"]["content"]
                if ai_message is None:
                    ai_message = ""

                usage = data.get("usage", {})
                self.logger.info("generic_llm_request_success", trace_id=inp.trace_id, usage=usage)
                
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