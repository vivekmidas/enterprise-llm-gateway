# backend/app/nodes/built_in/webhook/api.py

from app.nodes.base import TriggerNode, NodeInput, NodeOutput
import time
import json
import asyncio
from typing import List, Dict, Any, Optional
import uvicorn
from fastapi import FastAPI, Request
from pydantic import PrivateAttr

class WebhookAgent(TriggerNode):
    name: str = "api_webhook_agent"
    description: str = "API Webhook Agent for external system integration"
    version: str = "1.0.0"
    category: str = "Integration"
    node_type: str = "trigger"

    property_schema: List[Dict[str, Any]] = [
        {"key": "port", "label": "Listening Port", "type": "number", "placeholder": "8080"},
        {"key": "host", "label": "Host", "type": "string", "placeholder": "0.0.0.0"},
    ]

    properties: Dict[str, Any] = {
        "port": 8080,
        "host": "0.0.0.0"
    }

    _server_task: Optional[asyncio.Task] = PrivateAttr(default=None)

    async def init(self):
        """
        Initialization loads configuration and metadata. 
        The server is no longer started automatically on discovery.
        """
        await super().init()

    def activate(self, agent_node_id: str, workflow_config: Dict[str, Any]):
        """
        Activates the workflow and ensures the Webhook listener server is running.
        """
        super().activate(agent_node_id, workflow_config)

        # Start the listener server only if it hasn't been started yet
        if self._server_task is None:
            self.logger.info("webhook_server_startup_triggered", agent_node_id=agent_node_id)
            self._server_task = asyncio.create_task(self._start_webhook_server(agent_node_id))
        

    async def _start_webhook_server(self, agent_node_id: str):
        """Internal task to run the Uvicorn server."""
        port = int(self.properties.get("port", 8080))
        host = self.properties.get("host", "0.0.0.0")
        workers = int(self.properties.get("workers", 1))

        # Setup FastAPI listener to receive incoming webhook data
        app = FastAPI()

        @app.post("/")
        async def webhook_endpoint( request: Request):
            try:
                payload = await request.json()
                self.logger.info("webhook_received", payload=payload)
                
                # When invoked, find the workflow associated with this specific node ID
                workflow_config = self._workflows.get(agent_node_id)
                self.logger.info("webhook_received_for_registered_node", agent_node_id=agent_node_id)
                if not workflow_config:
                    self.logger.warning("webhook_received_for_unregistered_node")
                    return {"status": "error", "message": f"No workflow registered for trigger"}

                # Build and trigger the graph execution immediately
                asyncio.create_task(self.execute_dynamic_agent(workflow_config, payload))
                return {"status": "triggered", "agent_node_id": agent_node_id}
            except Exception as e:
                self.logger.error("webhook_processing_failed", error=str(e))
                return {"status": "error", "message": str(e)}

        config = uvicorn.Config(app, host=host, port=port, workers=workers, log_level="info", access_log=False)
        server = uvicorn.Server(config)
        self.logger.info("webhook_server_started", host=host, port=port)
        await server.serve()

    async def validate_input(self, inp: NodeInput) -> NodeOutput:
        # Basic validation - can be extended with schema checks
        if not inp.content:
            return NodeOutput(
                trace_id=inp.trace_id,
                content=inp.content,
                status="failure",
                code=400,
                error_message="Content is required"
            )
        return None

    async def execute(self, inp: NodeInput) -> NodeOutput:
        """
        As a trigger node, when this is called inside the graph,
        it simply passes the triggering payload forward.
        """
        return NodeOutput(
            trace_id=inp.trace_id,
            content=inp.content,
            status="success",
            metadata={"source": "api_webhook"}
        )