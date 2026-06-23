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
        Activates the workflow and ensures the Webhook listener server is running on configured port.
        """
        self.logger.info("activating webhook agent", agent_node_id=agent_node_id, name=self.name, function=__name__)
        await super().activate(agent_node_id, workflow_config)

        # Resolve instance configuration manually for the background server
        nodes = workflow_config.get("nodes_structure", [])
        node_data = next((n for n in nodes if n.get("id") == agent_node_id), {})
        overrides = (
            node_data.get("data", {}).get("user_properties")
            or node_data.get("data", {}).get("properties")
            or node_data.get("config")
            or {}
        )
        config = {**self.properties, **overrides}

        port = int(config.get("port", 8888))
        host = config.get("host", "0.0.0.0")
        base_path = config.get("base_path", "").strip("/")
        self.logger.info("webhook config", port=port, host=host, base_path=base_path,name=self.name)
        server_key = (host, port)
        route_path = base_path if base_path else agent_node_id

        # Initialize server state mappings if not exist
        if server_key not in self._active_routes:
            self._active_routes[server_key] = {}

        # Check for path conflicts
        if route_path in self._active_routes[server_key]:
            existing_node_id, _ = self._active_routes[server_key][route_path]
            if existing_node_id != agent_node_id:
                self.logger.error(
                    "webhook_route_conflict",
                    path=route_path,
                    port=port,
                    existing_node=existing_node_id,
                    new_node=agent_node_id,
                )
                raise ValueError(
                    f"Path '/{route_path}' is already registered on port {port} by node '{existing_node_id}'"
                )

        # Register this node's route
        self._active_routes[server_key][route_path] = (agent_node_id, self)
        self._endpoint_to_server_map[agent_node_id] = (server_key, route_path)

        if server_key not in self._fastapi_apps:
            self.logger.info("starting_new_webhook_server", host=host, port=port)
            app = FastAPI()
            self._fastapi_apps[server_key] = app

            # Register wildcard/catch-all endpoint
            @app.api_route("/{request_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
            async def webhook_endpoint(request: Request, request_path: str):
                normalized_path = request_path.strip("/")
                routes = self._active_routes.get(server_key, {})

                if normalized_path not in routes:
                    self.logger.warning(
                        "webhook_route_not_found", path=normalized_path, host=host, port=port
                    )
                    raise HTTPException(status_code=404, detail="Webhook path not registered")

                target_node_id, agent_instance = routes[normalized_path]

                try:
                    content_type = request.headers.get("content-type", "")
                    if "application/json" in content_type:
                        payload_json = await request.json()
                        raw_payload = json.dumps(payload_json)
                    else:
                        payload_bytes = await request.body()
                        raw_payload = payload_bytes.decode("utf-8", errors="ignore")
                except Exception as e:
                    self.logger.error("webhook_payload_parse_failed", error=str(e))
                    raise HTTPException(status_code=400, detail="Invalid request payload")

                # Delegate signature verification to the registering agent instance
                try:
                    is_valid = await agent_instance.validate_request(request, raw_payload)
                except Exception as e:
                    self.logger.error("webhook_signature_validation_crashed", error=str(e))
                    is_valid = False

                if not is_valid:
                    self.logger.warning(
                        "webhook_unauthorized", path=normalized_path, agent_node_id=target_node_id
                    )
                    raise HTTPException(status_code=401, detail="Invalid signature or token")

                self.logger.info(
                    "webhook_received", endpoint=normalized_path, agent_node_id=target_node_id
                )
                try:
                    workflow_result = await agent_instance.execute_dynamic_agent(
                        target_node_id, raw_payload
                    )
                    return {
                        "status": "completed",
                        "agent_node_id": target_node_id,
                        "result": workflow_result,
                    }
                except Exception as e:
                    self.logger.error("webhook_workflow_execution_failed", error=str(e))
                    raise HTTPException(status_code=500, detail=str(e))

            # Start the Uvicorn server in a separate asyncio task
            self._server_tasks[server_key] = asyncio.create_task(
                self._run_uvicorn_server(app, host, port)
            )
        else:
            app = self._fastapi_apps[server_key]
            self.logger.info("reusing_existing_webhook_server", host=host, port=port)

        self.logger.info(
            "webhook_endpoint_registered",
            agent_node_id=agent_node_id,
            endpoint=route_path,
            host=host,
            port=port,
        )

    async def _run_uvicorn_server(self, app: FastAPI, host: str, port: int):
        """Internal task to run the Uvicorn server."""
        config = Config(app, host=host, port=port, log_level="info", access_log=False)
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
        Deactivates a specific workflow instance, removing its route.
        If no other workflows use the same (host, port), the server is stopped.
        """
        if agent_node_id in self._workflows:
            del self._workflows[agent_node_id]
            self.logger.info("workflow_unregistered_to_trigger", agent_node_id=agent_node_id)

        mapping = self._endpoint_to_server_map.pop(agent_node_id, None)
        if mapping is None:
            self.logger.warning(
                "deactivation_failed_server_key_not_found", agent_node_id=agent_node_id
            )
            return

        server_key, route_path = mapping

        # Remove from active routes
        if server_key in self._active_routes and route_path in self._active_routes[server_key]:
            del self._active_routes[server_key][route_path]
            self.logger.info(
                "route_unregistered", route_path=route_path, server_key=server_key
            )

        # Stop server if no active routes remain
        if server_key in self._active_routes and not self._active_routes[server_key]:
            self.logger.info("stopping_webhook_server", server_key=server_key)
            task = self._server_tasks.pop(server_key, None)
            if task:
                task.cancel()
                asyncio.create_task(task)
            self._fastapi_apps.pop(server_key, None)
            self._active_routes.pop(server_key, None)

    async def stop_all_servers(self):
        """Gracefully stops all running Uvicorn servers."""
        self.logger.info("stopping_all_webhook_servers")
        tasks_to_await = []
        for server_key, task in list(self._server_tasks.items()):
            self.logger.info("cancelling_webhook_server_task", server_key=server_key)
            task.cancel()
            tasks_to_await.append(task)

        self._server_tasks.clear()
        self._fastapi_apps.clear()
        self._active_routes.clear()
        self._endpoint_to_server_map.clear()
        self._workflows.clear()

        if tasks_to_await:
            await asyncio.gather(*tasks_to_await, return_exceptions=True)
        self.logger.info("all_webhook_servers_stopped")

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
            data_val = (
                json_content.get("data") if isinstance(json_content, dict) else json_content
            )
            if (
                data_val is None
                or (isinstance(data_val, str) and not data_val.strip())
                or (isinstance(data_val, (dict, list)) and not data_val)
            ):
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
        return NodeOutput(
            trace_id=inp.trace_id,
            data=inp.data,
            status="success",
            metadata={"source": "api_webhook"},
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
        "port": "8888",
        "host": "0.0.0.0",
        "workers": 1
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