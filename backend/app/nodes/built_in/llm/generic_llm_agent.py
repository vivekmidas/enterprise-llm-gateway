import httpx
from typing import Any, Dict, List, Optional
import json
from app.nodes.base import BaseNode, NodeInput, NodeOutput

class GenericLLMAgent(BaseNode):
    name: str = "generic_llm_agent"
    label: str = "Generic LLM"
    description: str = "Calls an LLM via specific IP and Port using OpenAI-compatible API"
    version: str = "1.0.0"
    category: str = "LLM"
    group: str = "LLM"
    icon: str = "bot"

    # Defines the fields available for this node in the UI and NodeDB
    property_schema: List[Dict[str, Any]] = [
        {"key": "ip", "label": "IP Address", "type": "string", "placeholder": "127.0.0.1"},
        {"key": "port", "label": "Port", "type": "string", "placeholder": "8000"},
        {"key": "model", "label": "Model Name", "type": "string", "placeholder": "default-model"},
        {"key": "temperature", "label": "Temperature", "type": "number", "placeholder": "0.7"},
        {"key": "system_prompt", "label": "System Prompt", "type": "textarea", "placeholder": "You are a helpful assistant."},
        {"key": "path", "label": "API Path", "type": "string", "placeholder": "/v1/chat/completions"},
    ]

    # Hardcoded fallback defaults (Level 0)
    # Level 1 (NodeDB) will override these during init()
    # Level 2 (Workflow Instance) will override everything during run()
    properties: Dict[str, Any] = {
        "ip": "127.0.0.1",
        "port": "8000",
        "model": "qwen:0.5b",
        "temperature": 0.7, 
        "system_prompt": "You are a helpful assistant.",
        "path": "/v1/chat/completions"
    }

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
        if not inp.content or not inp.content.strip():
            return NodeOutput(
                trace_id=inp.trace_id,
                content=inp.content,
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
        model = config.get("model")
        temperature = float(config.get("temperature")) # Ensure temperature is a float
        system_prompt = config.get("system_prompt")

        message_to_llm = inp.content # Default to using the raw content

        # Attempt to parse as JSON and extract 'message' if it's a dict
        try:
            parsed_json = json.loads(inp.content)
            if isinstance(parsed_json, dict) and "message" in parsed_json:
                message_to_llm = parsed_json["message"]
        except json.JSONDecodeError:
            # Not a valid JSON string, fallback to using the original content
            pass
        
        # OpenAI-compatible chat completion endpoint
        endpoint = f"http://{ip}:{port}{self.properties['path']}"
        
        payload = {
            "model": model,
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
                    content=ai_message,
                    metadata={
                        "endpoint": endpoint,
                        "model": model,
                        "usage": usage
                    },
                    status="success"
                )
        except Exception as e:
            self.logger.error("generic_llm_request_failed", error=str(e), endpoint=endpoint)
            return NodeOutput(
                trace_id=inp.trace_id,
                content=inp.content,
                status="failure",
                error_message=f"Generic LLM request failed: {str(e)}",
            )