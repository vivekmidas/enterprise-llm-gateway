# backend/app/nodes/built_in/webhook/api_webhook_agent.py

import abc
import asyncio
import json
import time
from typing import Any, ClassVar, Dict, List, Optional, Tuple

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from pydantic import PrivateAttr
from uvicorn.config import Config

from app.core.types.common import NodeInput, NodeOutput
from app.nodes.base import TriggerNode
from app.utils.type_utils import safe_int


class BaseWebhookAgent(TriggerNode, abc.ABC):
    """
    Abstract Base Webhook Trigger.
    
    Manages Uvicorn/FastAPI server lifecycles on configured host/ports and 
    multiplexes dynamic workflow endpoints onto a shared FastAPI instance 
    using a catch-all wildcard router.
    """
    node_type: str = "trigger"

    # Shared class-level dictionaries mapping (host, port) to running server tasks and apps.
    # Annotated with ClassVar so Pydantic does not treat them as model fields.
    _server_tasks: ClassVar[Dict[Tuple[str, int], asyncio.Task]] = {}
    _fastapi_apps: ClassVar[Dict[Tuple[str, int], FastAPI]] = {}

    # Multiplexing registry mapping (host, port) -> { path_string: (agent_node_id, agent_instance) }
    _active_routes: ClassVar[Dict[Tuple[str, int], Dict[str, Tuple[str, Any]]]] = {}

    # Endpoint tracking: agent_node_id -> (server_key, path)
    _endpoint_to_server_map: ClassVar[Dict[str, Tuple[Tuple[str, int], str]]] = {}

    @abc.abstractmethod
    async def validate_request(self, request: Request, payload: str) -> bool:
        """
        Validate incoming request signatures or security tokens.
        Must be implemented by subclasses.
        """
        pass

    async def activate(self, agent_node_id: str, workflow_config: Dict[str, Any]):
        """
        Activates the webhook trigger node by registering its workflow config in memory.
        The actual routing is handled centrally via the /webhooks/run gateway endpoint.
        """
        self.logger.info("activating webhook agent (gateway routed)", agent_node_id=agent_node_id, name=self.name, function=__name__)
        await super().activate(agent_node_id, workflow_config)

    async def deactivate(self, agent_node_id: str):
        """
        Deactivates a specific workflow instance by removing its route config.
        """
        if agent_node_id in self._workflows:
            del self._workflows[agent_node_id]
            self.logger.info("webhook_deactivated", agent_node_id=agent_node_id)

    async def stop_all_servers(self):
        """Deregisters all active webhook trigger instances."""
        self.logger.info("stopping_all_webhook_agents")
        self._workflows.clear()
        self.logger.info("all_webhook_agents_stopped")

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        self.logger.info("webhook_validation_started")
        if not inp.data:
            return NodeOutput(
                trace_id=inp.trace_id,
                data=inp.data,
                status="failure",
                error_code=400,
                error_message="data is required",
            )

        try:
            json_content = json.loads(inp.data)
            # data_val = (
            #     json_content.get("data") if isinstance(json_content, dict) else json_content
            # )
            # if (
            #     data_val is None
            #     or (isinstance(data_val, str) and not data_val.strip())
            #     or (isinstance(data_val, (dict, list)) and not data_val)
            # ):
            if not json_content:
                return NodeOutput(
                    trace_id=inp.trace_id,
                    data=inp.data,
                    status="failure",
                    error_code=400,
                error_message="Invalid trigger: 'data' field cannot be empty",
            )
        except (json.JSONDecodeError, TypeError):
            pass

        return None

    async def execute(self, inp: NodeInput) -> NodeOutput:
        self.logger.info("webhook_execution_started", trace_id=inp.trace_id, agent_name=self.name)
        return NodeOutput(
            trace_id=inp.trace_id,
            data=inp.data,
            status="success",
            metadata={"source": self.name},
        )


class WebhookAgent(BaseWebhookAgent):
    """
    Standard Webhook Agent.
    Validates optional Bearer tokens configured by admins.
    """
    name: str = "api_webhook_agent"
    description: str = "API Webhook Agent for external system integration"
    version: str = "1.0.0"
    category: str = "Integration"
    node_type: str = "trigger"

    # Define default contracts and properties
    input_contract: Dict[str, Any] = {
        "data": {"type": "json", "required": "True"},
        "auth_token": {"type": "string", "required": "False"},
        "source_system": {"type": "string", "required": "True"},
        "event_type": {"type": "string", "required": "False"},
        "request_id": {"type": "string", "required": "False"}
    }
    output_contract: Dict[str, Any] = {
        "result": {
            "data": "{{data}}",
            "error_code": "{{error_code}}",
            "status": "{{status}}",
            "error_message": "{{error_message}}"
        }
    }
    system_properties: Dict[str, Any] = {
        "base_path": "docs"
    }
    user_properties: Dict[str, Any] = {}

    async def validate_request(self, request: Request, payload: str) -> bool:
        # Check standard headers for Authorization bearer token if configured
        expected_token = self.properties.get("auth_token")
        if not expected_token:
            return True

        provided_token = request.headers.get("Authorization")
        if not provided_token:
            return False

        if provided_token.startswith("Bearer "):
            provided_token = provided_token[7:]

        return provided_token == expected_token