# backend/app/nodes/built_in/webhook/api.py

from app.nodes.base import TriggerNode, NodeInput, NodeOutput
import time
import json
import asyncio
from typing import List, Dict, Any, Optional,Tuple
import uvicorn
from uvicorn.config import Config
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
        {"key": "path", "label": "Webhook Path (e.g., /my-webhook)", "type": "string", "placeholder": "/webhook"},
    ]

    properties: Dict[str, Any] = {
        "port": 8080,
        "host": "0.0.0.0",
        "path": "/webhook"
    }

    # Store server tasks keyed by (host, port)
    _server_tasks: Dict[Tuple[str, int], asyncio.Task] = PrivateAttr(default_factory=dict)
    # Store FastAPI app instances keyed by (host, port)
    _fastapi_apps: Dict[Tuple[str, int], FastAPI] = PrivateAttr(default_factory=dict)

    _endpoint_to_server_map: Dict[str, Tuple[str, int]] = PrivateAttr(default_factory=dict)

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

        # Extract properties for this specific node instance
        # Align with DB schema 'nodes_structure' while maintaining compatibility with frontend 'nodes'
        nodes_list = workflow_config.get("nodes") or workflow_config.get("nodes_structure", [])
        
        # Handle stringified JSON from Varchar columns
        if isinstance(nodes_list, str):
            nodes_list = json.loads(nodes_list)

        node_data = next((n for n in nodes_list if n["id"] == agent_node_id), None)
        if not node_data:
            self.logger.error("webhook_activation_failed", reason="node_data_not_found", agent_node_id=agent_node_id)
            return

        # Properties are now expected to be re-hydrated into node_data["data"]["properties"]
        # by the WorkflowService.
        props = node_data.get("data", {}).get("properties", {})

        port = int(props.get("port", self.properties["port"]))
        host = props.get("host", self.properties["host"])
        base_path = props.get("path", self.properties["path"]).strip('/') # Remove leading/trailing slashes

        server_key = (host, port)
        full_path = f"/{base_path}/{agent_node_id}" # Unique path for this agent_node_id

        if server_key not in self._fastapi_apps:
            self.logger.info("starting_new_webhook_server", host=host, port=port)
            app = FastAPI()
            self._fastapi_apps[server_key] = app
            # Start the Uvicorn server in a separate asyncio task
            self._server_tasks[server_key] = asyncio.create_task(self._run_uvicorn_server(app, host, port))
        else:
            app = self._fastapi_apps[server_key]
            self.logger.info("reusing_existing_webhook_server", host=host, port=port)

        # Register the specific endpoint for this agent_node_id on the FastAPI app
        # Use a closure to capture agent_node_id for the endpoint handler
        @app.post("/")
        async def webhook_endpoint(request: Request):
            try:
                payload = await request.json()
                self.logger.info("webhook_received", payload=payload, endpoint=full_path, agent_node_id=agent_node_id)
                
                json_payload = json.dumps(payload)
                workflow_result = await self.execute_dynamic_agent(agent_node_id, json_payload)
                return {"status": "completed", "agent_node_id": agent_node_id, "result": workflow_result}
            except Exception as e:
                self.logger.error("webhook_processing_failed", error=str(e), endpoint=full_path, agent_node_id=agent_node_id)
                return {"status": "error", "message": str(e)}
        
        self.logger.info("webhook_endpoint_registered", agent_node_id=agent_node_id, endpoint=full_path, host=host, port=port)
        self._endpoint_to_server_map[agent_node_id] = server_key

    async def _run_uvicorn_server(self, app: FastAPI, host: str, port: int):
        """Internal task to run the Uvicorn server."""
        config = Config(app, host=host, port=port, log_level="info", access_log=False) # Removed workers from here
        server = uvicorn.Server(config)
        self.logger.info("webhook_server_started", host=host, port=port)
        try:
            await server.serve()
        except asyncio.CancelledError:
            self.logger.info("uvicorn_server_stopped", host=host, port=port)
        except Exception as e:
            self.logger.error("uvicorn_server_crashed", error=str(e), host=host, port=port)

    async def deactivate(self, agent_node_id: str):
        """
        Deactivates a specific workflow instance, effectively removing its endpoint
        by making its workflow_config unavailable. If no other workflows use the
        same (host, port), the server is stopped.
        """
        # Remove workflow config from base TriggerNode's registry
        if agent_node_id in self._workflows:
            del self._workflows[agent_node_id]
            self.logger.info("workflow_unregistered_to_trigger", agent_node_id=agent_node_id)

        server_key = self._endpoint_to_server_map.pop(agent_node_id, None)
        if server_key is None:
            self.logger.warning("deactivation_failed_server_key_not_found", agent_node_id=agent_node_id)
            return

        host, port = server_key

        # Check if any other active workflows are still using this server_key
        active_on_this_server = False
        for other_agent_id in self._workflows.keys():
            if self._endpoint_to_server_map.get(other_agent_id) == server_key:
                active_on_this_server = True
                break

        if not active_on_this_server:
            # No other active workflows use this server, so stop it.
            self.logger.info("stopping_webhook_server", server_key=server_key)
            task = self._server_tasks.pop(server_key, None)
            if task:
                task.cancel() # Request the task to be cancelled
                # Await the task to ensure it cleans up properly, but don't block deactivate
                # This needs to be done in an async context, so we create a detached task.
                asyncio.create_task(task)
            del self._fastapi_apps[server_key]
        else:
            self.logger.info("webhook_server_still_in_use", server_key=server_key, agent_node_id=agent_node_id)

    async def stop_all_servers(self):
        """Gracefully stops all running Uvicorn servers."""
        self.logger.info("stopping_all_webhook_servers")
        tasks_to_await = []
        for server_key, task in list(self._server_tasks.items()): # Iterate over a copy
            self.logger.info("cancelling_webhook_server_task", server_key=server_key)
            task.cancel()
            tasks_to_await.append(task)
        
        # Clear dictionaries
        self._server_tasks.clear()
        self._fastapi_apps.clear()
        self._endpoint_to_server_map.clear()
        self._workflows.clear() # Also clear all registered workflows from base class

        # Await all tasks to ensure they are properly shut down
        if tasks_to_await:
            await asyncio.gather(*tasks_to_await, return_exceptions=True)
        self.logger.info("all_webhook_servers_stopped")

    async def validate_input(self, inp: NodeInput) -> Optional[NodeOutput]:
        # Basic validation - can be extended with schema checks
        if not inp.content:
            return NodeOutput(
                trace_id=inp.trace_id,
                content=inp.content,
                status="failure",
                code=400,
                error_message="Content is required"
            )

        try:
            json_content = json.loads(inp.content)
            # Safely check for the 'message' key only if the content is a JSON object.
            # This avoids KeyErrors when passing other types of JSON data.
            if isinstance(json_content, dict) and "message" in json_content and not json_content.get("message"):
                return NodeOutput(
                    trace_id=inp.trace_id,
                    content=inp.content,
                    status="failure",
                    code=400,
                    error_message="Invalid trigger: 'message' field cannot be empty"
                )
        except (json.JSONDecodeError, TypeError):
            # Skip JSON-specific validation if the content is raw text or improperly formatted JSON
            pass

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